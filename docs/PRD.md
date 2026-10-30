# FocusBuddy — Product Requirements Document

| | |
|---|---|
| **Product** | FocusBuddy — AI desk companion for focused, healthy study |
| **Version** | 1.0 (hackathon MVP) |
| **Status** | MVP built and working end-to-end on hardware; integrations on roadmap |
| **Date** | 30 Oct 2026 |
| **Host platform** | Android phone (Termux) as server + ESP32 desk device |
| **Related docs** | [ARCHITECTURE](ARCHITECTURE.md) · [MOBILE_HOSTING](MOBILE_HOSTING.md) · [API](API.md) · [GUARDRAILS](GUARDRAILS.md) · [ODOO_INTEGRATION](ODOO_INTEGRATION.md) · [SETUP](../focusbuddy/SETUP.md) |

---

## 1. Summary

FocusBuddy is a small device on a student's desk paired with their own phone. The device **measures** real study behaviour: whether you're at the desk, how close you sit to the screen, and how bright the desk and window are. The phone **thinks and talks**. It turns those measurements into short spoken coaching, runs a Pomodoro timer that pauses when you leave, switches a lamp when the desk gets dark, answers spoken questions, and writes an end-of-day report.

The whole backend runs **on the phone**: no cloud server, no laptop, no subscription. The phone is the web server, database, AI gateway, voice, microphone and Wi-Fi hotspot.

## 2. Problem

Students working at a desk for long hours face three problems they usually don't notice while they happen:

1. **Lost focus time.** Phone checks, wandering off and unplanned breaks. Generic timers keep counting when you walk away, so the numbers they report are wrong.
2. **Screen strain and posture.** People drift closer to the screen as they concentrate. Most people don't notice until their eyes or neck hurt.
3. **Bad lighting.** People keep studying in a dim room as daylight fades, because nobody stops to turn on a lamp.

Existing tools fall short. Timer apps can't tell whether you're actually there. Screen-time apps can't see your posture or your light. Camera-based solutions feel invasive in a bedroom or hostel.

## 3. Solution

| Need | FocusBuddy response | Sensor / tech |
|---|---|---|
| Know if I'm really studying | Presence detection; Pomodoro only counts while you're at the desk | HC-SR04 ultrasonic |
| Stop me sitting too close | Beep + OLED warning + spoken AI nudge after 8 s under 45 cm | HC-SR04 |
| Fix my lighting automatically | Lamp turns on when the desk is dark and you're there; off in daylight or when you leave | 2 × LDR + relay |
| Coach me, don't nag me | LLM writes 1–2 sentence lines grounded in your live stats; rate-limited | OpenAI-compatible LLM |
| Answer my study questions hands-free | Touch a wire, speak to the phone, hear the answer from the desk speaker | Termux:API STT, gTTS, I2S amp |
| Show me how my day went | Live dashboard + AI daily report with 2 tips | SQLite + Chart.js + LLM |

**Privacy by design:** no camera, no audio stored, history stays on the phone.

## 4. Goals and non-goals

### Goals (MVP)
- G1. Measure presence, screen distance and light accurately enough for real-time feedback on a real desk.
- G2. Deliver helpful, short, spoken coaching at the right moments without spamming.
- G3. Run fully on an Android phone, with no external server and no paid infrastructure.
- G4. Degrade gracefully: the device works without the phone, and the phone works without AI or internet.
- G5. Be buildable by a student from cheap, common parts in an afternoon.

### Non-goals
- Medical or ergonomic diagnosis. FocusBuddy gives general wellness nudges only.
- Camera-based posture or attention tracking.
- Switching mains-voltage appliances.
- Multi-user / classroom management (roadmap).
- Native mobile app (the dashboard is a responsive web page served by the phone).

## 5. Users and personas

| Persona | Context | Needs | Key features |
|---|---|---|---|
| **Aarav, 17, exam aspirant** | Studies 6–8 h/day in a small room, laptop + books | Honest focus time, fewer breaks that run long, less eye strain | Presence-aware Pomodoro, too-close nudges, daily report |
| **Meera, 20, engineering student (hostel)** | Shared room, evening study, unreliable lighting | Lamp that follows her, quiet coaching, privacy (no camera) | Smart lamp, short spoken lines, data stays on phone |
| **Ravi, 26, remote worker / intern** | Logs hours for his employer | Real focus hours he can report | Daily facts; Odoo Timesheet sync (roadmap) |
| **Parent / mentor** (secondary) | Wants progress without surveillance | Summary, not a video feed | Daily report |

