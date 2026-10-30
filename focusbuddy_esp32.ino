/*
  FocusBuddy - ESP32 firmware
  ---------------------------------------------------------------
  Board   : "ESP32 Dev Module" (ESP32 DevKit V1 / ESP-WROOM-32)
  Core    : Arduino-ESP32 by Espressif, version 3.x
  Libraries (Library Manager):
            - Adafruit SSD1306   (also installs Adafruit GFX)
            - ArduinoJson        (version 7.x)

  What it does
    - HC-SR04 distance sensor: detects if you are at the desk and
      warns when you sit too close to the screen.
    - Two light sensors: desk light + window daylight. Turns the lamp
      on through the relay when the desk is dark, off when you leave
      or daylight is enough.
    - Pomodoro timer that only counts while you are actually present.
    - 0.96" OLED shows timer, status, distance and light.
    - Buzzer for alerts.
    - Every 2 s sends data to the phone server and receives commands.
    - Plays AI voice replies from the phone through MAX98357A + speaker.
    - Touch a wire on GPIO4 to ask the AI a question (phone mic listens).
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP_I2S.h>

// ===================== USER CONFIG =====================
const char* WIFI_SSID = "Vipul's iPhone";              // your phone hotspot name
const char* WIFI_PASS = "matkroconnect";                  // hotspot password
const char* SERVER    = "http://192.168.0.7:5000";   // phone server address (printed when server starts)

// Behaviour (tune during calibration)
const int   PRESENT_CM          = 100;    // closer than this = someone is at the desk
const int   CLOSE_CM            = 45;     // closer than this = too close to the screen
const unsigned long CLOSE_HOLD_MS     = 8000;   // must stay too close this long before alert
const unsigned long CLOSE_COOLDOWN_MS = 60000;  // min gap between too-close alerts
const int   DESK_DARK_PCT       = 35;     // desk brightness below this = too dark
const int   WINDOW_BRIGHT_PCT   = 70;     // daylight above this = lamp not needed
const unsigned long WINDOW_OFF_HOLD_MS = 10000; // daylight must stay bright this long to switch lamp off
const unsigned long LAMP_OFF_DELAY_MS  = 60000; // lamp turns off this long after you leave
const bool  AUTO_START_FOCUS    = true;   // start a focus session when you sit down
const int   VOLUME_PCT          = 70;     // speaker volume 0-100

// Hardware options
const bool RELAY_ACTIVE_LOW = true;   // most blue relay modules switch ON when IN is LOW
const bool LIGHT_INVERT     = true;   // most LDR modules read HIGHER in the dark; flip if % goes the wrong way
const bool BUZZER_ACTIVE    = false;  // true if your buzzer beeps on its own when given 3.3V
const bool ENABLE_TOUCH     = true;   // a bare wire / coin on GPIO4 acts as "Ask AI" button

// Pins
#define PIN_I2S_BCLK  26
#define PIN_I2S_LRC   25
#define PIN_I2S_DIN   33
#define PIN_SDA       21
#define PIN_SCL       22
#define PIN_TRIG      5
#define PIN_ECHO      18   // through a voltage divider (HC-SR04 echo is 5V)
#define PIN_LDR_DESK  34
#define PIN_LDR_WIN   35
#define PIN_RELAY     23
#define PIN_BUZZER    19
#define PIN_TOUCH     4
// =======================================================

Adafruit_SSD1306 display(128, 64, &Wire, -1);
I2SClass i2s;

enum Pomo { P_IDLE, P_FOCUS, P_BREAK };
enum LampMode { L_AUTO, L_ON, L_OFF };

// Sensor values
float distBuf[5] = {999, 999, 999, 999, 999};
int   distIdx = 0;
float dist = 999;
int   deskPct = 0, winPct = 0;

// State
bool present = false;
unsigned long presentCandidateSince = 0, awayCandidateSince = 0, awaySince = 0;
unsigned long closeSince = 0, lastCloseAlert = 0;
bool closeFired = false;
int  tooCloseCount = 0;

bool lampOn = false;
LampMode lampMode = L_AUTO;
unsigned long winBrightSince = 0;

Pomo pomo = P_IDLE;
long remainingMs = 0;
int  focusMin = 25, breakMin = 5;
unsigned long focusMsToday = 0;
int  sessionsDone = 0;
bool autoStartArmed = true;   // disarmed by a manual Stop, re-armed when you leave the desk

// Events to send to the server
String events[8];
int evCount = 0;

// Server / display
bool serverOk = false;
String oledMsg = "";
unsigned long oledMsgUntil = 0;
String pendingSay = "";
int touchBase = 0;
unsigned long lastTouch = 0;

unsigned long lastLoop = 0, lastDist = 0, lastLight = 0, lastDraw = 0, lastSync = 0, lastDebug = 0;

// ---------------------------------------------------------------
void pushEvent(const char* e) {
  if (evCount < 8) events[evCount++] = e;
  Serial.printf("[event] %s\n", e);
}

void showMessage(const String& m, unsigned long ms = 6000) {
  oledMsg = m;
  oledMsgUntil = millis() + ms;
}

void beep(int times) {
  for (int i = 0; i < times; i++) {
    if (BUZZER_ACTIVE) {
      digitalWrite(PIN_BUZZER, HIGH); delay(120); digitalWrite(PIN_BUZZER, LOW);
    } else {
      tone(PIN_BUZZER, 2200, 120); delay(120); noTone(PIN_BUZZER);
    }
    delay(90);
  }
}

void setLamp(bool on) {
  lampOn = on;
  digitalWrite(PIN_RELAY, (on ^ RELAY_ACTIVE_LOW) ? HIGH : LOW);
}

float readDistanceCm() {
  digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long d = pulseIn(PIN_ECHO, HIGH, 25000UL);  // ~4 m max
  if (d == 0) return 999;
  return d * 0.0343f / 2.0f;
}

float medianDist() {
  float t[5];
  memcpy(t, distBuf, sizeof(t));
  for (int i = 0; i < 4; i++)
    for (int j = i + 1; j < 5; j++)
      if (t[j] < t[i]) { float x = t[i]; t[i] = t[j]; t[j] = x; }
  return t[2];
}

int readLightPct(int pin) {
  long s = 0;
  for (int i = 0; i < 8; i++) s += analogRead(pin);
  int pct = (int)((s / 8) * 100L / 4095L);
  return LIGHT_INVERT ? 100 - pct : pct;
}

const char* pomoName() {
  return pomo == P_FOCUS ? "focus" : pomo == P_BREAK ? "break" : "idle";
}

const char* lampModeName() {
  return lampMode == L_ON ? "on" : lampMode == L_OFF ? "off" : "auto";
}

const char* statusLabel() {
  if (pomo == P_FOCUS) return present ? "FOCUS" : "PAUSED";
  if (pomo == P_BREAK) return "BREAK";
  return present ? "READY" : "AWAY";
}

void startFocus() {
  pomo = P_FOCUS;
  remainingMs = (long)focusMin * 60000L;
  pushEvent("focus_start");
}

// ---------------------------------------------------------------
void updatePresence(unsigned long now) {
  bool nearNow = dist < PRESENT_CM;
  if (!present) {
    if (nearNow) {
      if (!presentCandidateSince) presentCandidateSince = now;
      if (now - presentCandidateSince > 2000) {
        present = true;
        awayCandidateSince = 0;
        pushEvent("sit_down");
      }
    } else presentCandidateSince = 0;
  } else {
    if (!nearNow) {
      if (!awayCandidateSince) awayCandidateSince = now;
      if (now - awayCandidateSince > 10000) {
        present = false;
        presentCandidateSince = 0;
        awaySince = now;
        autoStartArmed = true;
        pushEvent("left_desk");
      }
    } else awayCandidateSince = 0;
  }
}

void updateTooClose(unsigned long now) {
  if (present && dist < CLOSE_CM) {
    if (!closeSince) closeSince = now;
    if (!closeFired && now - closeSince > CLOSE_HOLD_MS &&
        (lastCloseAlert == 0 || now - lastCloseAlert > CLOSE_COOLDOWN_MS)) {
      closeFired = true;
      lastCloseAlert = now;
      tooCloseCount++;
      showMessage("Too close! Sit back a little.");
      beep(2);
      pushEvent("too_close");
    }
  } else if (dist > CLOSE_CM + 5) {
    closeSince = 0;
    closeFired = false;
  }
}

void updateLamp(unsigned long now) {
  bool want = lampOn;
  if (lampMode == L_ON) want = true;
  else if (lampMode == L_OFF) want = false;
  else {
    if (!lampOn) {
      // Desk sensor decides when lamp is off: dark desk + someone there + not bright daylight
      if (present && deskPct < DESK_DARK_PCT && winPct < WINDOW_BRIGHT_PCT) want = true;
    } else {
      // Once on, the desk sensor sees the lamp itself, so the window sensor decides
      if (!present && awaySince && now - awaySince > LAMP_OFF_DELAY_MS) want = false;
      if (winPct > WINDOW_BRIGHT_PCT) {
        if (!winBrightSince) winBrightSince = now;
        if (now - winBrightSince > WINDOW_OFF_HOLD_MS) want = false;
      } else winBrightSince = 0;
    }
  }
  if (want != lampOn) {
    setLamp(want);
    pushEvent(want ? "lamp_on" : "lamp_off");
  }
}

void updatePomo(unsigned long dt) {
  if (pomo == P_IDLE) {
    if (present && AUTO_START_FOCUS && autoStartArmed) startFocus();
    return;
  }
  if (pomo == P_FOCUS) {
    if (present) {             // timer pauses while you are away
      remainingMs -= (long)dt;
      focusMsToday += dt;
    }
    if (remainingMs <= 0) {
      pomo = P_BREAK;
      remainingMs = (long)breakMin * 60000L;
      sessionsDone++;
      showMessage("Session done! Take a break.");
      beep(3);
      pushEvent("break_start");
    }
  } else if (pomo == P_BREAK) {
    remainingMs -= (long)dt;
    if (remainingMs <= 0) {
      beep(1);
      pushEvent("break_end");
      if (present) startFocus();
      else pomo = P_IDLE;
    }
  }
}

void checkTouch(unsigned long now) {
  if (!ENABLE_TOUCH || touchBase == 0) return;
  int v = touchRead(PIN_TOUCH);
  if (v < touchBase * 6 / 10 && now - lastTouch > 4000) {
    lastTouch = now;
    beep(1);
    showMessage("Listening... speak to the phone", 8000);
    pushEvent("ask");
  }
}

// ---------------------------------------------------------------
void drawOLED() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print(statusLabel());
  display.setCursor(80, 0);
  if (WiFi.status() != WL_CONNECTED) display.print("no WiFi");
  else display.print(serverOk ? "AI on" : "no AI");
  display.drawFastHLine(0, 10, 128, SSD1306_WHITE);

  if (oledMsg.length() && millis() < oledMsgUntil) {
    display.setTextWrap(true);
    display.setCursor(0, 14);
    display.print(oledMsg);
  } else {
    display.setTextSize(3);
    display.setCursor(20, 16);
    if (pomo == P_IDLE) display.print("--:--");
    else {
      long s = max(0L, remainingMs / 1000);
      display.printf("%02ld:%02ld", s / 60, s % 60);
    }
    display.setTextSize(1);
    display.setCursor(0, 46);
    if (dist >= 999) display.print("Dist: --");
    else display.printf("Dist:%3dcm", (int)dist);
    display.setCursor(74, 46);
    display.printf("Lamp:%s", lampOn ? "ON" : "off");
    display.setCursor(0, 56);
    display.printf("Desk:%2d%%  Window:%2d%%", deskPct, winPct);
  }
  display.display();
}

// ---------------------------------------------------------------
void playTTS(const String& id) {
  showMessage("Speaking...", 1500);
  drawOLED();
  HTTPClient http;
  http.setTimeout(10000);
  http.begin(String(SERVER) + "/api/tts/" + id + ".pcm");
  int code = http.GET();
  if (code == 200) {
    int total = http.getSize();
    auto* s = http.getStreamPtr();
    s->setTimeout(3000);
    static int16_t sbuf[512];
    int left = total > 0 ? total : (1 << 30);
    while (left > 0 && (http.connected() || s->available())) {
      int want = min(left, (int)sizeof(sbuf));
      int n = s->readBytes((uint8_t*)sbuf, want);
      if (n <= 0) break;
      int samples = n / 2;
      for (int i = 0; i < samples; i++) sbuf[i] = (int16_t)((int32_t)sbuf[i] * VOLUME_PCT / 100);
      i2s.write((uint8_t*)sbuf, samples * 2);
      left -= n;
    }
  } else {
    Serial.printf("[tts] HTTP %d\n", code);
  }
  http.end();
}

void syncServer() {
  if (WiFi.status() != WL_CONNECTED) { serverOk = false; return; }

  JsonDocument doc;
  doc["present"]         = present;
  doc["distance_cm"]     = (int)dist;
  doc["desk_light"]      = deskPct;
  doc["window_light"]    = winPct;
  doc["lamp"]            = lampOn;
  doc["lamp_mode"]       = lampModeName();
  doc["pomo"]            = pomoName();
  doc["remaining_s"]     = max(0L, remainingMs / 1000);
  doc["focus_s_today"]   = focusMsToday / 1000;
  doc["sessions"]        = sessionsDone;
  doc["too_close_count"] = tooCloseCount;
  JsonArray ev = doc["events"].to<JsonArray>();
  for (int i = 0; i < evCount; i++) ev.add(events[i]);
  String body;
  serializeJson(doc, body);

  HTTPClient http;
  http.setTimeout(1500);
  http.begin(String(SERVER) + "/api/telemetry");
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  serverOk = (code == 200);

  if (code == 200) {
    evCount = 0;
    JsonDocument r;
    if (!deserializeJson(r, http.getString())) {
      const char* lm = r["lamp_mode"] | "auto";
      lampMode = !strcmp(lm, "on") ? L_ON : !strcmp(lm, "off") ? L_OFF : L_AUTO;
      focusMin = r["focus_min"] | 25;
      breakMin = r["break_min"] | 5;

      const char* pc = r["pomo"] | "";
      if (!strcmp(pc, "start")) startFocus();
      else if (!strcmp(pc, "stop")) { pomo = P_IDLE; remainingMs = 0; autoStartArmed = false; }

      int bz = r["buzz"] | 0;
      if (bz > 0) beep(min(bz, 5));

      const char* msg = r["oled"] | "";
      if (strlen(msg)) showMessage(msg, 8000);

      const char* say = r["say"] | "";
      if (strlen(say)) pendingSay = say;
    }
  }
  http.end();

  if (pendingSay.length()) {
    String id = pendingSay;
    pendingSay = "";
    playTTS(id);
  }
}

// ---------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(200);

  digitalWrite(PIN_RELAY, RELAY_ACTIVE_LOW ? HIGH : LOW);  // lamp off before enabling output
  pinMode(PIN_RELAY, OUTPUT);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  analogReadResolution(12);

  Wire.begin(PIN_SDA, PIN_SCL);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED not found at 0x3C (try 0x3D)");
  }
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(2);
  display.setCursor(4, 8);
  display.print("FocusBuddy");
  display.setTextSize(1);
  display.setCursor(4, 40);
  display.print("Connecting WiFi...");
  display.display();

  i2s.setPins(PIN_I2S_BCLK, PIN_I2S_LRC, PIN_I2S_DIN);
  if (!i2s.begin(I2S_MODE_STD, 16000, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
    Serial.println("I2S init failed");
  }

  if (ENABLE_TOUCH) {
    long s = 0;
    for (int i = 0; i < 10; i++) { s += touchRead(PIN_TOUCH); delay(10); }
    touchBase = s / 10;
    Serial.printf("Touch baseline: %d\n", touchBase);
  }

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) delay(250);
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("WiFi OK, IP %s\n", WiFi.localIP().toString().c_str());
    showMessage("WiFi OK\n" + WiFi.localIP().toString(), 3000);
  } else {
    Serial.println("WiFi not connected yet; working offline and retrying");
    showMessage("WiFi failed - offline mode", 3000);
  }

  beep(1);
  lastLoop = millis();
}

void loop() {
  unsigned long now = millis();
  unsigned long dt = now - lastLoop;
  lastLoop = now;

  if (now - lastDist >= 150) {
    lastDist = now;
    distBuf[(distIdx++) % 5] = readDistanceCm();
    dist = medianDist();
  }
  if (now - lastLight >= 500) {
    lastLight = now;
    deskPct = readLightPct(PIN_LDR_DESK);
    winPct  = readLightPct(PIN_LDR_WIN);
  }

  updatePresence(now);
  updateTooClose(now);
  updateLamp(now);
  updatePomo(dt);
  checkTouch(now);

  if (now - lastDraw >= 250) { lastDraw = now; drawOLED(); }
  if (now - lastSync >= 2000) { lastSync = now; syncServer(); }

  if (now - lastDebug >= 1000) {   // calibration output for Serial Monitor
    lastDebug = now;
    Serial.printf("dist=%dcm desk=%d%% window=%d%% present=%d lamp=%d %s touch=%d\n",
                  (int)dist, deskPct, winPct, present, lampOn, pomoName(),
                  ENABLE_TOUCH ? touchRead(PIN_TOUCH) : -1);
  }
  delay(5);
}
