# FocusBuddy — Guardrails

FocusBuddy is an AI system that controls hardware, talks out loud, listens to a microphone, and runs in a student's room. It also gets built with AI coding agents. This document lists every guardrail. For each one it gives **where it is implemented** and its **status**, so a reviewer can check every claim against the code.

Status legend: ✅ implemented · 🛠️ enforced by tooling (agent hooks/permissions) · 📋 policy (rules agents and contributors must follow) · 🗺️ planned

## Contents
1. [Electrical and physical safety](#1-electrical-and-physical-safety)
2. [AI / LLM guardrails](#2-ai--llm-guardrails)
3. [Privacy and data protection](#3-privacy-and-data-protection)
4. [Input validation and API security](#4-input-validation-and-api-security)
5. [Reliability and graceful degradation](#5-reliability-and-graceful-degradation)
6. [Wellbeing and UX guardrails](#6-wellbeing-and-ux-guardrails)
7. [AI-assisted development guardrails (Claude Code)](#7-ai-assisted-development-guardrails-claude-code)
8. [Integration guardrails (Odoo / MCP)](#8-integration-guardrails-odoo--mcp)
9. [Known gaps and hardening plan](#9-known-gaps-and-hardening-plan)

---

## 1. Electrical and physical safety

| Guardrail | How | Where | Status |
|---|---|---|---|
| Low voltage only | Relay switches the +5 V wire of a USB LED lamp. Mains switching is explicitly forbidden | `SETUP.md` §1–2, `CLAUDE.md` rule 5 | ✅ 📋 |
| Lamp OFF at boot | OFF level written **before** `pinMode(OUTPUT)` so the relay never glitches on | firmware `setup()` | ✅ |
| 5 V → 3.3 V protection | HC-SR04 ECHO through 1 kΩ / 2 kΩ divider into GPIO 18 | `SETUP.md` wiring, `CLAUDE.md` rule 7 | ✅ 📋 |
| Stubborn 5 V relays | `RELAY_FLOAT_OFF` floats the pin for a reliable OFF | firmware `setLamp()` | ✅ |
| Polarity mistakes | `RELAY_ACTIVE_LOW`, `LIGHT_INVERT`, `BUZZER_ACTIVE` config flags + calibration guide | firmware `USER CONFIG`, `sensor-calibration` skill | ✅ |
| Buzzer abuse | Remote beeps capped at 5 per command | firmware `syncServer()` `min(bz, 5)` | ✅ |
| No accidental flash erase | `esptool erase_flash` blocked; uploads require confirmation | `.claude/hooks/guardrails.py`, `.claude/settings.json` `ask` | 🛠️ |

## 2. AI / LLM guardrails

| Guardrail | How | Where | Status |
|---|---|---|---|
| Constrained persona | System prompt: warm desk companion for a student; spoken plain English; no emojis, lists or markdown; short | `SYSTEM` in `app.py` | ✅ |
| Bounded output | `max_tokens` 120 (events), 180 (Q&A), 300 (report); temperature 0.7 | `llm()`, `get_reply()`, `summary()` | ✅ |
| Output sanitisation | `clean()` strips `* # _ \` > [ ]` and collapses whitespace before speech/display | `clean()` | ✅ |
| Display limits | OLED preview truncated to 84 chars; manual `say` truncated to 300 chars | `speak()`, `command()` | ✅ |
| Grounded answers | Every prompt includes live, measured context; daily report built only from DB facts | `context()`, `summary()` | ✅ |
| Separation of roles | User questions go in the **user** message, never in the system prompt | `get_reply()` | ✅ |
| No action authority | LLM output is only spoken and displayed. It never triggers commands, relay changes or code. Prompt injection therefore can't control hardware | architecture (no tool calls) | ✅ |
| No medical claims | Tips limited to general wellness (sit back, 20-20-20 rule, stretch, water); rule for any prompt change | `EVENT_PROMPTS`, `CLAUDE.md` rule 11, `ai-coaching-prompts` skill | ✅ 📋 |
| Deterministic fallback | ≥ 2 human-written lines per event + a fixed answer for questions; used on no key / error | `FALLBACK` | ✅ |
| Timeouts | 25 s LLM, 30 s espeak, 60 s ffmpeg, 40 s STT | `llm()`, `make_tts()`, `listen_phone()` | ✅ |
| Failures are visible | Every LLM/TTS/STT failure logged as an `error` event on the dashboard | `log_event("error", …)` | ✅ |
| Transparent AI status | Dashboard pill "AI ready" / "AI off (no API key)"; OLED "AI on" / "no AI" | `/api/state.ai_ready`, `drawOLED()` | ✅ |

## 3. Privacy and data protection

| Guardrail | How | Where | Status |
|---|---|---|---|
| No camera | Presence and posture from ultrasonic distance only | hardware design | ✅ |
| No audio stored | Mic is used only on explicit request (touch or button); transcript handled in memory; only the question text is logged | `listen_phone()`, `handle_listen()` | ✅ |
| Local-first storage | All history in SQLite on the user's own phone; no cloud database | `DB_PATH` | ✅ |
| Data minimisation | Persisted: numbers (distance, light, presence, timer, counters) and event names; ≤ 1 row / 10 s | `telemetry()` | ✅ |
| Generated audio expires | TTS files deleted after 1 h | `cleanup_tts()` | ✅ |
| Disclosed outbound data | LLM receives aggregate stats + user questions; Google TTS receives text to speak. Fully local mode: no key + espeak | `MOBILE_HOSTING.md` §9, this doc | ✅ |
| Secrets out of git | `.gitignore` covers `.env`, keys, DB, TTS cache; `.env.example` holds placeholders only | `.gitignore`, `focusbuddy/server/.env.example` | ✅ |
| Secrets out of code | Hook blocks key-shaped strings and `.env` writes by agents | `.claude/hooks/guardrails.py` | 🛠️ |
| No third-party telemetry upload without opt-in | Policy for all future features (incl. Odoo) | `CLAUDE.md` rule 12 | 📋 |

## 4. Input validation and API security

| Guardrail | How | Where | Status |
|---|---|---|---|
| Path traversal blocked | TTS id must match `^[0-9a-f]{10}$` before any filesystem access | `tts_file()` | ✅ |
| Random, unguessable audio ids | `uuid4().hex[:10]` | `make_tts()` | ✅ |
| Enum whitelists | `lamp_mode ∈ {auto,on,off}`, `pomo ∈ {start,stop}`; anything else ignored | `command()` | ✅ |
| Numeric clamping | `focus_min`, `break_min` clamped to 1–120 | `command()` | ✅ |
| Empty input rejected | Empty question → 400 | `ask()` | ✅ |
| Malformed JSON tolerated | `get_json(silent=True) or {}` everywhere | all routes | ✅ |
| XSS protection | All event/LLM text rendered through `escapeHtml()`; replies set via `textContent` | `index.html` | ✅ |
| SQL injection | Parameterised queries only (`?` placeholders) | `q()` callers | ✅ |
| Thread safety | `state_lock` for shared state, `db_lock` for SQLite | `app.py` | ✅ |
| Network boundary | Intended for a private WPA2 phone hotspot | `MOBILE_HOSTING.md` §6, §9 | 📋 |

## 5. Reliability and graceful degradation

| Scenario | Guardrail | Where | Status |
|---|---|---|---|
| Phone/Wi-Fi gone | Device keeps presence, timer, lamp, alerts, OLED locally | firmware design | ✅ |
| Wi-Fi drops / hotspot late | Auto-reconnect every 15 s; SSID scan printed on failure | firmware `loop()`, `setup()` | ✅ |
| Lost HTTP request | Events stay queued until a 200 response | `syncServer()` | ✅ |
| Slow server | 1.5 s telemetry timeout keeps the device loop responsive | `syncServer()` | ✅ |
| LLM unavailable | Fallback lines | `FALLBACK` | ✅ |
| gTTS unavailable | espeak offline voice | `make_tts()` | ✅ |
| Device offline when speaking | Speak via phone (`termux-tts-speak`) | `speak()` | ✅ |
| Server restart | Recent events reloaded from SQLite | `init_db()` | ✅ |
| Phone sleeps | `termux-wake-lock` + battery Unrestricted | `MOBILE_HOSTING.md` §7 | 📋 |
| Noisy sensors | Median-of-5 distance, 8-sample light average, 2 s / 10 s presence hysteresis, 5 cm too-close hysteresis | firmware | ✅ |
| Lamp flicker | Two-sensor design: desk decides ON, window decides OFF; 10 s daylight hold | `updateLamp()` | ✅ |
| Hardware failure at demo | `simulate.py` drives the full system | `simulate.py`, `hackathon-demo` skill | ✅ |

## 6. Wellbeing and UX guardrails

| Guardrail | How | Where | Status |
|---|---|---|---|
| No nagging | ≥ 15 s between spoken lines (break announcements exempt) | `handle_event()` | ✅ |
| Greeting limit | Max one greeting per 10 min | `handle_event()` | ✅ |
| Too-close debounce | Must persist 8 s; then 60 s cooldown; re-arms only after moving back > 50 cm | `updateTooClose()` | ✅ |
| Touch debounce | 4 s between "ask" triggers | `checkTouch()` | ✅ |
| Honest focus time | Focus countdown pauses when you leave | `updatePomo()` | ✅ |
| Respect for "stop" | Manual Stop disarms auto-start until you leave the desk | `autoStartArmed` | ✅ |
| Encouraging tone | Persona is warm and upbeat; never shaming | `SYSTEM`, `ai-coaching-prompts` skill | ✅ 📋 |
| User stays in control | Lamp override (on/off/auto), session lengths, start/stop from the dashboard | `/api/command` | ✅ |

## 7. AI-assisted development guardrails (Claude Code)

FocusBuddy is built with AI coding agents. These guardrails stop an agent from leaking secrets, destroying data or hardware state, or quietly breaking the device ↔ phone contract.

### 7.1 Layers

| Layer | File | What it does |
|---|---|---|
| Project brief + hard rules | [`CLAUDE.md`](../CLAUDE.md) | 17 numbered rules, each with its enforcement mechanism; definition of done |
| Pre-execution hook | [`.claude/hooks/guardrails.py`](../.claude/hooks/guardrails.py) | Runs before every `Bash`, `Write`, `Edit`, `MultiEdit`; exit code 2 blocks the action with an explanation |
| Permissions | [`.claude/settings.json`](../.claude/settings.json) | `deny` (secret files, `rm -rf`, `sudo`, force push, hard reset), `ask` (flash, install, commit, push, adb, edit `.mcp.json`), `allow` (compile, py_compile, simulator) |
| Skills (checklists) | [`.claude/skills/`](../.claude/skills/) | Task-specific procedures with built-in guardrails, e.g. the `telemetry-contract` sync checklist |
| Pre-push gate | [`.claude/skills/github-push/precheck.py`](../.claude/skills/github-push/precheck.py) | Before any push: repo root must be the project (not a parent like `$HOME`), no `.env`/DB/key files, no API keys in files **or unpushed commits**, no real Wi-Fi passwords in firmware, no files over GitHub limits. Shares secret patterns with the hook |

### 7.2 What the hook blocks

| Category | Blocked | Why |
|---|---|---|
| Secrets in files | Groq `gsk_…`, OpenAI/Anthropic/OpenRouter `sk-…`, Google `AIza…`, GitHub `ghp_…`, private key blocks | Keys must only live in the user's environment |
| Secret files | Writing `.env`, `.env.local`, `.env.*` (except `.env.example`) | Same |
| Secret disclosure | `echo $LLM_API_KEY`, `$ODOO_API_KEY`, `$ODOO_PASSWORD`, `printenv`, bare `env` | Would print secrets into the transcript |
| Data loss | `rm -rf`, `git reset --hard`, `git clean -f`, `DROP TABLE`, `DELETE FROM telemetry/events` | Protects code and the user's history |
| History rewrite | `git push --force` / `-f` / `--force-with-lease` | Protects shared branches |
| Privilege / supply chain | `sudo`, `curl … \| sh`, `chmod -R 777`, `mkfs`, `dd if=` | No system changes from the agent |
| Hardware | `esptool … erase_flash` | Irreversible device wipe |

Design choices: only **new** content is scanned, so removing a secret is always allowed. The hook **fails open** on malformed input, so a hook bug can never brick the developer's session. Every block message points to `CLAUDE.md` and tells the agent to hand the action to the human.

Verified with 24 allow/block test cases, e.g.:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf focusbuddy"}}' | python3 .claude/hooks/guardrails.py
# FocusBuddy guardrail blocked this action: recursive force delete (rm -rf).   (exit 2)
```

### 7.3 Policy-level rules (reviewed, not machine-enforced)

Low voltage only · relay OFF at boot · 3.3 V GPIO protection · placeholder Wi-Fi credentials in committed firmware · fallback parity for every AI event · spoken-output constraints and rate limits · no medical claims · privacy by default · telemetry contract sync · HTTP boundary validation · non-blocking firmware loop · Termux-compatible dependencies. See `CLAUDE.md` for the full table.

## 8. Integration guardrails (Odoo / MCP)

The Odoo integration is **planned**. `.mcp.json` is a reference configuration and is not connected in the hackathon build. Guardrails are designed in from day one:

| Guardrail | How | Status |
|---|---|---|
| No credentials in config | `.mcp.json` uses `${ODOO_URL}`, `${ODOO_DB}`, `${ODOO_API_KEY}` expansion with harmless placeholder defaults | ✅ |
| Config changes need approval | `Edit/Write(./.mcp.json)` is an `ask` permission | 🛠️ |
| Project MCP servers need approval | Claude Code asks the user before starting any server from a project `.mcp.json` | 🛠️ (Claude Code built-in) |
| Read-first, confirm-to-write | Search → draft → explicit user "yes" → create one record | 📋 `odoo-sync` skill |
| Least privilege | Dedicated Odoo API user limited to Project + Timesheets; no accounting/payroll/HR writes | 📋 |
| No updates/deletes | Agent may only create timesheet lines | 📋 |
| Data minimisation | Only daily totals (`/api/summary` facts) leave the phone, never raw telemetry | 📋 |
| No fabricated success | If the MCP tools aren't available, the agent must say so | 📋 |

## 9. Known gaps and hardening plan

Being explicit about limits is a guardrail too.

| Gap | Risk | Planned fix | Milestone |
|---|---|---|---|
| No API authentication | Anyone on the hotspot can send commands | Shared secret header on all `/api/*`; firmware sends it | M1 |
| Non-numeric `focus_min` / `buzz` raise a 500 | Bad request returns 500 instead of 400 (server keeps running) | `try/except ValueError` → 400 | M1 |
| `/api/ask` question length unbounded | Large prompts cost tokens | Truncate to ~500 chars like `say` | M1 |
| No content moderation on LLM output | Prompt-injected question could produce an off-tone reply (speech/display only) | Post-filter + provider moderation endpoint where available | M2 |
| Day counters reset at device reboot, not midnight | "Today" stats wrong after overnight uptime | Server-side daily baseline at local midnight | M1 |
| Audio playback blocks the firmware loop | Sensors pause while speaking (timer stays accurate because it uses real elapsed time) | Stream audio in a FreeRTOS task | M1 |
| Chart.js from CDN without SRI | Dashboard charts need internet; CDN trust | Vendor the file locally or add an `integrity` hash | M1 |
| Flask development server | Fine for one user on a phone; not for multi-user | `waitress` (pure Python, Termux-friendly) | M2 |
| Wi-Fi/server set at compile time | Re-flash to change network | Captive-portal provisioning | M2 |
