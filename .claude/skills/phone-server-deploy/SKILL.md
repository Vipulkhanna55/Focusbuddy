---
name: phone-server-deploy
description: Use when installing, updating, running or troubleshooting the FocusBuddy server on the Android phone (Termux, Termux:API, hotspot networking, wake-lock, battery optimisation).
---

# Deploy the server to the phone (Termux)

The production host is an **Android phone** running **Termux** + **Termux:API** (both from F-Droid, same source). Full background: `docs/MOBILE_HOSTING.md`.

## One-time setup (user runs these on the phone)

```bash
pkg update && pkg upgrade
pkg install python ffmpeg termux-api unzip
pkg install espeak                 # optional offline voice fallback
pip install flask requests gTTS
termux-setup-storage               # access ~/storage/downloads
```

Open the **Termux:API** app once and grant **microphone** permission (needed for `termux-speech-to-text`).

## Ship a new build

1. Re-zip the canonical tree so the phone gets the latest code:
   `cd <repo> && zip -r focusbuddy.zip focusbuddy -x '*/__pycache__/*' '*/focusbuddy.db' '*/tts_cache/*'`
2. Transfer to the phone's Downloads (USB, cloud drive, or `adb push focusbuddy.zip /sdcard/Download/` — `adb` is an ask-permission).
3. On the phone:
   ```bash
   cd ~ && unzip -o ~/storage/downloads/focusbuddy.zip
   cd ~/focusbuddy/server
   ```
   `unzip -o` keeps the existing `focusbuddy.db` because the zip excludes it.

## Run

```bash
set -a; . ./.env; set +a       # if the user keeps keys in a local .env (never commit it)
termux-wake-lock               # keep the CPU awake with the screen off
python app.py
```

The banner prints `Dashboard: http://<ip>:5000` and the value to put in the firmware `SERVER`.

## Networking rules

- Use the **phone's own hotspot**; venue Wi-Fi usually blocks device-to-device traffic.
- ESP32 is 2.4 GHz only — set the hotspot band to 2.4 GHz.
- If the printed IP is wrong, run `ifconfig` and use the `inet` of `wlan0` / `ap0` / `swlan0`.

## Guardrails

- Never ask the user to paste their API key into chat. They set it in Termux themselves.
- Never delete `focusbuddy.db` on the phone — it is the user's history.
- Disable battery optimisation for Termux (Android Settings → Apps → Termux → Battery → Unrestricted).

## Health check

```bash
curl -s http://127.0.0.1:5000/api/state | head -c 300
```
`online: true` means the ESP32 posted within the last 8 s; `ai_ready: true` means key + model are set.
