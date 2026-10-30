# FocusBuddy — Architecture

FocusBuddy is a two-tier edge system. A **desk device** (ESP32) handles sensing and real-time control. A **phone server** (Android + Termux + Flask) handles AI, voice, storage and the UI. There is no cloud backend. The only calls leaving the phone are optional ones to an LLM API and Google TTS.

## 1. System context

```mermaid
flowchart LR
  subgraph Desk["Desk device — ESP32 DevKit V1"]
    US[HC-SR04<br/>distance] --> MCU
    LD[LDR desk] --> MCU
    LW[LDR window] --> MCU
    TC[Touch wire GPIO4] --> MCU
    MCU((ESP32<br/>firmware)) --> RL[Relay → 5 V USB lamp]
    MCU --> OL[SSD1306 OLED]
    MCU --> BZ[Buzzer]
    MCU --> AMP[MAX98357A I2S → speaker]
  end

  subgraph Phone["Android phone — Termux"]
    HS[[Wi-Fi hotspot]]
    FL[Flask app.py<br/>threaded]
    DB[(SQLite<br/>focusbuddy.db)]
    TTS[gTTS / espeak → ffmpeg<br/>16 kHz PCM cache]
    API[Termux:API<br/>mic STT + phone TTS]
    FL --- DB
    FL --- TTS
    FL --- API
  end

  MCU <-- "POST /api/telemetry every 2 s<br/>GET /api/tts/&lt;id&gt;.pcm" --> HS --> FL
  Browser[Dashboard<br/>laptop or phone browser] <-- "GET /api/state every 2 s<br/>POST /api/command, /ask, /summary" --> FL
  FL -. "optional HTTPS" .-> LLM[(OpenAI-compatible LLM)]
  TTS -. "optional HTTPS" .-> GT[(Google TTS)]
```

## 2. Components

### 2.1 ESP32 firmware (`focusbuddy_esp32.ino`)

A single cooperative loop built on `millis()`. No RTOS tasks are created by the sketch.

| Cadence | Work |
|---|---|
| 150 ms | Ultrasonic ping → ring buffer of 5 → median distance |
| 500 ms | Desk + window LDR, 8-sample average each, → 0–100 % |
| every loop | `updatePresence` → `updateTooClose` → `updateLamp` → `updatePomo(dt)` → `checkTouch` |
| 250 ms | Redraw OLED |
| 2 s | `syncServer()`: POST telemetry + events, apply response, play pending TTS |
| 15 s | Wi-Fi reconnect attempt if disconnected (latest firmware) |
| 1 s | Serial calibration line |

All thresholds and hardware polarity flags are in the `USER CONFIG` block (see [SETUP §3](../focusbuddy/SETUP.md)).

### 2.2 Phone server (`app.py`)

| Module area | Responsibility |
|---|---|
| Routes | `/`, `/api/telemetry`, `/api/tts/<id>.pcm`, `/api/state`, `/api/command`, `/api/ask`, `/api/listen`, `/api/summary` ([API.md](API.md)) |
| State | `latest` (last telemetry), `settings` (lamp mode, focus/break min), `oneshot` (say/oled/buzz/pomo delivered once), `recent` (deque of 80 events) |
| Concurrency | Flask `threaded=True`; `state_lock` guards in-memory state, `db_lock` serialises SQLite; each device event and each speak runs on a daemon thread |
| AI | `llm()` → OpenAI-compatible chat completions; `context()` builds grounding; `clean()` sanitises output |
| Speech out | `make_tts()` gTTS→MP3 or espeak→WAV, then ffmpeg → s16le 16 kHz mono PCM; `phone_say()` fallback |
| Speech in | `listen_phone()` → `termux-speech-to-text` (40 s timeout) |
| Storage | SQLite file next to `app.py`; connection per query |

### 2.3 Dashboard (`static/index.html`)

Single HTML file with no build step: vanilla JS, CSS grid, Chart.js 4 from CDN. It polls `/api/state` every 2 s and re-renders tiles, charts and the activity log. Controls `POST` to `/api/command`, `/api/ask`, `/api/listen` and `/api/summary`. All event text is passed through `escapeHtml()`.

