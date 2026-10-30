# FocusBuddy

**An AI desk companion that measures how you really study and coaches you out loud. Its whole backend runs on your phone.**

FocusBuddy is a small ESP32 device on your desk paired with an Android phone. The device senses whether you're at the desk, how close you sit to the screen, and how bright the desk and window are. The phone runs the server, database, AI, voice and dashboard. Together they:

- ⏱️ run a **Pomodoro that pauses when you walk away**, so your focus minutes are real
- 👀 **warn you when you sit too close** to the screen (beep + OLED + spoken nudge)
- 💡 **switch your lamp on** when the desk gets dark, and **off** in daylight or when you leave
- 🗣️ **coach you by voice** with short, context-aware lines from an LLM, rate-limited so it never nags
- 🎙️ **answer spoken questions**: touch a wire, talk to the phone, hear the answer from the desk speaker
- 📊 show a **live dashboard** and write an **AI end-of-day report** with two tips for tomorrow

No camera. No cloud server. No subscription.

> *"Students lose hours to distraction and screen strain without noticing. FocusBuddy measures it with real sensors, and AI turns that data into coaching, automatically."*

---

## How it works

```
┌──────────── Desk device (ESP32) ────────────┐          ┌──────────── Android phone (Termux) ────────────┐
│ HC-SR04 distance   → presence, too-close    │  Wi-Fi   │ Flask server  app.py                           │
│ 2 × LDR            → desk + daylight        │◄────────►│  ├─ SQLite history                             │
│ Relay → 5 V USB lamp                         │ hotspot  │  ├─ LLM coaching (any OpenAI-compatible API)  │
│ 0.96" OLED, buzzer, touch "Ask AI"           │  2 s     │  ├─ gTTS / espeak → ffmpeg → 16 kHz PCM        │
│ MAX98357A I2S amp → speaker                  │          │  ├─ Termux:API mic speech-to-text             │
└──────────────────────────────────────────────┘          │  └─ Dashboard  http://<phone-ip>:5000          │
                                                          └────────────────────────────────────────────────┘
```

- The ESP32 posts sensor state and events every **2 s** and gets back settings and commands (speak this, show that, beep).
- Coaching events (`sit_down`, `too_close`, `break_start`, `break_end`) go to the LLM with live context. The reply is cleaned, turned into speech, and streamed to the desk speaker.
- **Graceful degradation everywhere:** the device works with no phone, and the phone works with no API key or internet (built-in lines, offline espeak voice).

Details: [Architecture](docs/ARCHITECTURE.md) · [Hosting on a phone](docs/MOBILE_HOSTING.md) · [API](docs/API.md)

## 📱 Runs entirely on a phone

The phone is the **server, database, AI gateway, voice, microphone and Wi-Fi hotspot**. Termux provides a Linux userland on Android, so Python, Flask, SQLite and ffmpeg run there natively, and Termux:API exposes the phone's mic and TTS. `termux-wake-lock` keeps it serving with the screen off. The phone's battery acts as a UPS and its mobile data provides internet for the AI, independent of venue Wi-Fi. → [docs/MOBILE_HOSTING.md](docs/MOBILE_HOSTING.md)

## Quick start

### Try it without hardware (2 terminals)

```bash
cd focusbuddy/server
pip install -r requirements.txt          # flask, requests, gTTS  (+ ffmpeg on your system for device audio)
python3 app.py                           # dashboard at http://127.0.0.1:5000
# 2nd terminal, same folder: a fake ESP32 sits down, leans in, takes a break
python3 simulate.py
```

Optional AI (any OpenAI-compatible provider). Without these, built-in lines are used:

```bash
export LLM_API_KEY="…"  LLM_BASE_URL="https://api.groq.com/openai/v1"  LLM_MODEL="<model id>"
```

### Full build

Parts list, wiring, flashing, calibration and phone setup: **[focusbuddy/SETUP.md](focusbuddy/SETUP.md)**. Indicative hardware cost ≈ ₹1,300–1,800.

## Features

| Feature | Sensors | Behaviour |
|---|---|---|
| Presence | HC-SR04 | < 100 cm for 2 s = at desk; away 10 s = left |
| Smart Pomodoro | HC-SR04 + timer | Auto-starts on sit-down, pauses when away, spoken break ideas |
| Eye/posture nudge | HC-SR04 | < 45 cm for 8 s → beep + OLED + spoken nudge (60 s cooldown) |
| Smart lamp | 2 × LDR + relay | Desk dark + present → ON; daylight 10 s or away 60 s → OFF (two sensors prevent flicker) |
| Voice Q&A | Touch wire + phone mic | LLM answer in ≤ 3 spoken sentences on the desk speaker |
| Daily AI report | SQLite | 3–4 sentence summary + 2 tips from real data |
| Dashboard | All | Live tiles, 3 charts, controls, ask box, activity log, responsive |

