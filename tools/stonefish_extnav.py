#!/usr/bin/env python3
"""
Stonefish ExternalNav (USBL) feed + acoustic-spoof injector.

A submerged AUV fixes horizontal position from an acoustic positioning system
(USBL/LBL), delivered to ArduSub as VISION_POSITION_ESTIMATE. This feed reads
the AUV's TRUE pose broadcast by the Stonefish bridge (MCR, UDP :9005) and sends
it to ArduSub -- the honest USBL. On command it forges an OFFSET (the acoustic
spoof), walking the vehicle's believed position off its true track. This is the
underwater analog of GPS spoofing, run against the high-fidelity Stonefish sim.

  pose in : UDP :9005  {"n":..,"e":..,"d":..,"yaw":..}   (from MCR bridge)
  control : UDP :10120 "step" | "ramp" | "off"           (the attack toggle)
  out     : VISION_POSITION_ESTIMATE -> ArduSub (default tcp:127.0.0.1:5762)

Usage: python3 tools/stonefish_extnav.py [mavlink_link]
Authorized lab/range use only.
"""
import json
import math
import os
import socket
import sys
import threading
import time

from pymavlink import mavutil

try:
    from scaleup.physics.acoustic_channel import AcousticChannel
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scaleup.physics.acoustic_channel import AcousticChannel

POSE_PORT = 9005
CTRL_PORT = 10120
LINK = sys.argv[1] if len(sys.argv) > 1 else "tcp:127.0.0.1:5762"
STEP_M = float(os.environ.get("MCR_SPOOF_STEP", "50.0"))
RAMP_MPS = float(os.environ.get("MCR_SPOOF_RAMP", "2.0"))
BEARING = float(os.environ.get("MCR_SPOOF_BEARING", "90.0"))

state = {"mode": "off", "t0": 0.0, "reset_cnt": 0}


def control_loop():
    cs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    cs.bind(("127.0.0.1", CTRL_PORT))
    while True:
        data, _ = cs.recvfrom(64)
        cmd = data.decode("ascii", "ignore").strip().lower()
        if cmd in ("off", "step", "ramp"):
            if cmd == "step" and state["mode"] != "step":
                state["reset_cnt"] = (state["reset_cnt"] + 1) % 255
            state["mode"] = cmd
            state["t0"] = time.time()
            print(f"[extnav] spoof -> {cmd.upper()}", flush=True)


def offset():
    if state["mode"] == "step":
        mag = STEP_M
    elif state["mode"] == "ramp":
        mag = RAMP_MPS * (time.time() - state["t0"])
    else:
        return 0.0, 0.0
    br = math.radians(BEARING)
    return mag * math.cos(br), mag * math.sin(br)   # (north, east)


def main():
    conn = mavutil.mavlink_connection(LINK, source_system=1, source_component=197)
    print(f"[extnav] waiting for ArduSub heartbeat on {LINK} ...", flush=True)
    if conn.wait_heartbeat(timeout=30) is None:
        print("[extnav] no heartbeat -- is ArduSub up?"); return
    print("[extnav] connected. Feeding USBL/ExternalNav (spoof OFF = transparent).", flush=True)
    threading.Thread(target=control_loop, daemon=True).start()
    ps = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ps.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ps.bind(("127.0.0.1", POSE_PORT))
    ps.settimeout(2.0)
    n0 = e0 = None
    acoustic_channel = AcousticChannel(sound_speed_mps=1542.4)
    while True:
        try:
            data, _ = ps.recvfrom(512)
        except socket.timeout:
            continue
        try:
            d = json.loads(data.decode("ascii", "ignore"))
        except Exception:
            continue
        n, e, dep, yaw = d["n"], d["e"], d["d"], d["yaw"]
        if n0 is None:
            n0, e0 = n, e
        on, oe = offset()
        now = time.time()
        
        # Buffer into acoustic channel
        packet_payload = (n + on, e + oe, dep, yaw)
        acoustic_channel.send_position(now, n + on, e + oe, dep, packet_payload)

        # Dispatch any packets whose acoustic travel time tau = d/c has elapsed
        ready_packets = acoustic_channel.receive_ready(now)
        for (pn, pe, pdep, pyaw), r, tau in ready_packets:
            usec = int(time.time() * 1e6)
            conn.mav.vision_position_estimate_send(
                usec, pn, pe, pdep, 0.0, 0.0, pyaw, (0.0,) * 21, state.get("reset_cnt", 0))


if __name__ == "__main__":
    main()
