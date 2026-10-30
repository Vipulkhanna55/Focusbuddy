---
name: simulate-and-test
description: Use to verify any change to the FocusBuddy server, dashboard or AI prompts without hardware — runs app.py plus the simulate.py fake ESP32 and checks every API endpoint.
---

# Simulate and test (no hardware needed)

`focusbuddy/server/simulate.py` is a fake ESP32. In ~3 minutes it sits down (t≈4 s), starts focus, leans too close (t≈40 s), turns the lamp on, finishes a 2-minute session and takes a 1-minute break. Every response it gets is printed (`OLED:` lines, `speaker would play N s of audio`).

## Run

```bash
# Terminal 1 — server (use a throwaway PORT if 5000 is busy)
cd focusbuddy/server && python3 app.py
# Terminal 2 — fake device
python3 focusbuddy/server/simulate.py http://127.0.0.1:5000
```

Run long-lived processes in the background and stop them when done. Don't leave a server running.

## Endpoint checks

```bash
B=http://127.0.0.1:5000
curl -s $B/api/state | python3 -m json.tool | head -30            # online, ai_ready, latest, events
curl -s -XPOST $B/api/command -H 'Content-Type: application/json' -d '{"lamp_mode":"on"}'
curl -s -XPOST $B/api/command -H 'Content-Type: application/json' -d '{"focus_min":500}'   # expect clamp to 120
curl -s -XPOST $B/api/ask     -H 'Content-Type: application/json' -d '{"question":""}'      # expect 400
curl -s -XPOST $B/api/ask     -H 'Content-Type: application/json' -d '{"question":"How do I stay focused?"}'
curl -s -XPOST $B/api/summary -H 'Content-Type: application/json' -d '{"speak":false}'
curl -s -o /dev/null -w '%{http_code}\n' "$B/api/tts/..%2Fapp.pcm"        # expect 404 (id must be 10 hex chars)
```

## What "pass" looks like

- Activity log shows `device` events in order: `sit_down`, `focus_start`, `too_close`, `lamp_on`, `break_start`, `break_end`.
- Each coaching event produces exactly one `ai` line (rate limit: 15 s gap, greeting max once per 10 min).
- With no `LLM_API_KEY`: lines come from `FALLBACK`, `ai_ready` is false, nothing crashes.
- `error` events only for expected local gaps (e.g. `termux-tts-speak` missing on a laptop).
- `python3 -m py_compile` passes.

## Notes

- Audio to the device needs `ffmpeg` on the host. Without it you'll see `TTS failed` errors and the phone-speech fallback.
- The simulator writes into `focusbuddy.db`. Use a scratch copy of `focusbuddy/server/` if the user's real history must not be touched.
