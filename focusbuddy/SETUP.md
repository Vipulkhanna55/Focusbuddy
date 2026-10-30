# FocusBuddy – Setup Guide

An AI desk companion: it knows when you're at your desk, warns you when you sit too close to the screen, turns your lamp on when the desk is dark, runs a Pomodoro timer that pauses when you leave, and talks to you through a small speaker using an AI running on your phone.

```
ESP32 (sensors, lamp relay, OLED, speaker)  <-- Wi-Fi -->  Phone server in Termux (AI, voice, database, dashboard)
```

---

## 1. Parts

| Part | Notes |
|---|---|
| ESP32 DevKit V1 (ESP-WROOM-32) | The device brain |
| MAX98357A I2S amplifier | Drives the speaker |
| Small speaker, 4Ω or 8Ω, 0.5–3W | Salvage from an old toy, laptop or phone, or buy one for ₹30–50 |
| HC-SR04 ultrasonic distance sensor | Presence + screen distance |
| 2 × light sensor modules (LDR, with AO pin) | Desk light + window daylight |
| 0.96" OLED (SSD1306, I2C, 4 pins) | Timer and status |
| 5V 1-channel relay module | Switches the lamp |
| Piezo buzzer | Alerts |
| USB LED lamp | Safe low-voltage lamp for the relay. **Do not switch 230V mains.** |
| 1kΩ and 2kΩ resistors | Voltage divider for the HC-SR04 echo pin |
| Breadboard(s), jumper wires, phone (server), power bank or USB charger | |

The Arduino Uno isn't needed.

---

## 2. Wiring

ESP32 pin labels: "VIN" is 5V when powered over USB, "3V3" is 3.3V.

| Part | Part pin | ESP32 |
|---|---|---|
| **MAX98357A** | VIN | VIN (5V) |
| | GND | GND |
| | BCLK | GPIO 26 |
| | LRC | GPIO 25 |
| | DIN | GPIO 33 |
| | SD, GAIN | leave unconnected |
| | + / − (output) | speaker wires |
| **OLED** | VCC | 3V3 |
| | GND | GND |
| | SDA | GPIO 21 |
| | SCL | GPIO 22 |
| **HC-SR04** | VCC | VIN (5V) |
| | GND | GND |
| | TRIG | GPIO 5 |
| | ECHO | GPIO 18 **through a divider** (see below) |
| **Desk light sensor** | VCC / GND / AO | 3V3 / GND / GPIO 34 |
| **Window light sensor** | VCC / GND / AO | 3V3 / GND / GPIO 35 |
| **Relay module** | VCC / GND / IN | VIN (5V) / GND / GPIO 23 |
| **Buzzer** | + / − | GPIO 19 / GND |
| **Touch "Ask AI" button** | a bare wire or coin | GPIO 4 |

**HC-SR04 echo divider** (its echo is 5V, the ESP32 takes 3.3V):
`ECHO → 1kΩ → GPIO 18`, and `GPIO 18 → 2kΩ → GND`.

**Lamp through the relay:** cut the USB LED lamp's cable, find the red (+5V) wire, and connect one cut end to relay **COM** and the other to relay **NO**. Black wire stays joined. Plug the lamp into any USB charger.