## 6. User stories

| ID | As a… | I want… | So that… | Status |
|---|---|---|---|---|
| US-1 | student | the timer to start when I sit down and pause when I leave | my focus minutes are real | ✅ Built |
| US-2 | student | a gentle warning when I lean too close for too long | I protect my eyes and neck | ✅ Built |
| US-3 | student | the lamp to turn itself on when the desk gets dark | I don't keep studying in dim light | ✅ Built |
| US-4 | student | the lamp to turn off when daylight is enough or I've left | I save power without thinking | ✅ Built |
| US-5 | student | a spoken break idea when a session ends | my breaks actually refresh me | ✅ Built |
| US-6 | student | to ask a question out loud and hear an answer | I don't break flow by picking up my phone | ✅ Built |
| US-7 | student | a live dashboard of today's focus, distance and light | I can see patterns | ✅ Built |
| US-8 | student | an end-of-day report with 2 tips | I improve tomorrow | ✅ Built |
| US-9 | student | to control lamp mode and session length from the dashboard | it fits my routine | ✅ Built |
| US-10 | student | everything to keep working when the internet drops | it's reliable | ✅ Built (fallbacks) |
| US-11 | intern | my daily focus hours logged to Odoo Timesheets | I don't do it by hand | 🗺️ Roadmap |
| US-12 | student | a weekly trend view | I see progress over days | 🗺️ Roadmap |

## 7. Functional requirements

Priority: **P0** must-have for demo, **P1** should-have, **P2** nice-to-have. Every requirement marked Built has been implemented in the referenced code.

### 7.1 Desk device (ESP32 firmware)

| ID | Requirement | Pri | Status | Implementation |
|---|---|---|---|---|
| FR-D1 | Measure distance every 150 ms; median of last 5 readings to reject noise; 25 ms echo timeout (~4 m) | P0 | ✅ | `readDistanceCm()`, `medianDist()` |
| FR-D2 | Presence = distance < `PRESENT_CM` (100) for > 2 s; away after ≥ 10 s beyond it. Emit `sit_down` / `left_desk` | P0 | ✅ | `updatePresence()` |
| FR-D3 | Too-close alert when present and < `CLOSE_CM` (45) for 8 s; 60 s cooldown; re-arm only after moving back > 50 cm (hysteresis). Beep ×2, OLED message, `too_close` event, daily counter | P0 | ✅ | `updateTooClose()` |
| FR-D4 | Read desk and window light every 500 ms (8-sample average, 0–100 %, configurable inversion) | P0 | ✅ | `readLightPct()` |
| FR-D5 | Lamp modes `auto` / `on` / `off`. Auto-on when present AND desk < 35 % AND window < 70 %. Auto-off when away > 60 s OR window > 70 % for 10 s. Emit `lamp_on` / `lamp_off` | P0 | ✅ | `updateLamp()` |
| FR-D6 | Pomodoro: auto-start focus on sit-down; count down only while present; on completion → break, session++, beep ×3, `break_start`; break end → beep, `break_end`, next focus if present | P0 | ✅ | `updatePomo()` |
| FR-D7 | Manual Stop disarms auto-start until the user leaves the desk (prevents instant restart) | P1 | ✅ | `autoStartArmed` |
| FR-D8 | Capacitive touch "Ask AI" on GPIO 4: trigger < 60 % of boot baseline, 4 s debounce, beep + `ask` event | P1 | ✅ | `checkTouch()` |
| FR-D9 | OLED (128×64): status (FOCUS/PAUSED/BREAK/READY/AWAY), link state (no WiFi / no AI / AI on), mm:ss timer, distance, lamp, light %; transient messages | P0 | ✅ | `drawOLED()` |
| FR-D10 | Sync with phone every 2 s (`POST /api/telemetry`, 1.5 s timeout); event queue (8) cleared only on HTTP 200 | P0 | ✅ | `syncServer()` |
| FR-D11 | Play server TTS: stream 16 kHz/16-bit PCM over HTTP to MAX98357A via I2S, software volume, L+R duplicated so any amp channel setting works | P0 | ✅ | `playTTS()` |
| FR-D12 | Work fully offline (presence, lamp, timer, alerts, OLED); retry Wi-Fi every 15 s; list visible SSIDs on failure | P0 | ✅ | `setup()`, `loop()` (latest firmware) |
| FR-D13 | Relay boots OFF; supports active-low modules and "float-off" for 5 V relays | P0 | ✅ | `setup()`, `setLamp()`, `RELAY_FLOAT_OFF` |
| FR-D14 | Serial calibration line every 1 s | P1 | ✅ | `loop()` |

