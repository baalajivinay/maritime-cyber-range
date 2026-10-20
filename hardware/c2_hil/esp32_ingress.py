#!/usr/bin/env python3
"""
ESP32 C2-HIL ingress + live blind detector.

The ESP32 rogue MAVLink node (hardware/esp32_mavlink_node/) sends UDP to
<host>:14550, but ArduPilot SITL's command links are TCP (5760/5762/5763) and
tools/mav_bridge.py only binds 127.0.0.1. This bridges that gap so the real
board can reach the target, and taps every message through the SAME blind
DetectorSuite tools/test_target.py uses -- so hardware detectability is directly
comparable to the software path.

    ESP32 --UDP--> 0.0.0.0:14550 <--> tcp:127.0.0.1:5762 (SITL)   (commands apply)
                        |
                        +--> DetectorSuite  -> prints each C2 alert live

Boot the target first with hardware/c2_hil/boot_c2_target.sh.

Env overrides:
    MCR_HIL_UDP   UDP port to listen on for the ESP32 (default 14550)
    MCR_HIL_SITL  SITL serial link to forward into   (default tcp:127.0.0.1:5762)
    MCR_HIL_DOMAIN surface | underwater               (default surface)

AUTHORIZED TESTING ONLY -- lab/range use on equipment you own.
"""
import os, sys, time
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "detection"))
from pymavlink import mavutil
from detectors import DetectorSuite

UDP_PORT = int(os.environ.get("MCR_HIL_UDP", "14550"))
SITL_LINK = os.environ.get("MCR_HIL_SITL", "tcp:127.0.0.1:5762")
DOMAIN = os.environ.get("MCR_HIL_DOMAIN", "surface")


def mav_to_event(msg):
    """Same mapping as tools/test_target.py's _mavlink_to_event (the shared
    detectability event shape) -- keeps HIL results comparable to software."""
    t = time.time(); mt = msg.get_type()
    if mt == "GLOBAL_POSITION_INT" and not (msg.lat == 0 and msg.lon == 0):
        return {"type": "believed_pos", "t": t, "lat": msg.lat / 1e7, "lon": msg.lon / 1e7}
    if mt == "HEARTBEAT" and msg.type != mavutil.mavlink.MAV_TYPE_GCS:
        return {"type": "armed", "t": t,
                "armed": bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)}
    if mt == "SET_MODE":
        return {"type": "mode_change", "t": t, "new_mode": str(msg.custom_mode),
                "prev_mode": "UNKNOWN", "domain": DOMAIN}
    if mt == "RC_CHANNELS":
        driven = [getattr(msg, f"chan{i}_raw", 0) for i in (1, 3)]
        if any(900 < v < 2100 and abs(v - 1500) > 100 for v in driven):
            return {"type": "rc_override", "t": t, "domain": DOMAIN}
    return None


def main():
    det = DetectorSuite(DOMAIN)
    alerts = []
    esp = mavutil.mavlink_connection(f"udpin:0.0.0.0:{UDP_PORT}")
    sitl = mavutil.mavlink_connection(SITL_LINK, source_system=255)
    print(f"[ingress] udpin 0.0.0.0:{UDP_PORT}  <->  {SITL_LINK} (SITL)", flush=True)
    print("[ingress] waiting for first ESP32 packet ...", flush=True)
    first_seen = False
    n_esp = n_sitl = 0
    by_type = {}
    last = time.time()

    def tap(msg):
        ev = mav_to_event(msg)
        if ev:
            new = det.update(ev)
            if new:
                alerts.extend(new)
                for a in new:
                    print(f"[ALERT #{len(alerts)}] {getattr(a, 'attack_type', a)} :: "
                          f"{getattr(a, 'detail', getattr(a, 'reason', ''))}", flush=True)

    while True:
        m = esp.recv_match(blocking=False)
        if m is not None and m.get_type() != "BAD_DATA":
            if not first_seen:
                print(f"[ingress] *** first ESP32 packet "
                      f"from {getattr(esp, 'last_address', None)} type={m.get_type()} *** WiFi path OK",
                      flush=True)
                first_seen = True
            n_esp += 1
            by_type[m.get_type()] = by_type.get(m.get_type(), 0) + 1
            try:
                sitl.write(m.get_msgbuf())
            except Exception:
                pass
            tap(m)
        s = sitl.recv_match(blocking=False)
        if s is not None and s.get_type() != "BAD_DATA":
            n_sitl += 1
            if first_seen:
                try:
                    esp.write(s.get_msgbuf())
                except Exception:
                    pass
            tap(s)
        if m is None and s is None:
            time.sleep(0.002)
        if time.time() - last > 5:
            print(f"[ingress] esp->sitl={n_esp} sitl->esp={n_sitl} esp_types={by_type} "
                  f"alerts={len(alerts)}", flush=True)
            last = time.time()


if __name__ == "__main__":
    main()
