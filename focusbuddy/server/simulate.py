#!/usr/bin/env python3
"""
Fake ESP32 for testing the server and dashboard before the hardware is wired.
Run the server first, then:  python simulate.py  [http://127.0.0.1:5000]
It sits down, focuses, leans too close once, and takes a break (demo timings).
"""
import sys
import time
import random
import requests

SERVER = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000").rstrip("/")

t0 = time.time()
focus_s = sessions = too_close = 0
pomo, remaining, present, lamp = "idle", 0, False, False
sent_close = False

while True:
    t = time.time() - t0
    events = []
    if not present and t > 4:
        present = True
        events.append("sit_down")
        pomo, remaining = "focus", 120
        events.append("focus_start")
    dist = 999 if not present else (35 if 30 < t < 45 else random.randint(55, 75))
    if 40 < t < 45 and not sent_close:
        sent_close = True
        too_close += 1
        events.append("too_close")
    desk = 25 if t < 60 else 70
    win = 20
    if present and desk < 35 and not lamp:
        lamp = True
        events.append("lamp_on")
    if pomo == "focus":
        remaining -= 2
        focus_s += 2
        if remaining <= 0:
            pomo, remaining = "break", 60
            sessions += 1
            events.append("break_start")
    elif pomo == "break":
        remaining -= 2
        if remaining <= 0:
            pomo, remaining = "focus", 120
            events.append("break_end")

    body = dict(present=present, distance_cm=dist, desk_light=desk, window_light=win, lamp=lamp,
                lamp_mode="auto", pomo=pomo, remaining_s=max(0, remaining), focus_s_today=focus_s,
                sessions=sessions, too_close_count=too_close, events=events)
    try:
        r = requests.post(SERVER + "/api/telemetry", json=body, timeout=3).json()
        if r.get("say"):
            pcm = requests.get(f"{SERVER}/api/tts/{r['say']}.pcm", timeout=10).content
            print(f"  speaker would play {len(pcm) / 32000:.1f}s of audio")
        if r.get("oled"):
            print("  OLED:", r["oled"])
        print(f"t={int(t):3d}s {pomo:5s} {max(0, remaining):3d}s dist={dist} events={events}")
    except Exception as e:
        print("server not reachable:", e)
    time.sleep(2)