**Placement:**
- HC-SR04 at the base or top of your screen, facing you.
- Desk light sensor flat on the desk where the lamp shines.
- Window light sensor pointing at the window (that's what lets the lamp switch off in daylight).

---

## 3. Flash the ESP32

1. Install **Arduino IDE 2**.
2. *File → Preferences → Additional boards manager URLs*, add:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. *Tools → Board → Boards Manager*: install **esp32 by Espressif** (version 3.x).
4. *Library Manager*: install **Adafruit SSD1306** (accept Adafruit GFX too) and **ArduinoJson** (7.x).
5. If the board isn't detected, install the USB driver for its chip (CP2102 or CH340, printed on the board).
6. Open `esp32/focusbuddy_esp32/focusbuddy_esp32.ino` and edit the top:
   - `WIFI_SSID`, `WIFI_PASS`: your phone hotspot.
   - `SERVER`: the address the phone server prints when it starts (step 4).
7. *Tools → Board → ESP32 Dev Module*, pick the port, **Upload**. If it hangs at "Connecting...", hold the **BOOT** button until it starts.

The device works on its own even without the phone (presence, lamp, timer, buzzer, OLED). The phone adds AI, voice and the dashboard.

### Calibrate (5 minutes)
Open *Serial Monitor* at **115200**. Every second it prints distance, light % and touch value.
- **Light:** cover the desk sensor with your hand. Desk % should drop. If it rises, set `LIGHT_INVERT = false`.
- Note desk % with the room lamp off vs on, and set `DESK_DARK_PCT` between them. Do the same for the window sensor and `WINDOW_BRIGHT_PCT`.
- **Distance:** sit normally and note the cm. Set `PRESENT_CM` about 30 cm beyond that; `CLOSE_CM` stays around 45.
- **Relay:** if the lamp is on when it should be off, flip `RELAY_ACTIVE_LOW`.
- **Buzzer:** if it clicks instead of beeping, set `BUZZER_ACTIVE = true`.
- **OLED blank:** change `0x3C` to `0x3D` in `setup()`.

---

## 4. Phone server (Termux)

Install **Termux** and **Termux:API** from the same source (F-Droid recommended; the Play Store Termux is outdated). Open Termux:API once and grant microphone permission.

```bash
pkg update && pkg upgrade
pkg install python ffmpeg termux-api unzip
pkg install espeak          # optional: offline backup voice
pip install flask requests gTTS
termux-setup-storage        # lets Termux see your Downloads folder
```

Copy the project to the phone (e.g. download `focusbuddy.zip` to Downloads), then:

```bash
cd ~ && unzip ~/storage/downloads/focusbuddy.zip
cd ~/focusbuddy/server
```

### AI key
Any OpenAI-compatible provider works (Groq, OpenRouter, Google Gemini's OpenAI-compatible endpoint, and others). Several have free tiers. Pick a model name from your provider's model list.

```bash
export LLM_API_KEY="your-key"
export LLM_BASE_URL="https://api.groq.com/openai/v1"   # or your provider's base URL
export LLM_MODEL="model-name-from-your-provider"
```

Put those three lines in `~/.bashrc` so you don't retype them.

### Run
```bash
termux-wake-lock            # stops Android from sleeping the server
python app.py
```

It prints the dashboard address, e.g. `http://192.168.43.1:5000`. Put that same address in the ESP32 `SERVER` setting.

Without an API key everything still runs, using built-in messages instead of AI.

### Networking (important for the venue)
Hackathon Wi-Fi often blocks devices from talking to each other. Use the **phone's hotspot**:
- Turn on the hotspot on the server phone.
- ESP32 and your laptop join that hotspot.
- Open the dashboard on the laptop or on the phone itself.

If the printed address doesn't work, run `ifconfig` in Termux and use the `inet` address of the hotspot interface (`wlan0`, `ap0` or `swlan0`).

### Test without hardware
In a second Termux session (swipe from the left edge → New session):
```bash
cd ~/focusbuddy/server && python simulate.py
```
A fake device sits down, focuses, leans too close and takes a break, so you can check the dashboard and AI.

---

## 5. How it works

| Feature | Sensors | What happens |
|---|---|---|
| Presence | HC-SR04 | Closer than 100 cm for 2 s = at desk; away for 10 s = left |
| Smart Pomodoro | HC-SR04 + timer | Starts when you sit down, pauses when you leave, beeps and the AI suggests a break activity |
| Posture / eye strain | HC-SR04 | Closer than 45 cm for 8 s = beep + spoken AI nudge |
| Smart lamp | 2 light sensors + relay | Desk dark and you're there = lamp on. Window daylight bright, or you're gone 60 s = lamp off. Two sensors stop it flickering, because once the lamp is on the desk sensor sees the lamp itself |
| Voice questions | Touch wire / dashboard | Phone mic listens, the LLM answers, the answer plays on the device speaker |
| Daily AI report | Database | LLM writes a summary and two tips from the day's real data |
| Dashboard | All | Live stats, charts, controls and activity log |

---

## 6. Demo script (about 3 minutes)

1. Dashboard → **Demo 2 / 1 min**. Explain the idea in one sentence while it shows "AWAY".
2. **Sit down** → timer starts, FocusBuddy greets you through the speaker.
3. **Lean close** to the sensor for 8 s → beep, OLED warning, spoken nudge. The distance chart dips below the red line.
4. **Cover the desk light sensor** → lamp turns on. **Shine a phone torch at the window sensor** → lamp turns off after 10 s.
5. **Stand up and walk away** → timer shows PAUSED. Come back → it resumes.
6. **Touch the wire** and ask the phone "How can I study better after lunch?" → spoken answer.
7. Wait for the 2-minute session to end → AI suggests a break activity.
8. Dashboard → **Generate and speak** the daily report.

Pitch line: *"Students lose hours to distraction and screen strain without noticing. FocusBuddy measures it with real sensors, and AI turns that data into coaching, automatically."*

---

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| OLED says "no AI" | Wrong `SERVER` address, server not running, or ESP32 and phone on different networks |
| No sound | Check MAX98357A wiring (BCLK 26, LRC 25, DIN 33) and VIN on 5V. Use dashboard → Say to test |
| Voice works on dashboard but not device | ffmpeg missing in Termux (`pkg install ffmpeg`) or gTTS has no internet; install espeak as backup |
| Distance always 999 | TRIG/ECHO swapped, HC-SR04 not on 5V, or divider wrong |
| Lamp flickers | Window sensor is seeing the lamp; point it away from the lamp |
| Upload fails | Hold BOOT during "Connecting...", use a data USB cable |
| Server stops when the screen is off | Run `termux-wake-lock` and disable battery optimisation for Termux |
