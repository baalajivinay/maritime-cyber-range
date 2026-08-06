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

System-performance-overhead metric: this process is a passive blind tap --
it sits alongside the autopilot/dashboard, not inline with them, so the
resource cost it adds to "the system" IS its own CPU/memory footprint plus
its own per-event processing time. Both are sampled here (stdlib `resource`
+ `time.perf_counter` around each detector update) and written to
evidence/detector_overhead_<profile>.json at exit, alongside the existing
alert JSONL.

Usage:
  MCR_VEHICLE_PROFILE=<profile> python3 detection/run_detectors.py [--seconds N] [--out path]
"""
import argparse
import json
import os
import resource
import socket
import statistics
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
OVERHEAD_OUT = os.path.join(REPO, "evidence", f"detector_overhead_{constants.PROFILE_NAME}.json")
# own-vessel MMSI is operational fleet knowledge (openly broadcast), not attack
# ground truth -- lets the AIS detector whitelist the real vessel and catch
# impersonation of it.
suite = DetectorSuite(DOMAIN, cfg={"known_mmsi": constants.VESSEL_MMSI})
_lock = threading.Lock()
_fh = open(OUT, "w")
_alerts_emitted = 0
_event_proc_s = []      # one entry per suite.update() call: wall time spent inside it
_events_processed = 0


def emit(alerts):
    global _alerts_emitted
    with _lock:
        for a in alerts:
            _fh.write(json.dumps(a.as_dict()) + "\n")
            _fh.flush()
            _alerts_emitted += 1
            print(f"ALERT {a.attack_type}: {a.detail}", flush=True)


def tap(event):
    """Feed one live event through the detector suite, timing the call so the
    per-event processing overhead can be reported alongside the alerts."""
    global _events_processed
    t0 = time.perf_counter()
    alerts = suite.update(event)
    dt = time.perf_counter() - t0
    with _lock:
        _event_proc_s.append(dt)
        _events_processed += 1
    emit(alerts)


def _pctile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def write_overhead_report(wall_s):
    """Dump the CPU/memory/throughput footprint of this blind-tap process --
    the system-performance-overhead metric the monitoring layer adds."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    cpu_s = usage.ru_utime + usage.ru_stime
    proc_us = sorted(d * 1e6 for d in _event_proc_s)
    report = {
        "profile": constants.PROFILE_NAME,
        "domain": DOMAIN,
        "wall_s": round(wall_s, 3),
        "cpu_s": round(cpu_s, 3),
        "cpu_pct_of_wall": round(100.0 * cpu_s / wall_s, 3) if wall_s > 0 else None,
        "peak_rss_mb": round(usage.ru_maxrss / 1024.0, 2),   # ru_maxrss is KB on Linux
        "events_processed": _events_processed,
        "alerts_emitted": _alerts_emitted,
        "events_per_sec": round(_events_processed / wall_s, 2) if wall_s > 0 else None,
        "event_proc_time_us": {
            "mean": round(statistics.mean(proc_us), 2) if proc_us else None,
            "median": round(statistics.median(proc_us), 2) if proc_us else None,
            "p95": round(_pctile(proc_us, 0.95), 2) if proc_us else None,
            "max": round(max(proc_us), 2) if proc_us else None,
        },
    }
    with open(OVERHEAD_OUT, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[detectors] overhead: cpu={report['cpu_pct_of_wall']}% of wall, "
          f"peak_rss={report['peak_rss_mb']}MB, {_events_processed} events "
          f"(avg proc {report['event_proc_time_us']['mean']}us) -> {OVERHEAD_OUT}",
          flush=True)


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
            tap({"type": "believed_pos", "t": t,
                 "lat": msg.lat / 1e7, "lon": msg.lon / 1e7})
        elif mt == "LOCAL_POSITION_NED":
            tap({"type": "local_pos", "t": t,
                 "n": msg.x, "e": msg.y, "d": msg.z, "vx": msg.vx, "vy": msg.vy})
        elif mt == "HEARTBEAT" and msg.type != mavutil.mavlink.MAV_TYPE_GCS:
            tap({"type": "armed", "t": t,
                 "armed": bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)})
        elif mt == "RC_CHANNELS":
            # No physical RC in this project -> any driven throttle/steering
            # channel is an override (C2 actuator seizure).
            driven = [getattr(msg, f"chan{i}_raw", 0) for i in (1, 3)]
            if any(900 < v < 2100 and abs(v - 1500) > 100 for v in driven):
                tap({"type": "rc_override", "t": t, "domain": DOMAIN})


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
                tap({"type": "ais", "t": time.time(),
                     "mmsi": d["mmsi"], "lat": float(d["lat"]), "lon": float(d["lon"])})


def main():
    start = time.time()
    deadline = start + ARGS.seconds
    print(f"[detectors] domain={DOMAIN} tapping {ARGS.mav} + AIS; {ARGS.seconds:.0f}s -> {OUT}", flush=True)
    threads = [threading.Thread(target=mav_loop, args=(deadline,), daemon=True)]
    if DOMAIN == "surface" and constants.AIS_UDP_ADDR:
        threads.append(threading.Thread(target=ais_loop, args=(deadline,), daemon=True))
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    _fh.close()
    write_overhead_report(time.time() - start)
    print("[detectors] done.", flush=True)


if __name__ == "__main__":
    main()
