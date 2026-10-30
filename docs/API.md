# FocusBuddy — HTTP API Reference

Base URL: `http://<phone-ip>:5000` (port from `PORT`). All bodies are JSON. No authentication in the MVP: the API is meant for a private, password-protected phone hotspot (see [GUARDRAILS §3](GUARDRAILS.md#3-privacy-and-data-protection)).

| Method | Path | Caller | Purpose |
|---|---|---|---|
| `POST` | `/api/telemetry` | ESP32 (every 2 s) | Push state + events, receive settings + commands |
| `GET` | `/api/tts/<id>.pcm` | ESP32 | Download speech audio |
| `GET` | `/api/state` | Dashboard (every 2 s) | Live state, charts, events |
| `POST` | `/api/command` | Dashboard | Lamp mode, session lengths, start/stop, buzz, say |
| `POST` | `/api/ask` | Dashboard | Typed question → AI answer (also spoken) |
| `POST` | `/api/listen` | Dashboard | Ask the phone mic to listen for a question |
| `POST` | `/api/summary` | Dashboard / integrations | End-of-day report |
| `GET` | `/` | Browser | Dashboard HTML |

---

## `POST /api/telemetry`

The device ↔ phone contract. **Any change here must follow the `telemetry-contract` skill.**

### Request (from ESP32)

| Field | Type | Description |
|---|---|---|
| `present` | bool | User at the desk (after hysteresis) |
| `distance_cm` | int | Median screen distance; `999` = no echo |
| `desk_light` | int 0–100 | Desk light % |
| `window_light` | int 0–100 | Window/daylight % |
| `lamp` | bool | Relay state |
| `lamp_mode` | `auto`\|`on`\|`off` | Mode the device is applying |
| `pomo` | `idle`\|`focus`\|`break` | Timer state |
| `remaining_s` | int | Seconds left in the current focus/break |
| `focus_s_today` | int | Focused seconds since device boot |
| `sessions` | int | Completed focus sessions since boot |
| `too_close_count` | int | Too-close alerts since boot |
| `events` | string[] (≤ 8) | Events since last successful sync |

Event names: `sit_down`, `left_desk`, `focus_start`, `too_close`, `break_start`, `break_end`, `lamp_on`, `lamp_off`, `ask`.

```json
{
  "present": true, "distance_cm": 41, "desk_light": 28, "window_light": 12,
  "lamp": true, "lamp_mode": "auto", "pomo": "focus", "remaining_s": 1310,
  "focus_s_today": 2890, "sessions": 1, "too_close_count": 2,
  "events": ["too_close"]
}
```

### Response (to ESP32)

| Field | Type | Persistent / one-shot | Device action |
|---|---|---|---|
| `lamp_mode` | `auto`\|`on`\|`off` | persistent | Sets lamp mode |
| `focus_min` | int 1–120 | persistent | Length of next focus session |
| `break_min` | int 1–120 | persistent | Length of next break |
| `say` | string (10 hex) or `""` | one-shot | Fetch `/api/tts/<say>.pcm` and play |
| `oled` | string ≤ 84 chars or `""` | one-shot | Show for 8 s |
| `buzz` | int | one-shot | Beep N times (device caps at 5) |
| `pomo` | `start`\|`stop`\|`""` | one-shot | Start focus / stop + disarm auto-start |

```json
{ "lamp_mode": "auto", "focus_min": 25, "break_min": 5,
  "say": "3fa9c01b7e", "oled": "You're leaning in quite a bit. Sit back to rest your eyes.",
  "buzz": 0, "pomo": "" }
```

Server side effects: updates `latest` and `last_seen`; inserts a `telemetry` row at most every 10 s; logs each event and handles it on a background thread (coaching, listening).

---

## `GET /api/tts/<id>.pcm`

Raw speech audio: **16 kHz, 16-bit signed little-endian, mono**, `application/octet-stream`. `id` must match `^[0-9a-f]{10}$`, otherwise **404**. Files expire after 1 h.

```bash
curl -s http://127.0.0.1:5000/api/tts/3fa9c01b7e.pcm -o say.pcm
ffplay -f s16le -ar 16000 -ac 1 say.pcm
```

---

## `GET /api/state`

```json
{
  "online": true,
  "ai_ready": true,
  "latest": { "...last telemetry fields..." },
  "settings": { "lamp_mode": "auto", "focus_min": 25, "break_min": 5 },
  "events": [ { "ts": 1761811200.5, "type": "ai", "text": "Great session! ..." } ],
  "series": [ { "ts": 1761811190.0, "distance": 62, "desk": 41, "win": 18, "present": 1 } ],
  "hourly": { "9": 18.5, "10": 42.0 }
}
```

| Field | Meaning |
|---|---|
| `online` | Telemetry received in the last 8 s |
| `ai_ready` | `LLM_API_KEY` and `LLM_MODEL` are set |
| `events` | Latest 40 of: `device`, `ai`, `you`, `error`, `summary` |
| `series` | Telemetry rows from the last hour (for charts) |
| `hourly` | Focused minutes per local hour today |

---

## `POST /api/command`

Any combination of fields:

| Field | Validation | Effect |
|---|---|---|
| `lamp_mode` | must be `auto`, `on` or `off`, otherwise ignored | Persistent setting |
| `focus_min`, `break_min` | integer, clamped to 1–120 | Persistent setting |
| `pomo` | must be `start` or `stop`, otherwise ignored | One-shot to device |
| `buzz` | integer | One-shot beeps |
| `say` | truncated to 300 chars | Spoken via TTS (device, or phone if device offline) |

```bash
curl -s -XPOST http://127.0.0.1:5000/api/command -H 'Content-Type: application/json' \
     -d '{"lamp_mode":"auto","focus_min":2,"break_min":1}'
# {"ok": true, "settings": {"break_min": 1, "focus_min": 2, "lamp_mode": "auto"}}
```

---

## `POST /api/ask`

```bash
curl -s -XPOST http://127.0.0.1:5000/api/ask -H 'Content-Type: application/json' \
     -d '{"question":"How should I plan my next hour?"}'
# {"reply": "You've done forty minutes already, ..."}
```

Empty question → **400** `{"error": "empty question"}`. The reply is also spoken. Without AI, a fixed fallback line is returned.

---

## `POST /api/listen`

Starts `termux-speech-to-text` on the phone in the background (up to 40 s). The transcript is answered and spoken like `/api/ask`. Returns `{"ok": true}` immediately. Requires Termux:API with mic permission.

---

## `POST /api/summary`

```bash
curl -s -XPOST http://127.0.0.1:5000/api/summary -H 'Content-Type: application/json' -d '{"speak":true}'
```

```json
{
  "summary": "You focused for 96 minutes across 3 sessions today ... Tip: ... Tip: ...",
  "facts": "Focused minutes: 96. Completed sessions: 3. Minutes at desk: 140. Too-close-to-screen alerts: 4. Times left the desk: 5. Lamp switched on automatically: 1 times. Average desk light: 47%. Average daylight: 22%. Most focused hour: 10:00."
}
```

`speak: true` speaks the first two sentences. The report is also logged as a `summary` event. `facts` is the structured source used by the planned [Odoo sync](ODOO_INTEGRATION.md).

---

## Event log types (`events.type`)

| Type | Written when |
|---|---|
| `device` | Every device event (text = event name) |
| `ai` | Every line FocusBuddy speaks |
| `you` | Every user question (typed or spoken) |
| `error` | LLM / TTS / STT / phone-speech failures |
| `summary` | Daily report generated |