## 3. Key flows

### 3.1 Telemetry heartbeat (every 2 s)

```mermaid
sequenceDiagram
  participant D as ESP32
  participant S as Phone server
  participant DB as SQLite
  D->>S: POST /api/telemetry {state…, events:[…]}
  S->>S: latest = state, last_seen = now
  alt ≥ 10 s since last row
    S->>DB: INSERT telemetry
  end
  loop each event
    S->>DB: INSERT events(device, name)
    S-)S: thread handle_event(name)
  end
  S-->>D: {lamp_mode, focus_min, break_min, say, oled, buzz, pomo}
  S->>S: clear one-shot fields
  D->>D: apply settings / commands, clear event queue
```

The device's event queue is cleared **only on HTTP 200**, so events survive a dropped request.

### 3.2 Coaching event (e.g. `too_close`)

```mermaid
sequenceDiagram
  participant D as ESP32
  participant S as Phone server
  participant L as LLM
  D->>D: < 45 cm for 8 s → beep ×2, OLED "Too close!"
  D->>S: telemetry events:["too_close"]
  S-)S: handle_event (rate limit: 15 s since last line)
  S->>L: SYSTEM + EVENT_PROMPTS[too_close] + context()
  L-->>S: "You're leaning in quite a bit…"
  Note over S: on error / no key → random FALLBACK line
  S->>S: clean() → make_tts() → oneshot.say = id, oneshot.oled = text[:84]
  D->>S: next telemetry
  S-->>D: say=id, oled=text
  D->>S: GET /api/tts/id.pcm
  S-->>D: 16 kHz s16le PCM stream
  D->>D: I2S → MAX98357A → speaker
```

### 3.3 Voice question via touch

```mermaid
sequenceDiagram
  participant U as User
  participant D as ESP32
  participant S as Phone server
  participant P as Termux:API
  participant L as LLM
  U->>D: touches wire on GPIO 4
  D->>D: beep, OLED "Listening… speak to the phone"
  D->>S: telemetry events:["ask"]
  S->>P: termux-speech-to-text
  U->>P: "How can I study better after lunch?"
  P-->>S: transcript
  S->>L: question + context()
  L-->>S: ≤ 3 spoken sentences
  S-->>D: say=id (next heartbeat) → device plays answer
```

### 3.4 Daily report

`POST /api/summary` aggregates today's rows (`AVG(desk)`, `AVG(win)`, `SUM(present)`, `MAX(focus_s)`, `MAX(sessions)`, event counts, best focus hour) into a facts string. The LLM turns that into a 3–4 sentence report plus exactly two `Tip:` lines. Without a key, the facts plus two default tips are returned. If `speak: true`, the first two sentences are spoken.

## 4. Device state machines

### 4.1 Presence

```mermaid
stateDiagram-v2
  [*] --> Away
  Away --> Away: dist ≥ 100 cm (reset candidate)
  Away --> Present: dist < 100 cm for > 2 s / sit_down
  Present --> Present: dist < 100 cm (reset candidate)
  Present --> Away: dist ≥ 100 cm for > 10 s / left_desk, re-arm auto-start
```

### 4.2 Pomodoro

```mermaid
stateDiagram-v2
  [*] --> Idle
  Idle --> Focus: present ∧ auto-start armed / focus_start
  Idle --> Focus: dashboard Start
  Focus --> Focus: present → count down + add focus time
  Focus --> Focus: away → paused (no countdown)
  Focus --> Break: remaining ≤ 0 / sessions++, beep×3, break_start
  Focus --> Idle: dashboard Stop (disarm auto-start)
  Break --> Focus: remaining ≤ 0 ∧ present / break_end, focus_start
  Break --> Idle: remaining ≤ 0 ∧ away / break_end
```

The break timer runs whether or not you are present: a break is a break.

### 4.3 Smart lamp (auto mode)

```mermaid
stateDiagram-v2
  [*] --> Off
  Off --> On: present ∧ desk < 35 % ∧ window < 70 % / lamp_on
  On --> Off: away for > 60 s / lamp_off
  On --> Off: window > 70 % for 10 s / lamp_off
```

