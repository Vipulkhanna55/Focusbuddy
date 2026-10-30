---
name: esp32-firmware
description: Use when editing, compiling or flashing the FocusBuddy ESP32 firmware (focusbuddy_esp32.ino) — pins, sensors, relay, OLED, I2S speaker, Wi-Fi, Pomodoro or presence logic.
---

# ESP32 firmware

Firmware: `focusbuddy/esp32/focusbuddy_esp32/focusbuddy_esp32.ino` (canonical). Board **ESP32 Dev Module**, core **Arduino-ESP32 3.x**, libraries **Adafruit SSD1306** (+ GFX) and **ArduinoJson 7.x**.

## Mental model

- `loop()` is a cooperative scheduler built on `millis()`:
  distance every 150 ms (median of 5) · light every 500 ms (avg of 8) · OLED every 250 ms · server sync every 2 s · serial debug every 1 s.
- State machines, each an `update*()` function: `updatePresence` → `updateTooClose` → `updateLamp` → `updatePomo` → `checkTouch`.
- Device→server events go through `pushEvent()` into a fixed 8-slot queue, cleared only after a successful POST.
- Server→device commands arrive in the `/api/telemetry` response (see `docs/API.md`).

## Before you change anything

1. All tunables belong in the `USER CONFIG` block at the top. Don't scatter magic numbers.
2. Committed `WIFI_SSID` / `WIFI_PASS` / `SERVER` must be placeholders. `SERVER` must include the scheme and port, e.g. `http://192.168.43.1:5000`.
3. Pin changes → update the wiring table in `focusbuddy/SETUP.md`. Avoid strapping/input-only surprises: GPIO 34/35 are input-only (used for LDRs), GPIO 4 is touch-capable.

## Safety rules (hardware)

- Relay must be OFF at boot: keep `digitalWrite(PIN_RELAY, OFF_LEVEL)` **before** `pinMode(PIN_RELAY, OUTPUT)`.
- Lamp is a 5 V USB lamp. Never introduce mains switching.
- HC-SR04 ECHO is 5 V → 1 kΩ/2 kΩ divider into GPIO 18. Never wire it direct.
- Don't add long blocking `delay()` calls. `beep()` and `playTTS()` already block briefly; don't make that worse.

## Compile (always) / flash (only with user OK)

```bash
arduino-cli core install esp32:esp32
arduino-cli lib install "Adafruit SSD1306" "ArduinoJson"
arduino-cli compile --fqbn esp32:esp32:esp32 focusbuddy/esp32/focusbuddy_esp32
# Upload is an "ask" permission — confirm port with the user first:
arduino-cli upload  --fqbn esp32:esp32:esp32 -p /dev/ttyUSB0 focusbuddy/esp32/focusbuddy_esp32
arduino-cli monitor -p /dev/ttyUSB0 -c baudrate=115200
```

If upload hangs at "Connecting…", the user must hold **BOOT**.

## Verify

- Serial monitor prints `dist=… desk=…% window=…% present=… lamp=… <pomo> touch=…` every second.
- OLED header shows `AI on` once the phone server answers 200.
- If you touched the telemetry JSON, run the `telemetry-contract` skill.
