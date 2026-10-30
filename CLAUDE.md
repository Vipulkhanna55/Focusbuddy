# CLAUDE.md — FocusBuddy

Guidance for Claude Code (and any AI agent) working in this repository. Read this first.

## What this project is

FocusBuddy is an AI desk companion for students. An **ESP32** on the desk senses presence, screen distance and light, drives a lamp relay, an OLED, a buzzer and a speaker. A **Flask server running on an Android phone (Termux)** receives telemetry every 2 s, stores it in SQLite, generates short spoken coaching lines with an LLM (any OpenAI-compatible API), converts them to speech, streams the audio back to the ESP32 speaker, and serves a live web dashboard.

```
ESP32 (sensors, relay, OLED, buzzer, I2S speaker) <-- Wi-Fi / phone hotspot --> Android phone: Termux + Flask
                                                                                 ├─ SQLite history
                                                                                 ├─ LLM coaching (OpenAI-compatible)
                                                                                 ├─ gTTS / espeak -> ffmpeg -> 16 kHz PCM
                                                                                 ├─ Termux:API mic (speech-to-text)
                                                                                 └─ Dashboard  http://<phone-ip>:5000
```

Deep dives: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/MOBILE_HOSTING.md](docs/MOBILE_HOSTING.md), [docs/API.md](docs/API.md), [docs/GUARDRAILS.md](docs/GUARDRAILS.md), [docs/PRD.md](docs/PRD.md).

## Repository map

| Path | What it is |
|---|---|
| `focusbuddy/server/app.py` | Phone server: telemetry API, LLM, TTS, STT, SQLite, dashboard routes |
| `focusbuddy/server/static/index.html` | Single-page dashboard (vanilla JS + Chart.js), polls `/api/state` every 2 s |
| `focusbuddy/server/simulate.py` | Fake ESP32 — exercises the full server + dashboard without hardware |
| `focusbuddy/server/requirements.txt` | `flask`, `requests`, `gTTS` (kept Termux-installable on purpose) |
| `focusbuddy/esp32/focusbuddy_esp32/focusbuddy_esp32.ino` | ESP32 firmware (Arduino-ESP32 core 3.x) |
| `focusbuddy/SETUP.md` | Parts list, wiring, flashing, calibration, phone setup, demo script |
| `focusbuddy.zip` | The `focusbuddy/` folder packaged for transfer to the phone |
| `*.ino`, `app.py`, `SETUP.md` at repo root | Working copies used during the build. **`focusbuddy/` is the canonical tree** — make changes there |
| `.claude/` | Agent guardrails: `settings.json` (permissions + hooks), `hooks/guardrails.py`, `skills/` |
| `.mcp.json` | Reference MCP config for the planned Odoo integration (not connected) |

## Commands

```bash
# Server on a laptop (for development; production host is the phone)
cd focusbuddy/server && pip install -r requirements.txt && python3 app.py      # needs ffmpeg for device audio

# Fake device (second terminal) — full end-to-end without hardware
python3 focusbuddy/server/simulate.py http://127.0.0.1:5000

# Quick checks
python3 -m py_compile focusbuddy/server/app.py focusbuddy/server/simulate.py
curl -s http://127.0.0.1:5000/api/state | python3 -m json.tool | head -40

# Firmware compile (no upload)
arduino-cli compile --fqbn esp32:esp32:esp32 focusbuddy/esp32/focusbuddy_esp32
```

Env vars for the server: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `TTS_TLD`, `PORT` — see `focusbuddy/server/.env.example`. With no key the product still works using built-in fallback lines.

## Hard rules (guardrails)

These are non-negotiable. The **Enforced by** column says what stops a violation; "Review" means you must self-check.