**Why two sensors:** once the lamp is on, the desk sensor measures the lamp itself and would immediately say "bright enough". So the desk sensor only decides **ON**, and the window sensor, aimed away from the lamp, decides **OFF**. Modes `on` / `off` from the dashboard override auto.

### 4.4 Too-close alert

```mermaid
stateDiagram-v2
  [*] --> Armed
  Armed --> Timing: present ∧ dist < 45 cm
  Timing --> Armed: dist > 50 cm
  Timing --> Fired: held 8 s ∧ 60 s since last alert / too_close
  Fired --> Armed: dist > 50 cm (hysteresis)
```

## 5. Data model (SQLite)

```sql
CREATE TABLE telemetry(           -- one row per ≥ 10 s
  ts REAL,          -- unix time
  present INT,      -- 0/1
  distance INT,     -- cm, 999 = no echo
  desk INT,         -- desk light %
  win INT,          -- window light %
  lamp INT,         -- 0/1
  pomo TEXT,        -- idle | focus | break
  focus_s INT,      -- device focus seconds (since device boot)
  sessions INT,     -- completed sessions (since device boot)
  too_close INT     -- too-close alerts (since device boot)
);
CREATE TABLE events(ts REAL, type TEXT, text TEXT);
-- type: device (text = event name) | ai (spoken line) | you (user question) | error | summary
```

Derived metrics: minutes at desk = `SUM(present) × 10 / 60` (each row ≈ 10 s). Focused minutes by hour = the same, restricted to `pomo = 'focus'` and grouped by local hour.

## 6. Audio pipeline

```
LLM text ─► clean() ─► gTTS (MP3, accent TTS_TLD)  ─┐
                    └► espeak (WAV, offline)  ─────┴► ffmpeg -ac 1 -ar 16000 -f s16le ─► tts_cache/<10-hex>.pcm
ESP32: HTTP GET stream ─► 512-sample chunks ─► × VOLUME_PCT ─► duplicate to L+R ─► I2S 16 kHz 16-bit stereo ─► MAX98357A
```

32,000 bytes ≈ 1 s of audio. IDs are 10 random hex characters, validated by regex before any file access.

## 7. Failure modes and graceful degradation

| Failure | Device behaviour | Server behaviour | User sees |
|---|---|---|---|
| No Wi-Fi / phone off | Full local features; OLED "no WiFi"; reconnect every 15 s | — | Timer, lamp, alerts still work |
| Server down | OLED "no AI"; events stay queued (max 8) | — | Same as above |
| No LLM key / LLM error | — | `FALLBACK` lines; error logged | Spoken built-in lines; pill "AI off" |
| No internet for gTTS | — | espeak voice | Robotic but working voice |
| ffmpeg/TTS failure or device offline | — | `termux-tts-speak` on phone | Phone speaks instead |
| STT fails / silence | — | OLED "Sorry, I didn't catch that" | Retry or type on dashboard |
| Dashboard can't reach server | — | — | Pill "Server offline" |

## 8. Timing and threshold reference

| Constant | Default | Where |
|---|---|---|
| `PRESENT_CM` / sit-down hold / away hold | 100 cm / 2 s / 10 s | firmware |
| `CLOSE_CM` / hold / cooldown / re-arm | 45 cm / 8 s / 60 s / > 50 cm | firmware |
| `DESK_DARK_PCT` / `WINDOW_BRIGHT_PCT` | 35 % / 70 % | firmware |
| `WINDOW_OFF_HOLD_MS` / `LAMP_OFF_DELAY_MS` | 10 s / 60 s | firmware |
| Focus / break | 25 / 5 min (dashboard: 50/10, 2/1) | server `settings` → device |
| Telemetry sync / HTTP timeout | 2 s / 1.5 s | firmware |
| Touch threshold / debounce | < 60 % baseline / 4 s | firmware |
| Device online window | 8 s | server |
| DB persist interval | 10 s | server |
| Speech gap / greeting gap | 15 s / 600 s | server |
| LLM timeout / max tokens | 25 s / 120–300 | server |
| TTS cache TTL | 1 h | server |
