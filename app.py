#!/usr/bin/env python3
"""
FocusBuddy phone server  (Termux + Python)

- Receives sensor data from the ESP32 every 2 s and sends back commands.
- Logs everything to SQLite.
- Uses an LLM (any OpenAI-compatible API) to write short spoken coaching lines.
- Turns text into speech (gTTS, fallback espeak) and serves it to the ESP32 speaker.
- Listens to questions through the phone mic (Termux:API speech-to-text).
- Serves the live dashboard at http://<phone-ip>:5000

Environment variables:
  LLM_API_KEY   your API key (no key = friendly built-in messages, no AI)
  LLM_BASE_URL  OpenAI-compatible base URL, e.g. https://api.groq.com/openai/v1
  LLM_MODEL     a model name from your provider's model list
  TTS_TLD       gTTS accent, default "co.in" (Indian English)
  PORT          default 5000
"""
import os
import re
import time
import uuid
import random
import socket
import sqlite3
import datetime
import threading
import subprocess
from collections import deque

import requests
from flask import Flask, request, jsonify, send_file, send_from_directory, abort

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "focusbuddy.db")
TTS_DIR = os.path.join(BASE, "tts_cache")
os.makedirs(TTS_DIR, exist_ok=True)

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
TTS_TLD = os.getenv("TTS_TLD", "co.in")
PORT = int(os.getenv("PORT", "5000"))

app = Flask(__name__, static_folder=os.path.join(BASE, "static"))

state_lock = threading.Lock()
db_lock = threading.Lock()

latest = {}                 # last telemetry from the ESP32
last_seen = 0.0
last_logged = 0.0
recent = deque(maxlen=80)   # recent events for the dashboard
settings = {"lamp_mode": "auto", "focus_min": 25, "break_min": 5}
oneshot = {"say": None, "oled": None, "buzz": 0, "pomo": None}
last_spoken = 0.0
last_greet = 0.0

# --------------------------------------------------------------- database
def q(sql, args=(), fetch=False):
    with db_lock:
        c = sqlite3.connect(DB_PATH, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            cur = c.execute(sql, args)
            rows = cur.fetchall() if fetch else None
            c.commit()
            return rows
        finally:
            c.close()


def init_db():
    q("""CREATE TABLE IF NOT EXISTS telemetry(
            ts REAL, present INT, distance INT, desk INT, win INT, lamp INT,
            pomo TEXT, focus_s INT, sessions INT, too_close INT)""")
    q("CREATE TABLE IF NOT EXISTS events(ts REAL, type TEXT, text TEXT)")
    for r in q("SELECT ts, type, text FROM events ORDER BY ts DESC LIMIT 80", fetch=True)[::-1]:
        recent.appendleft({"ts": r["ts"], "type": r["type"], "text": r["text"]})


def log_event(kind, text=""):
    ts = time.time()
    q("INSERT INTO events VALUES(?,?,?)", (ts, kind, text))
    recent.appendleft({"ts": ts, "type": kind, "text": text})
    print(f"[{datetime.datetime.now():%H:%M:%S}] {kind}: {text}")


def today_start():
    return datetime.datetime.combine(datetime.date.today(), datetime.time.min).timestamp()


def device_online():
    return time.time() - last_seen < 8

# --------------------------------------------------------------- AI
SYSTEM = (
    "You are FocusBuddy, a warm, upbeat desk companion that helps a student study well "
    "and protect their eyes and posture. Your words are spoken aloud through a small speaker, "
    "so reply in plain spoken English with no emojis, lists or markdown. Keep it short."
)

EVENT_PROMPTS = {
    "too_close": "The user has been sitting closer than 45 cm to the screen for a while. "
                 "In one or two short sentences, kindly nudge them to sit back and mention why it helps.",
    "break_start": "A focus session just ended. In two short sentences, congratulate them briefly "
                   "and suggest one specific 5-minute break activity, like stretching, drinking water "
                   "or the 20-20-20 eye rule.",
    "break_end": "The break is over. In one short sentence, motivate them to start the next focus session.",
    "sit_down": "The user just sat down at the desk. Greet them in one short sentence and mention "
                "the time of day or their progress so far.",
}

FALLBACK = {
    "too_close": ["You're quite close to the screen. Sit back a little to rest your eyes.",
                  "Lean back a bit. Keeping an arm's length from the screen helps your eyes and neck."],
    "break_start": ["Great session! Stand up, stretch, and drink some water for five minutes.",
                    "Nice work. Look at something far away for twenty seconds and take a short walk."],
    "break_end": ["Break's over. Let's get back to it, you're doing great.",
                  "Ready for another round? Let's focus."],
    "sit_down": ["Welcome back! Let's have a focused session.",
                 "Hi there. Your timer is running, let's do this."],
    "ask": ["I can't reach my AI brain right now. Please check the API key on the server."],
}


def llm(prompt, max_tokens=120, system=SYSTEM):
    if not (LLM_API_KEY and LLM_MODEL):
        return None
    try:
        r = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.7,
            },
            timeout=25,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log_event("error", f"LLM call failed: {e}")
        return None


