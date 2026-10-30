---
name: ai-coaching-prompts
description: Use when changing what FocusBuddy says — LLM system/event prompts, fallback lines, daily report, the LLM provider or model, or the TTS voice/accent — with spoken-output, safety and rate-limit guardrails.
---

# AI coaching prompts

All AI behaviour is in `focusbuddy/server/app.py`:

| Piece | Where | Purpose |
|---|---|---|
| `SYSTEM` | persona | Warm desk companion; output is **spoken**: plain English, short, no emojis/lists/markdown |
| `EVENT_PROMPTS` | per device event | `too_close`, `break_start`, `break_end`, `sit_down` |
| `FALLBACK` | per event + `ask` | Used when there is no key, no internet or the LLM errors |
| `context()` | grounding | Time, focus minutes, sessions, too-close count, distance, light, lamp, timer state |
| `get_reply()` | Q&A | ≤ 3 short spoken sentences, `max_tokens=180` |
| `summary()` | daily report | 3–4 sentences + exactly 2 `Tip:` lines from real DB facts, `max_tokens=300` |
| `clean()` | output filter | Strips `* # _ \` > [ ]`, collapses whitespace |

## Guardrails for any prompt change

1. **Fallback parity.** Every key in `EVENT_PROMPTS` must have ≥ 2 lines in `FALLBACK`. The product must sound fine with AI off.
2. **Speakable.** One or two sentences per event. Anything longer clogs the speaker and the 84-char OLED preview.
3. **Grounded.** Only state facts present in `context()` or the summary `facts`. Don't let the model invent stats.
4. **No medical advice.** Eye/posture tips stay general wellness (20-20-20 rule, sit back, stretch, water). No diagnoses, no conditions, no medication.
5. **Tone.** Encouraging, never shaming. Students are the audience.
6. **Rate limits stay.** 15 s between spoken lines (except `break_start`), greeting at most every 10 min, too-close cooldown 60 s on the device.
7. **User text is untrusted.** Questions go into the user message, never the system prompt. Output is only spoken + shown via `escapeHtml`, so no tool or code execution path exists — keep it that way.
8. **Small budgets.** Keep `max_tokens` ≤ 300 and the 25 s request timeout; the server must stay responsive on a phone.

## Switching provider / model

Any OpenAI-compatible `/chat/completions` endpoint works. Change env vars only — no code change:

```bash
export LLM_BASE_URL="https://api.groq.com/openai/v1"   # or OpenRouter, Gemini OpenAI-compatible, etc.
export LLM_MODEL="<model id from the provider>"
export LLM_API_KEY="<set by the user, never committed>"
```

## Voice

`TTS_TLD` selects the gTTS accent (`co.in` Indian English by default; `com`, `co.uk`, `com.au` …). Offline fallback is `espeak`. Audio is resampled to 16 kHz mono s16le for the ESP32.

## Verify

Run `simulate-and-test` twice: once with a key, once with `LLM_API_KEY` unset. Read every `ai` line in the activity log out loud — if it doesn't sound natural spoken, rewrite it.