### 7.2 Phone server (Flask on Termux)

| ID | Requirement | Pri | Status | Implementation |
|---|---|---|---|---|
| FR-S1 | Accept telemetry, keep latest state in memory, persist a row every ≥ 10 s to SQLite | P0 | ✅ | `telemetry()` |
| FR-S2 | Log every device event; process each in a background thread so the device response is never delayed | P0 | ✅ | `log_event()`, `handle_event()` |
| FR-S3 | Generate coaching for `sit_down`, `too_close`, `break_start`, `break_end` via LLM with live context; fall back to built-in lines | P0 | ✅ | `EVENT_PROMPTS`, `FALLBACK`, `context()` |
| FR-S4 | Rate-limit speech: ≥ 15 s between lines (break start exempt); greeting ≤ once / 10 min | P0 | ✅ | `handle_event()` |
| FR-S5 | Text-to-speech: gTTS (accent via `TTS_TLD`) → ffmpeg → 16 kHz mono PCM; espeak offline fallback; cache pruned after 1 h | P0 | ✅ | `make_tts()`, `cleanup_tts()` |
| FR-S6 | If the device is offline, speak through the phone speaker instead (`termux-tts-speak`) | P1 | ✅ | `speak()`, `phone_say()` |
| FR-S7 | Voice questions: phone mic STT (`termux-speech-to-text`), LLM answer ≤ 3 sentences, spoken on device | P1 | ✅ | `handle_listen()`, `get_reply()` |
| FR-S8 | Typed questions from the dashboard, answer returned + spoken | P1 | ✅ | `POST /api/ask` |
| FR-S9 | Daily report from DB facts (focus min, sessions, desk minutes, alerts, departures, lamp use, avg light, best hour) + 2 tips; optional speak | P1 | ✅ | `POST /api/summary` |
| FR-S10 | Commands: lamp mode, session lengths (clamped 1–120 min), start/stop, buzz, say (≤ 300 chars) | P0 | ✅ | `POST /api/command` |
| FR-S11 | Device online = telemetry within last 8 s | P0 | ✅ | `device_online()` |
| FR-S12 | Works with any OpenAI-compatible provider via env vars; runs without a key | P0 | ✅ | `llm()` |
| FR-S13 | Print dashboard URL + firmware `SERVER` value at start-up | P1 | ✅ | `__main__` |

### 7.3 Dashboard (web, served by the phone)

| ID | Requirement | Pri | Status |
|---|---|---|---|
| FR-W1 | Status pills: device online/offline, AI ready/off | P0 | ✅ |
| FR-W2 | Big timer with state colour and sub-label | P0 | ✅ |
| FR-W3 | 8 live tiles: at desk, distance (colour-coded <45 red, <60 amber), desk light, daylight, lamp + mode, focused today, sessions, too-close alerts | P0 | ✅ |
| FR-W4 | Charts: distance last hour with 45 cm reference line; desk vs daylight last hour; focused minutes by hour today | P1 | ✅ |
| FR-W5 | Controls: lamp Auto/On/Off; Start/Stop; presets 25/5, 50/10, Demo 2/1; Say; Beep | P0 | ✅ |
| FR-W6 | Ask box, "Use phone mic", daily report (generate / generate + speak) | P1 | ✅ |
| FR-W7 | Activity log (last 40) with friendly labels, HTML-escaped | P0 | ✅ |
| FR-W8 | Responsive layout (phone-sized screens) | P1 | ✅ |
| FR-W9 | Poll every 2 s | P0 | ✅ |

### 7.4 Roadmap requirements

| ID | Requirement | Pri | Status |
|---|---|---|---|
| FR-R1 | Odoo Timesheets sync of daily focus hours via MCP (Claude Code) | P2 | 🗺️ Reference config in `.mcp.json`, design in [ODOO_INTEGRATION](ODOO_INTEGRATION.md) |
| FR-R2 | Shared-secret token on device ↔ server API | P1 | 🗺️ |
| FR-R3 | Day counters reset at local midnight (currently reset at device reboot) | P1 | 🗺️ |
| FR-R4 | Weekly trends view + CSV export | P2 | 🗺️ |
| FR-R5 | Wi-Fi/server provisioning without re-flashing (captive portal) | P2 | 🗺️ |
| FR-R6 | Multiple desks per phone (device id in telemetry) | P2 | 🗺️ |