def context():
    with state_lock:
        d = dict(latest)
    return (
        f"Time now {datetime.datetime.now():%H:%M}. "
        f"Focused today: {int(d.get('focus_s_today', 0)) // 60} minutes across {d.get('sessions', 0)} sessions. "
        f"Too-close alerts today: {d.get('too_close_count', 0)}. "
        f"Distance from screen now: {d.get('distance_cm', 'unknown')} cm. "
        f"Desk light {d.get('desk_light', '?')}%, daylight {d.get('window_light', '?')}%. "
        f"Lamp {'on' if d.get('lamp') else 'off'}. Timer state: {d.get('pomo', 'idle')}."
    )


def clean(text):
    text = re.sub(r"[*#_`>\[\]]", "", text or "")
    return re.sub(r"\s+", " ", text).strip()

# --------------------------------------------------------------- speech
def cleanup_tts():
    cutoff = time.time() - 3600
    for f in os.listdir(TTS_DIR):
        p = os.path.join(TTS_DIR, f)
        try:
            if os.path.getmtime(p) < cutoff:
                os.remove(p)
        except OSError:
            pass


def make_tts(text):
    """Text -> 16 kHz, 16-bit, mono raw PCM file the ESP32 can play. Returns its id."""
    cleanup_tts()
    tid = uuid.uuid4().hex[:10]
    pcm = os.path.join(TTS_DIR, tid + ".pcm")
    try:
        from gtts import gTTS
        src = os.path.join(TTS_DIR, tid + ".mp3")
        gTTS(text=text, lang="en", tld=TTS_TLD).save(src)
    except Exception as e:
        log_event("error", f"gTTS failed ({e}), using espeak")
        src = os.path.join(TTS_DIR, tid + ".wav")
        subprocess.run(["espeak", "-w", src, text], check=True, timeout=30)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", src,
         "-ac", "1", "-ar", "16000", "-f", "s16le", pcm],
        check=True, timeout=60,
    )
    return tid


def phone_say(text):
    try:
        subprocess.Popen(["termux-tts-speak", text])
    except Exception as e:
        log_event("error", f"Phone speech failed: {e}")


def speak(text):
    """Say text through the ESP32 speaker (or the phone if the device is offline)."""
    global last_spoken
    text = clean(text)
    if not text:
        return
    last_spoken = time.time()
    log_event("ai", text)
    if device_online():
        try:
            tid = make_tts(text)
            with state_lock:
                oneshot["say"] = tid
                oneshot["oled"] = text[:84]
            return
        except Exception as e:
            log_event("error", f"TTS failed: {e}")
    phone_say(text)


def listen_phone():
    try:
        out = subprocess.run(["termux-speech-to-text"], capture_output=True,
                             text=True, timeout=40).stdout
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        return lines[-1] if lines else None
    except Exception as e:
        log_event("error", f"Speech-to-text failed: {e}")
        return None


