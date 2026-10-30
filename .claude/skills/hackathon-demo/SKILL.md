---
name: hackathon-demo
description: Use before and during the FocusBuddy live demo or judging — pre-flight checklist, the 3-minute demo script, pitch lines, and fast recovery steps when something fails on stage.
---

# Hackathon demo

## Pre-flight (T-15 min)

- [ ] Phone charged / on charger; Termux battery optimisation **off**; `termux-wake-lock` run.
- [ ] Phone hotspot ON, **2.4 GHz**, SSID/password match the flashed firmware.
- [ ] `python app.py` running; banner shows `AI: ON (<model>)`.
- [ ] Dashboard open on the laptop (joined to the same hotspot) at `http://<phone-ip>:5000`; both pills green: **Device online**, **AI ready**.
- [ ] OLED header shows `AI on`.
- [ ] Dashboard → **Say** "Testing" → heard on the speaker.
- [ ] Dashboard → **Demo 2 / 1 min**.
- [ ] Phone torch ready (window sensor), hand ready (desk sensor).
- [ ] Backup: a second Termux session ready with `python simulate.py` in case the hardware fails.

## 3-minute script

1. Dashboard shows **AWAY**. One-line problem statement.
2. **Sit down** → timer starts, spoken greeting.
3. **Lean in** under 45 cm for 8 s → beep, OLED warning, spoken nudge; distance chart dips under the red line.
4. **Cover desk sensor** → lamp ON. **Torch on window sensor** → lamp OFF after 10 s.
5. **Walk away** → **PAUSED**; come back → resumes.
6. **Touch the wire** → ask the phone "How can I study better after lunch?" → spoken answer.
7. Session ends (2 min) → spoken break suggestion.
8. **Generate and speak** the daily report.

## Talking points

- *"Students lose hours to distraction and screen strain without noticing. FocusBuddy measures it with real sensors, and AI turns that data into coaching, automatically."*
- **Runs on a phone**: no cloud server, no laptop. The phone is server, database, voice, microphone and hotspot.
- **Works offline**: device logic runs without the phone; server runs without an API key (fallback lines).
- **Privacy**: no camera, distance and light only; history stays on the phone.
- **Guardrails**: low-voltage lamp, rate-limited AI voice, input validation, agent guardrails for AI-assisted development (`CLAUDE.md`, hooks).
- **Roadmap**: Odoo Timesheets sync via MCP (`docs/ODOO_INTEGRATION.md`). Present it as roadmap, not as live.

## On-stage recovery

| Problem | Fix in < 30 s |
|---|---|
| Pill "Device offline" | Check hotspot is on; power-cycle ESP32 (it retries Wi-Fi every 15 s) |
| "AI off" | Keys not exported in this Termux session — fallback lines still work; keep going |
| No sound | Use dashboard **Say**; if still silent, device is offline → phone speaks instead |
| Hardware dead | Run `python simulate.py` and demo the dashboard + AI |
| Phone mic fails | Type the question in **Ask FocusBuddy** on the dashboard |
