---
name: telemetry-contract
description: Use when adding, renaming or removing any FocusBuddy telemetry field, device event, or server command — keeps the ESP32 firmware, app.py, simulate.py, the dashboard, the SQLite schema and docs/API.md in sync.
---

# Telemetry contract change checklist

The ESP32 and the phone talk through one call: `POST /api/telemetry` every 2 s. The request carries sensor state + queued events; the response carries settings + one-shot commands. Spec: `docs/API.md`.

A field changed in one place and not the others fails silently: ArduinoJson defaults (`r["x"] | 0`) and Python `.get()` hide the mismatch.

## Touch every one of these

| # | File | What to update |
|---|---|---|
| 1 | `focusbuddy/esp32/.../focusbuddy_esp32.ino` | `syncServer()` request fields / response parsing; `pushEvent()` names |
| 2 | `focusbuddy/server/app.py` | `telemetry()` insert, `context()` LLM context, `EVENT_PROMPTS` + `FALLBACK` for spoken events, `summary()` counts |
| 3 | SQLite schema in `init_db()` | `CREATE TABLE IF NOT EXISTS` does **not** migrate. New columns need an `ALTER TABLE` guarded by a column check, or existing phones break |
| 4 | `focusbuddy/server/simulate.py` | Send the new field / emit the new event |
| 5 | `focusbuddy/server/static/index.html` | Stat tiles, charts, `LABELS` map for event names |
| 6 | `docs/API.md` | Field tables and examples |
| 7 | `docs/GUARDRAILS.md` | If the change adds a rate limit, validation rule or safety behaviour |

## Rules

- Event names are `snake_case` strings, ≤ 16 chars. The device queue holds 8 events between syncs; don't emit per-loop events.
- Server one-shot commands (`say`, `oled`, `buzz`, `pomo`) are cleared after one delivery. Keep that semantics.
- Validate every new command server-side (whitelist enums, clamp numbers) before it reaches the device.
- Keep the response small: the ESP32 uses a 1.5 s HTTP timeout.
- Backwards compatible by default: old firmware must still work against the new server.

## Verify

Run the `simulate-and-test` skill, then `arduino-cli compile` (`esp32-firmware` skill).