def get_reply(question):
    prompt = (f"The user asks: {question}\nTheir current desk context: {context()}\n"
              "Answer helpfully in at most three short spoken sentences.")
    return llm(prompt, max_tokens=180) or random.choice(FALLBACK["ask"])


def handle_listen():
    with state_lock:
        oneshot["oled"] = "Listening... speak to the phone"
    question = listen_phone()
    if not question:
        with state_lock:
            oneshot["oled"] = "Sorry, I didn't catch that"
        return
    log_event("you", question)
    speak(get_reply(question))


def handle_event(ev):
    global last_greet
    now = time.time()
    if ev == "ask":
        handle_listen()
        return
    if ev not in EVENT_PROMPTS:
        return
    if ev == "sit_down":
        if now - last_greet < 600:
            return
        last_greet = now
    if ev != "break_start" and now - last_spoken < 15:
        return
    line = llm(EVENT_PROMPTS[ev] + "\nContext: " + context()) or random.choice(FALLBACK[ev])
    speak(line)

# --------------------------------------------------------------- routes
@app.get("/")
def dashboard():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/api/telemetry")
def telemetry():
    global last_seen, last_logged
    d = request.get_json(force=True, silent=True) or {}
    events = d.pop("events", []) or []
    now = time.time()
    with state_lock:
        latest.clear()
        latest.update(d)
        last_seen = now
    if now - last_logged >= 10:
        last_logged = now
        q("INSERT INTO telemetry VALUES(?,?,?,?,?,?,?,?,?,?)", (
            now, int(bool(d.get("present"))), int(d.get("distance_cm", 999)),
            int(d.get("desk_light", 0)), int(d.get("window_light", 0)),
            int(bool(d.get("lamp"))), str(d.get("pomo", "idle")),
            int(d.get("focus_s_today", 0)), int(d.get("sessions", 0)),
            int(d.get("too_close_count", 0))))
    for ev in events:
        log_event("device", str(ev))
        threading.Thread(target=handle_event, args=(str(ev),), daemon=True).start()

    with state_lock:
        resp = dict(settings)
        resp["say"] = oneshot["say"] or ""
        resp["oled"] = oneshot["oled"] or ""
        resp["buzz"] = oneshot["buzz"]
        resp["pomo"] = oneshot["pomo"] or ""
        oneshot.update(say=None, oled=None, buzz=0, pomo=None)
    return jsonify(resp)


@app.get("/api/tts/<tid>.pcm")
def tts_file(tid):
    if not re.fullmatch(r"[0-9a-f]{10}", tid):
        abort(404)
    path = os.path.join(TTS_DIR, tid + ".pcm")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="application/octet-stream")


@app.get("/api/state")
def api_state():
    now = time.time()
    rows = q("SELECT ts, distance, desk, win, present FROM telemetry WHERE ts >= ? ORDER BY ts",
             (now - 3600,), fetch=True)
    hourly = q("""SELECT CAST(strftime('%H', ts, 'unixepoch', 'localtime') AS INT) AS h,
                         SUM(present) AS n
                  FROM telemetry WHERE ts >= ? AND pomo = 'focus' GROUP BY h""",
               (today_start(),), fetch=True)
    with state_lock:
        data = dict(latest)
        s = dict(settings)
    return jsonify(
        online=device_online(),
        ai_ready=bool(LLM_API_KEY and LLM_MODEL),
        latest=data,
        settings=s,
        events=list(recent)[:40],
        series=[dict(r) for r in rows],
        hourly={int(r["h"]): round(r["n"] * 10 / 60, 1) for r in hourly},
    )


@app.post("/api/command")
def command():
    d = request.get_json(force=True, silent=True) or {}
    with state_lock:
        if d.get("lamp_mode") in ("auto", "on", "off"):
            settings["lamp_mode"] = d["lamp_mode"]
        for k in ("focus_min", "break_min"):
            if k in d:
                settings[k] = max(1, min(120, int(d[k])))
        if d.get("pomo") in ("start", "stop"):
            oneshot["pomo"] = d["pomo"]
        if d.get("buzz"):
            oneshot["buzz"] = int(d["buzz"])
        s = dict(settings)
    if d.get("say"):
        threading.Thread(target=speak, args=(str(d["say"])[:300],), daemon=True).start()
    return jsonify(ok=True, settings=s)