## 8. Non-functional requirements

| Area | Requirement |
|---|---|
| **Latency** | Device → server state visible on dashboard ≤ ~4 s (2 s sync + 2 s poll). Too-close nudge spoken ≈ 8 s hold + LLM + TTS (typically a few seconds). |
| **Availability** | Device core features 100 % offline. Server runs without LLM key / internet (fallback lines, espeak voice). |
| **Host footprint** | One Python process on the phone. Telemetry persisted at most every 10 s → ≤ 8,640 rows/day (well under 1 MB/day). TTS files deleted after 1 h. |
| **Power** | ESP32 + peripherals powered over USB (power bank or charger). Phone held awake with `termux-wake-lock`. |
| **Privacy** | No camera, no microphone recording stored; only distance/light/timer numbers persisted locally. See [GUARDRAILS §3](GUARDRAILS.md#3-privacy-and-data-protection). |
| **Safety** | Low-voltage (5 V USB) lamp only; 5 V → 3.3 V divider on ECHO; relay forced OFF at boot. |
| **Portability** | Any OpenAI-compatible LLM; any Android phone that runs Termux; standard ESP32 DevKit. |
| **Cost** | Indicative hardware BOM ≈ ₹1,300–1,800 (see §10); software $0 with a free-tier LLM. |
| **Maintainability** | ~450-line server, ~550-line firmware, single-file dashboard; no build step. |

## 9. Experience flow

```
Sit down ──► (2 s) present ──► greeting spoken ──► focus timer starts (25 min default)
   │                                                     │
   ├─ lean < 45 cm for 8 s ──► beep + OLED + spoken nudge (≤ 1/min)
   ├─ desk dark ─────────────► lamp ON        daylight bright 10 s ─► lamp OFF
   ├─ walk away ─────────────► PAUSED  (≥ 10 s)  … away 60 s ─► lamp OFF
   ├─ touch wire ────────────► phone listens ─► LLM answer ─► spoken on desk speaker
   └─ timer hits 0 ──────────► beep ×3 + spoken break idea ─► 5 min break ─► next focus
End of day: Dashboard ► "Generate and speak" ► 3–4 sentence report + 2 tips
```

## 10. Hardware bill of materials (indicative)

| Part | Qty | Indicative price (₹) |
|---|---|---|
| ESP32 DevKit V1 (ESP-WROOM-32) | 1 | 350–500 |
| MAX98357A I2S amplifier | 1 | 200–300 |
| Speaker 4–8 Ω, 0.5–3 W (salvaged or new) | 1 | 0–50 |
| HC-SR04 ultrasonic sensor | 1 | 60–100 |
| LDR light sensor module (AO) | 2 | 60–100 |
| 0.96" SSD1306 I2C OLED | 1 | 180–250 |
| 5 V 1-channel relay module | 1 | 50–80 |
| Piezo buzzer | 1 | 10–20 |
| USB LED lamp | 1 | 100–200 |
| Resistors 1 kΩ + 2 kΩ, breadboard, jumpers | — | 100–150 |
| **Total** | | **≈ 1,300–1,800** |

Prices are rough Indian hobby-store estimates and vary by vendor. The phone is the user's own.

## 11. AI design

| Aspect | Decision | Why |
|---|---|---|
| Provider | Any OpenAI-compatible `/chat/completions` (Groq, OpenRouter, Gemini-compatible…) | Free tiers, no lock-in, configurable from the phone |
| Persona | "Warm, upbeat desk companion" for students | Encouraging tone improves adherence; never shaming |
| Output format | Plain spoken English, short, no markdown/emojis/lists, then `clean()` | It's heard, not read; OLED shows first 84 chars |
| Grounding | Every prompt gets live context (time, focus minutes, sessions, alerts, distance, light, lamp, timer) | Specific, believable coaching; no invented stats |
| Budgets | `max_tokens` 120 / 180 / 300, temperature 0.7, 25 s timeout | Fast on mobile networks; short speech |
| Fallbacks | ≥ 2 built-in lines per event | Product works with no key / no internet |
| Rate limits | 15 s between lines, greeting ≤ 1 / 10 min, device too-close cooldown 60 s | Coaching, not nagging |

Full responsible-AI controls: [GUARDRAILS §2](GUARDRAILS.md#2-ai--llm-guardrails).

## 12. Success metrics

All of these can be computed from the on-phone SQLite database (`telemetry`, `events`).

| Metric | Definition | MVP target |
|---|---|---|
| Real focus minutes / day | `MAX(focus_s)` today ÷ 60 | Baseline in week 1, +15 % by week 3 |
| Session completion rate | `break_start` events ÷ `focus_start` events | ≥ 70 % |
| Too-close alerts per focus hour | `too_close` ÷ focus hours | Downward trend week over week |
| Dim-light minutes | Minutes present with desk light < threshold and lamp off | → ~0 in auto mode |
| Coaching spam rate | Spoken lines per hour | ≤ 6 / h outside breaks |
| Device uptime | % of 2 s syncs answered 200 while the phone is on | ≥ 99 % on phone hotspot |
| Demo reliability | Full 8-step demo completes without manual intervention | 100 % in rehearsal |

## 13. Release plan

| Phase | Scope | Status |
|---|---|---|
| **M0 — Hackathon MVP** | Device + phone server + dashboard + LLM coaching + voice Q&A + daily report + simulator + docs + AI dev guardrails | ✅ Done |
| **M1 — Hardening** | Consolidate firmware copies; API token; midnight reset; input-type validation on `/api/command`; non-blocking audio | Next |
| **M2 — Insights** | Weekly trends, CSV export, configurable thresholds from dashboard | Planned |
| **M3 — Integrations** | Odoo Timesheets sync (MCP-assisted, then native) | Planned — config + design ready |
| **M4 — Scale** | Multi-desk per phone, captive-portal provisioning, enclosure design | Exploring |

## 14. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Venue Wi-Fi blocks device-to-device traffic | Device can't reach phone | Use phone hotspot (documented default) |
| Android kills Termux in background | Server stops | `termux-wake-lock`, battery optimisation off |
| LLM provider down / no data | No AI lines | Fallback lines; espeak voice; dashboard still live |
| HC-SR04 noise / soft surfaces | False presence | Median filter + 2 s / 10 s hysteresis; calibration guide |
| Lamp flicker (desk sensor sees lamp) | Annoying | Two-sensor design: window sensor decides OFF |
| 5 V relay won't release from 3.3 V GPIO | Lamp stuck on | `RELAY_FLOAT_OFF` option |
| Unauthenticated LAN API | Someone on the hotspot can send commands | Password-protected private hotspot; token on roadmap |
| User text sent to cloud LLM / gTTS | Privacy | Disclosed; run without key + espeak for fully local mode |
| Mains wiring by a user | Electrical hazard | Docs mandate USB lamp; agent guardrail forbids mains changes |

## 15. Open questions

1. Should focus minutes be shown to parents/mentors, and with what consent model?
2. Is 45 cm the right default for laptops vs desktop monitors? Collect calibration data.
3. Native Odoo sync from the phone vs MCP-assisted sync via Claude Code: which do pilot users prefer?
4. Battery-powered device (no USB power): what duty cycle is acceptable?

## 16. Appendix

### Event catalogue

| Event | Source | Trigger | Spoken? |
|---|---|---|---|
| `sit_down` | device | present for > 2 s | Yes (≤ 1 / 10 min) |
| `left_desk` | device | away ≥ 10 s | No |
| `focus_start` | device | auto-start / Start / after break | No |
| `too_close` | device | < 45 cm for 8 s (60 s cooldown) | Yes |
| `break_start` | device | focus timer reached 0 | Yes (always) |
| `break_end` | device | break timer reached 0 | Yes |
| `lamp_on` / `lamp_off` | device | auto lamp logic | No |
| `ask` | device | touch on GPIO 4 | Triggers phone mic + spoken answer |

### Glossary
- **Termux**: Linux userland app for Android; runs Python, ffmpeg, SQLite.
- **Termux:API**: companion app exposing phone mic (speech-to-text) and TTS to Termux.
- **MAX98357A**: I2S digital-to-analog class-D amplifier.
- **MCP**: Model Context Protocol, the standard for connecting AI agents (e.g. Claude Code) to tools like Odoo.
