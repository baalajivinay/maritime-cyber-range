#!/usr/bin/env python3
"""
WO-23 (live tap) / WO-24 feed: run the domain's detectors against the LIVE feeds
and append each Alert to a JSONL log. Consumes only live telemetry (never the
attack_logs ground truth). Domain comes from the active profile.

Feeds tapped:
  - MAVLink (a spare ArduPilot port, default tcp:5763 = SERIAL2, so it doesn't
    contend with the dashboard/bridge): GLOBAL_POSITION_INT (surface believed
    position), LOCAL_POSITION_NED (underwater believed position), HEARTBEAT
    (armed state), RC_CHANNELS (to surface RC-override / C2 seizures).
  - AIS UDP (surface only).

Usage:
  MCR_VEHICLE_PROFILE=<profile> python3 detection/run_detectors.py [--seconds N] [--out path]
"""
import argparse
import json
import os
import socket
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "detection"))
import constants
from detectors import DetectorSuite
from pymavlink import mavutil

ap = argparse.ArgumentParser()
ap.add_argument("--seconds", type=float, default=60.0)
ap.add_argument("--out", default=None)
ap.add_argument("--mav", default=os.environ.get("MCR_DETECT_MAV", "tcp:127.0.0.1:5763"))
ARGS = ap.parse_args()

DOMAIN = constants.DOMAIN
OUT = ARGS.out or os.path.join(REPO, "evidence", f"detector_alerts_{constants.PROFILE_NAME}.jsonl")
# own-vessel MMSI is operational fleet knowledge (openly broadcast), not attack
# ground truth -- lets the AIS detector whitelist the real vessel and catch
# impersonation of it.
suite = DetectorSuite(DOMAIN, cfg={"known_mmsi": constants.VESSEL_MMSI})
_lock = threading.Lock()
_fh = open(OUT, "w")


def emit(alerts):
    with _lock:
        for a in alerts:
            _fh.write(json.dumps(a.as_dict()) + "\n")
            _fh.flush()
            print(f"ALERT {a.attack_type}: {a.detail}", flush=True)


def mav_loop(deadline):
    m = mavutil.mavlink_connection(ARGS.mav)
    m.wait_heartbeat(timeout=15)
    m.mav.request_data_stream_send(m.target_system, m.target_component,
                                   mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
    while time.time() < deadline:
        msg = m.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue
        t = time.time()
        mt = msg.get_type()
        if mt == "GLOBAL_POSITION_INT":
            emit(suite.update({"type": "believed_pos", "t": t,
                               "lat": msg.lat / 1e7, "lon": msg.lon / 1e7}))
        elif mt == "LOCAL_POSITION_NED":
            emit(suite.update({"type": "local_pos", "t": t,
                               "n": msg.x, "e": msg.y, "d": msg.z, "vx": msg.vx, "vy": msg.vy}))
        elif mt == "HEARTBEAT" and msg.type != mavutil.mavlink.MAV_TYPE_GCS:
            emit(suite.update({"type": "armed", "t": t,
                               "armed": bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)}))
        elif mt == "RC_CHANNELS":
            # No physical RC in this project -> any driven throttle/steering
            # channel is an override (C2 actuator seizure).
            driven = [getattr(msg, f"chan{i}_raw", 0) for i in (1, 3)]
            if any(900 < v < 2100 and abs(v - 1500) > 100 for v in driven):
                emit(suite.update({"type": "rc_override", "t": t, "domain": DOMAIN}))


def ais_loop(deadline):
    ip, port = constants.AIS_UDP_ADDR
    from pyais import decode
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except OSError:
        pass
    s.bind(("127.0.0.1", port))
    s.settimeout(1.0)
    while time.time() < deadline:
        try:
            data, _ = s.recvfrom(2048)
        except socket.timeout:
            continue
        for ln in data.decode("ascii", "ignore").splitlines():
            ln = ln.strip()
            if not ln.startswith("!AIVD"):
                continue
            try:
                d = decode(ln).asdict()
            except Exception:
                continue
            if d.get("lat") and d.get("lon") and d.get("mmsi"):
                emit(suite.update({"type": "ais", "t": time.time(),
                                   "mmsi": d["mmsi"], "lat": float(d["lat"]), "lon": float(d["lon"])}))


def main():
    deadline = time.time() + ARGS.seconds
    print(f"[detectors] domain={DOMAIN} tapping {ARGS.mav} + AIS; {ARGS.seconds:.0f}s -> {OUT}", flush=True)
    threads = [threading.Thread(target=mav_loop, args=(deadline,), daemon=True)]
    if DOMAIN == "surface" and constants.AIS_UDP_ADDR:
        threads.append(threading.Thread(target=ais_loop, args=(deadline,), daemon=True))
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    _fh.close()
    print("[detectors] done.", flush=True)


if __name__ == "__main__":
    main()