@app.post("/api/ask")
def ask():
    question = str((request.get_json(force=True, silent=True) or {}).get("question", "")).strip()
    if not question:
        return jsonify(error="empty question"), 400
    log_event("you", question)
    reply = clean(get_reply(question))
    threading.Thread(target=speak, args=(reply,), daemon=True).start()
    return jsonify(reply=reply)


@app.post("/api/listen")
def listen():
    threading.Thread(target=handle_listen, daemon=True).start()
    return jsonify(ok=True)


@app.post("/api/summary")
def summary():
    start = today_start()
    counts = {r["text"]: r["n"] for r in q(
        "SELECT text, COUNT(*) AS n FROM events WHERE ts >= ? AND type = 'device' GROUP BY text",
        (start,), fetch=True)}
    agg = q("SELECT AVG(desk) AS desk, AVG(win) AS win, SUM(present) AS pres, "
            "MAX(focus_s) AS focus_s, MAX(sessions) AS sessions FROM telemetry WHERE ts >= ?",
            (start,), fetch=True)[0]
    hourly = q("""SELECT CAST(strftime('%H', ts, 'unixepoch', 'localtime') AS INT) AS h, SUM(present) AS n
                  FROM telemetry WHERE ts >= ? AND pomo = 'focus' GROUP BY h ORDER BY n DESC LIMIT 1""",
               (start,), fetch=True)
    best_hour = f"{hourly[0]['h']}:00" if hourly else "not enough data"
    facts = (
        f"Focused minutes: {int(agg['focus_s'] or 0) // 60}. "
        f"Completed sessions: {agg['sessions'] or 0}. "
        f"Minutes at desk: {int((agg['pres'] or 0) * 10 / 60)}. "
        f"Too-close-to-screen alerts: {counts.get('too_close', 0)}. "
        f"Times left the desk: {counts.get('left_desk', 0)}. "
        f"Lamp switched on automatically: {counts.get('lamp_on', 0)} times. "
        f"Average desk light: {round(agg['desk'] or 0)}%. Average daylight: {round(agg['win'] or 0)}%. "
        f"Most focused hour: {best_hour}."
    )
    prompt = ("Write a short end-of-day focus report for the user in 3 to 4 sentences, "
              "then give exactly 2 practical tips for tomorrow, each starting with 'Tip:'. "
              "Plain text, no markdown. Use these facts: " + facts)
    text = llm(prompt, max_tokens=300,
               system="You are FocusBuddy, a friendly study coach. Be specific and encouraging.")
    if not text:
        text = "Today's numbers: " + facts + " Tip: keep an arm's length from your screen. Tip: take a break every 25 minutes."
    text = clean(text)
    log_event("summary", text)
    if (request.get_json(force=True, silent=True) or {}).get("speak"):
        first = " ".join(re.split(r"(?<=[.!?])\s+", text)[:2])
        threading.Thread(target=speak, args=(first,), daemon=True).start()
    return jsonify(summary=text, facts=facts)

# --------------------------------------------------------------- main
def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


if __name__ == "__main__":
    init_db()
    print("=" * 56)
    print(" FocusBuddy server")
    ip = local_ip()
    if ip:
        print(f" Dashboard:  http://{ip}:{PORT}")
        print(f" ESP32 SERVER setting:  http://{ip}:{PORT}")
    print(" If the ESP32 can't connect, run `ifconfig` and use the inet")
    print(" address of the hotspot interface (wlan0 / ap0 / swlan0).")
    print(f" AI: {'ON (' + LLM_MODEL + ')' if LLM_API_KEY and LLM_MODEL else 'OFF - set LLM_API_KEY and LLM_MODEL'}")
    print("=" * 56)
    app.run(host="0.0.0.0", port=PORT, threaded=True)