| # | Rule | Enforced by |
|---|---|---|
| 1 | **Never write secrets** (LLM keys, Odoo keys, private keys) into any file. Never create or edit `.env` — only `.env.example` with placeholders. | `hooks/guardrails.py` (blocks), `settings.json` deny `Read(.env)` |
| 2 | **Never print secrets** — no `echo $LLM_API_KEY`, `printenv`, bare `env`. | `hooks/guardrails.py` |
| 3 | **No destructive commands**: `rm -rf`, `git push --force`, `git reset --hard`, `git clean -f`, `sudo`, `curl … \| sh`, `esptool erase_flash`, `DROP TABLE` / `DELETE FROM telemetry/events`. | `hooks/guardrails.py` + `settings.json` deny |
| 4 | **Flashing hardware, installing packages, committing and pushing need the user's OK.** | `settings.json` `ask` rules |
| 5 | **Low voltage only.** The relay switches a 5 V USB lamp. Never add code, docs or wiring that switches 110/230 V mains. | Review |
| 6 | **Relay must be OFF at boot.** In `setup()`, the OFF level is written *before* `pinMode(OUTPUT)`. Keep that order. | Review |
| 7 | **ESP32 GPIO is 3.3 V.** Any 5 V signal (e.g. HC-SR04 ECHO) needs the 1 kΩ/2 kΩ divider. Don't change pins without updating `SETUP.md`. | Review |
| 8 | **Wi-Fi credentials in committed firmware are placeholders.** Real SSID/password/server IP stay local. | Review (flagged in docs) |
| 9 | **Every AI line has a non-AI fallback.** New event → add to `EVENT_PROMPTS` *and* `FALLBACK`. The product must run with no API key and no internet. | Review — `ai-coaching-prompts` skill |
| 10 | **AI output is spoken.** Keep the `SYSTEM` prompt constraints (short, plain spoken English, no markdown/emojis), keep `clean()`, keep `max_tokens` small, keep the rate limits (15 s between lines, 10 min between greetings, 60 s too-close cooldown). | Review |
| 11 | **No medical claims.** FocusBuddy is a study-habit coach, not a medical or ergonomic device. Prompts and docs must not diagnose or treat. | Review |
| 12 | **Privacy by default.** No camera, no stored audio, data stays in SQLite on the phone. Never add uploads of telemetry to third parties without an explicit opt-in setting. | Review |
| 13 | **Keep the telemetry contract in sync** across firmware ↔ `app.py` ↔ `simulate.py` ↔ `docs/API.md`. | `telemetry-contract` skill |
| 14 | **Validate at the HTTP boundary.** Keep the TTS id regex (`[0-9a-f]{10}`), whitelists for `lamp_mode`/`pomo`, clamping of `focus_min`/`break_min`, and `escapeHtml` in the dashboard. | Review |
| 15 | **Firmware loop stays responsive.** Use `millis()` timers, not new long `delay()` calls. Sensor cadences: distance 150 ms, light 500 ms, OLED 250 ms, sync 2 s. | Review |
| 16 | **Termux-compatible dependencies only.** No packages that need heavy native builds on Android. Prefer stdlib. | Review |
| 17 | **Odoo is read-only unless the user confirms a write**, and `.mcp.json` must only contain `${ENV}` placeholders. | `settings.json` `ask` on `.mcp.json`, `odoo-sync` skill |

If a task seems to require breaking a rule, stop and ask the user.

## Skills in this repo

Project skills live in `.claude/skills/`. Use them — they encode the checklists for this codebase.

| Skill | Use when |
|---|---|
| `esp32-firmware` | Editing, compiling or flashing the `.ino` |
| `phone-server-deploy` | Installing/running the server on the Android phone (Termux) |
| `simulate-and-test` | Verifying any server/dashboard change without hardware |
| `sensor-calibration` | Tuning distance/light thresholds, relay/buzzer polarity |
| `telemetry-contract` | Adding/renaming a telemetry field, event or command |
| `ai-coaching-prompts` | Changing what FocusBuddy says, LLM provider, TTS voice |
| `hackathon-demo` | Pre-flight checklist and the 3-minute live demo |
| `odoo-sync` | (Planned) pushing focus sessions to Odoo Timesheets via MCP |
| `github-push` | Committing and pushing to GitHub — runs `precheck.py` (repo root, secrets, Wi-Fi passwords, forbidden/large files) first |

## Conventions

- Match the existing style: small, flat, single-file modules; plain Flask; vanilla JS; no build step.
- Python: stdlib first, f-strings, short helper functions, comments only where intent isn't obvious.
- Firmware: all tunables live in the `USER CONFIG` block at the top; state machines are `update*()` functions called from `loop()`.
- Dashboard: no frameworks; all dynamic text that can come from the device or the LLM goes through `escapeHtml`.

## Definition of done

1. `python3 -m py_compile` passes for changed Python files.
2. `simulate.py` runs a full cycle (sit down → too close → break) against the server with no errors in the activity log.
3. Firmware changes compile with `arduino-cli compile`.
4. Docs updated: `docs/API.md` for contract changes, `SETUP.md` for wiring/pins, `docs/GUARDRAILS.md` for any new safety behaviour.
5. No hard rule above was broken.