## Repository

```
.
├── README.md                     ← you are here
├── CLAUDE.md                     ← AI agent brief + 17 hard rules (guardrails)
├── .mcp.json                     ← reference MCP config: Odoo (planned, not connected)
├── .claude/
│   ├── settings.json             ← permissions (deny/ask/allow) + hook wiring
│   ├── hooks/guardrails.py       ← blocks secrets & destructive commands before they run
│   └── skills/                   ← 8 project skills (firmware, phone deploy, testing, calibration, …)
├── docs/
│   ├── PRD.md                    ← product requirements
│   ├── ARCHITECTURE.md           ← components, sequences, state machines, data model
│   ├── MOBILE_HOSTING.md         ← running the backend on Android/Termux
│   ├── API.md                    ← HTTP API + device contract
│   ├── GUARDRAILS.md             ← safety, AI, privacy, security, dev-agent guardrails
│   └── ODOO_INTEGRATION.md       ← roadmap: Odoo Timesheets via MCP
└── focusbuddy/                   ← canonical source
    ├── SETUP.md                  ← hardware + phone setup guide, demo script
    ├── server/                   ← app.py, simulate.py, static/index.html, requirements.txt, .env.example
    └── esp32/focusbuddy_esp32/   ← focusbuddy_esp32.ino
```

## Guardrails

FocusBuddy controls hardware, speaks, listens and runs in someone's room, so guardrails are built into every layer:

- **Physical:** 5 V USB lamp only (no mains), relay forced OFF at boot, 5 V→3.3 V divider on the ultrasonic echo.
- **AI:** constrained spoken persona, small token budgets, output sanitisation, grounding in measured data, no action authority for the LLM, fallback lines, no medical claims.
- **Privacy:** no camera, no stored audio, local SQLite on the user's phone, TTS cache expires after 1 h.
- **Security:** path-traversal-proof audio ids, enum whitelists, numeric clamping, parameterised SQL, XSS escaping.
- **Wellbeing:** rate-limited speech, debounced alerts, encouraging tone, the user can always override.
- **AI-assisted development:** `CLAUDE.md` rules, a tested pre-execution hook, permission deny/ask lists and skills with built-in checklists.

Every item is mapped to code, along with the known gaps: **[docs/GUARDRAILS.md](docs/GUARDRAILS.md)**.

## Built with Claude Code

| Asset | Purpose |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Project brief, commands, hard rules with enforcement mechanism, definition of done |
| [`.claude/skills/`](.claude/skills/) | `esp32-firmware`, `phone-server-deploy`, `simulate-and-test`, `sensor-calibration`, `telemetry-contract`, `ai-coaching-prompts`, `hackathon-demo`, `odoo-sync` |
| [`.claude/hooks/guardrails.py`](.claude/hooks/guardrails.py) | PreToolUse hook: blocks API keys/private keys in files, `.env` writes, secret echo, `rm -rf`, force push, hard reset, `sudo`, `curl \| sh`, flash erase, history deletion |
| [`.claude/settings.json`](.claude/settings.json) | Deny secret reads and destructive commands; ask before flashing, installing, committing, pushing, or editing `.mcp.json` |
| [`.mcp.json`](.mcp.json) | Odoo MCP server reference config with env-var placeholders (roadmap) |

## Roadmap

| Milestone | Scope |
|---|---|
| ✅ M0 Hackathon MVP | Device, phone server, dashboard, AI coaching, voice Q&A, daily report, simulator, docs, agent guardrails |
| M1 Hardening | API token, midnight reset, stricter input types, non-blocking audio, vendored Chart.js |
| M2 Insights | Weekly trends, CSV export, thresholds editable from the dashboard |
| M3 Integrations | **Odoo Timesheets** sync: MCP-assisted first, then native ([design](docs/ODOO_INTEGRATION.md)) |
| M4 Scale | Multiple desks per phone, captive-portal Wi-Fi setup, enclosure |

Full requirements, personas, metrics and risks: **[docs/PRD.md](docs/PRD.md)**.
