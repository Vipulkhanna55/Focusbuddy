---
name: sensor-calibration
description: Use when FocusBuddy misdetects presence, alerts at the wrong distance, the lamp flickers or switches the wrong way, the buzzer clicks, or the OLED is blank — guides threshold and polarity tuning from serial output.
---

# Sensor calibration

All tunables are in the firmware `USER CONFIG` block. Calibrate from the **Serial Monitor at 115200**, which prints once per second:

```
dist=62cm desk=41% window=18% present=1 lamp=0 focus touch=58
```

Ask the user to read values aloud or paste the log; never guess thresholds.

## Procedure

| Symptom / step | Measure | Set |
|---|---|---|
| Light direction | Cover desk sensor with a hand — `desk%` must **drop** | If it rises: `LIGHT_INVERT = false` |
| Desk darkness | `desk%` with room light off vs on | `DESK_DARK_PCT` between the two (default 35) |
| Daylight cut-off | `window%` at night vs bright daylight / phone torch | `WINDOW_BRIGHT_PCT` between them (default 70) |
| Presence | `dist` while sitting normally | `PRESENT_CM` ≈ normal + 30 cm (default 100) |
| Too close | Keep `CLOSE_CM` ≈ 45 cm (arm's length guideline); hold 8 s, cooldown 60 s | `CLOSE_CM`, `CLOSE_HOLD_MS`, `CLOSE_COOLDOWN_MS` |
| Relay inverted | Lamp on when it should be off | Flip `RELAY_ACTIVE_LOW` |
| 5 V relay won't release | Stays on even when "off" | `RELAY_FLOAT_OFF = true` (latest firmware) |
| Buzzer clicks | Active vs passive buzzer | `BUZZER_ACTIVE = true` for active buzzers |
| OLED blank | I2C address | `0x3C` → `0x3D` in `setup()` |
| Touch too sensitive | `touch=` idle vs touched | Trigger is < 60 % of the boot baseline; keep the wire short |

## Why two light sensors

Once the lamp is on, the desk sensor sees the lamp itself. So the **desk** sensor decides when to turn the lamp **on**, and the **window** sensor (pointed away from the lamp) decides when to turn it **off**. If the lamp flickers, the window sensor is seeing the lamp — re-aim it.

## Guardrails

- Never suggest powering the HC-SR04 ECHO line straight into a GPIO; the divider is mandatory.
- Never suggest replacing the USB lamp with a mains lamp.
- After changing thresholds, recompile (`esp32-firmware` skill) and re-run the demo steps from `hackathon-demo`.
