# Hosting FocusBuddy on a Mobile Phone

FocusBuddy's entire backend runs on an **Android phone**: web server, database, AI gateway, text-to-speech, speech-to-text, dashboard host and Wi-Fi network. There is no cloud server, no laptop and no Raspberry Pi. This document explains how that works and how to operate it.

## 1. Why a phone

| A phone already has… | Which FocusBuddy uses as… |
|---|---|
| A Linux kernel and multi-core CPU | The application server (Python + Flask via Termux) |
| Flash storage | The SQLite history database |
| A microphone + Google speech services | Voice input (`termux-speech-to-text`) |
| A speaker + TTS engine | Fallback voice when the desk device is offline (`termux-tts-speak`) |
| Mobile data | Internet for the LLM and gTTS, independent of venue Wi-Fi |
| A Wi-Fi hotspot | A private network for the ESP32 and the dashboard viewer |
| A battery | A built-in UPS: the server survives power cuts |
| A browser | A dashboard viewer (the page is responsive) |

The result: **₹0 hosting cost**, nothing extra to buy for the backend, it's portable (it goes wherever the student goes), and the data stays private because it never leaves the student's own phone, apart from the optional LLM/TTS calls.

## 2. Software stack on the phone

```
┌──────────────────────────────── Android ────────────────────────────────┐
│  Termux (F-Droid)                         Termux:API (F-Droid)          │
│  ┌──────────────────────────────────┐     ┌──────────────────────────┐  │
│  │ python app.py  (Flask, threaded) │────►│ termux-speech-to-text    │  │
│  │  ├─ SQLite  focusbuddy.db        │     │ termux-tts-speak         │  │
│  │  ├─ requests → LLM API (HTTPS)   │     └──────────────────────────┘  │
│  │  ├─ gTTS → Google TTS (HTTPS)    │                                   │
│  │  ├─ espeak (offline voice)       │     Hotspot (2.4 GHz)             │
│  │  └─ ffmpeg → 16 kHz PCM          │◄──── ESP32 + dashboard clients    │
│  └──────────────────────────────────┘                                   │
│  termux-wake-lock keeps the CPU awake with the screen off               │
└─────────────────────────────────────────────────────────────────────────┘
```

| Package | Source | Purpose |
|---|---|---|
| `python` | `pkg` | Runtime |
| `flask`, `requests`, `gTTS` | `pip` | Web server, HTTP client, Google TTS |
| `ffmpeg` | `pkg` | Convert MP3/WAV → raw 16 kHz mono PCM for the ESP32 |
| `termux-api` | `pkg` + Termux:API app | Mic speech-to-text, phone TTS |
| `espeak` (optional) | `pkg` | Offline voice fallback |
| `unzip` | `pkg` | Unpack the project zip |

All dependencies are pure-Python or packaged by Termux, so nothing needs compiling on the phone.

## 3. Install (once)

1. Install **Termux** and **Termux:API** from **F-Droid**. The Play Store Termux is outdated, and both apps must come from the same source.
2. Open **Termux:API** once and grant **Microphone** permission.
3. In Termux:
   ```bash
   pkg update && pkg upgrade
   pkg install python ffmpeg termux-api unzip
   pkg install espeak            # optional offline voice
   pip install flask requests gTTS
   termux-setup-storage          # lets Termux read ~/storage/downloads
   ```
4. Android Settings → Apps → Termux → Battery → **Unrestricted** (disable battery optimisation).

## 4. Deploy / update the app

```bash
# on the phone, after downloading focusbuddy.zip to Downloads
cd ~ && unzip -o ~/storage/downloads/focusbuddy.zip
cd ~/focusbuddy/server
```

Configure the AI (any OpenAI-compatible provider; several have free tiers):

```bash
export LLM_API_KEY="…"                                  # never commit this
export LLM_BASE_URL="https://api.groq.com/openai/v1"
export LLM_MODEL="<model id from your provider>"
```

Put these in `~/.bashrc` (Termux home, private to the app), or copy `.env.example` → `.env` and load it with `set -a; . ./.env; set +a`.

## 5. Run

```bash
termux-wake-lock        # stop Android from sleeping the CPU
python app.py
```

Start-up banner:

```
========================================================
 FocusBuddy server
 Dashboard:  http://192.168.43.1:5000
 ESP32 SERVER setting:  http://192.168.43.1:5000
 If the ESP32 can't connect, run `ifconfig` and use the inet
 address of the hotspot interface (wlan0 / ap0 / swlan0).
 AI: ON (<model>)
========================================================
```

The server binds `0.0.0.0:5000`, so it is reachable from every device on the hotspot.

## 6. Networking

```
            ┌──────────── Phone hotspot "FocusBuddyNet" (2.4 GHz, WPA2) ────────────┐
            │                                                                        │
  ESP32 ── DHCP client ──►  Phone (gateway, typically 192.168.43.1)  ◄── Laptop/phone browser
                                   │  Flask :5000
                                   └── mobile data ──► LLM API, Google TTS
```

- **Use the phone's own hotspot.** Venue/campus Wi-Fi commonly isolates clients, so the ESP32 can't reach the phone.
- **2.4 GHz only.** The ESP32 cannot join 5 GHz networks. Set the hotspot band accordingly.
- The phone is the gateway, so its IP on the hotspot is stable across restarts on most phones (often `192.168.43.1`; some vendors use other ranges, so check the banner or `ifconfig` for `wlan0` / `ap0` / `swlan0`).
- The firmware's `SERVER` must be the full URL including scheme and port, e.g. `http://192.168.43.1:5000`.
- **iPhone note:** any phone can provide the hotspot, but the server itself needs Android + Termux. With an iPhone hotspot, run the server on an Android phone (or a laptop for development) that joins the same hotspot, and use that device's IP in `SERVER`.

## 7. Power and lifecycle

| Concern | Handling |
|---|---|
| Screen off | `termux-wake-lock` holds a partial wake lock; Termux shows a persistent notification |
| Battery optimisation | Set Termux to **Unrestricted**, or Android may kill it |
| Long sessions | Keep the phone on a charger during long study days; the hotspot + CPU wake lock draw steady power |
| Restarts | State is rebuilt from SQLite on start (`init_db()` reloads the last 80 events) |
| Stop | `Ctrl+C`, then `termux-wake-unlock` |

## 8. Storage footprint

| Data | Location | Growth |
|---|---|---|
| Telemetry | `~/focusbuddy/server/focusbuddy.db` | ≤ 1 row / 10 s → ≤ 8,640 rows/day, well under 1 MB/day |
| Events | same DB | A few hundred rows/day typical |
| TTS audio | `~/focusbuddy/server/tts_cache/` | ~32 KB per second of speech; files older than 1 h deleted on each new TTS |

Backup: `cp ~/focusbuddy/server/focusbuddy.db ~/storage/downloads/focusbuddy-$(date +%F).db`

## 9. Security posture on the phone

| Aspect | Status |
|---|---|
| App sandbox | Termux runs as its own Android app user; files in `~` are private to it |
| Secrets | API keys live in Termux env / `~/.bashrc`, not in the repo (`.gitignore` covers `.env`) |
| Network exposure | Port 5000 on all interfaces. On a password-protected private hotspot only your devices can reach it. **Don't run the server while the phone is joined to public Wi-Fi.** |
| Authentication | None in MVP (trusted private network). Shared-token auth is on the roadmap |
| Outbound data | Only coaching prompts (aggregate stats + your questions) to your LLM provider, and spoken text to Google TTS. Run without a key + with espeak for fully local operation |

## 10. Troubleshooting on the phone

| Symptom | Fix |
|---|---|
| Server dies with the screen off | `termux-wake-lock`; battery → Unrestricted |
| `termux-speech-to-text` returns nothing | Open Termux:API once; grant mic; both apps from F-Droid |
| Device audio silent but dashboard works | `pkg install ffmpeg`; gTTS needs internet → install `espeak` |
| ESP32 "no AI" | Wrong `SERVER` (missing `http://` or port), wrong IP, or different network |
| Port in use | `PORT=5050 python app.py` and update firmware `SERVER` |
| Dashboard charts empty | Chart.js loads from a CDN; the viewing device needs internet (the hotspot phone's mobile data provides it) |

## 11. Development without a phone

The same `app.py` runs on Linux/macOS for development (`python3 app.py`). Termux-only features (`termux-speech-to-text`, `termux-tts-speak`) log a friendly error and the rest works. Use `simulate.py` as a fake ESP32 (see the `simulate-and-test` skill).
