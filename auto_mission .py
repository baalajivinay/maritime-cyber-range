"""
Autonomous waypoint mission demo.

Everything tested so far has used MANUAL mode with a human sending
rc 3 1600-style throttle commands via MAVProxy. This script does the
opposite: uploads a real MAVLink mission (a sequence of GPS waypoints)
and switches ArduPilot to AUTO mode, so the autopilot navigates on its
own -- no human input after this script finishes. This is the actual
"autonomous" claim of an Autonomous Maritime Cyber Range, and it hasn't
been demonstrated yet.

PREREQUISITE (once per SITL session, in the MAVProxy console, same
pattern as WO-07's c2_replay.py -- gives this script its own MAVLink
endpoint so it doesn't conflict with the dashboard or c2_replay.py):
    output add 127.0.0.1:14552

Requires: pymavlink
"""

import time
from pymavlink import mavutil

MAVLINK_ENDPOINT = "udpin:127.0.0.1:14552"

# Home position used throughout this project (sydney_regatta / SITL -l flag)
HOME_LAT = -33.724223
HOME_LON = 150.679736

# A simple L-shaped path: north 50m, then east 50m -- enough to show
# both straight-line travel AND a real autonomous turn/waypoint switch.
import math

def offset_latlon(lat, lon, north_m, east_m):
    dlat = north_m / 111320.0
    dlon = east_m / (111320.0 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon

def connect():
    print(f"Connecting to {MAVLINK_ENDPOINT} ...")
    conn = mavutil.mavlink_connection(MAVLINK_ENDPOINT)
    conn.wait_heartbeat(timeout=15)
    print(f"Heartbeat received from system {conn.target_system}. Connected.")
    return conn


def get_actual_position(conn, timeout_s=10):
    """IMPORTANT: ArduPilot's configured HOME (-l flag) and the WAM-V's
    actual spawn point in the Gazebo world have been found to differ by
    ~500m -- likely because Gazebo's world file has its own fixed origin
    independent of ArduPilot's home setting. Waypoints computed from the
    -l flag value are therefore NOT relative to where the vessel actually
    is. This reads the vessel's real, current position from a live
    GLOBAL_POSITION_INT message instead, so waypoints are always relative
    to reality, not an assumption."""
    print("Reading live position to use as waypoint origin "
          "(NOT using the -l home flag, which does not match actual "
          "vessel position in this setup)...")
    msg = conn.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=timeout_s)
    if msg is None:
        raise RuntimeError("No GLOBAL_POSITION_INT received -- is the vessel "
                            "publishing telemetry?")
    lat, lon = msg.lat / 1e7, msg.lon / 1e7
    print(f"Actual current position: ({lat:.6f}, {lon:.6f})")
    return lat, lon


def check_arming_checks(conn):
    """Reads ARMING_CHECK param -- if it's not 0, arming may fail on a
    pre-arm check (GPS/EKF/compass health etc). This does NOT change
    anything, just reports the value so you know before attempting to arm."""
    conn.mav.param_request_read_send(
        conn.target_system, conn.target_component, b"ARMING_CHECK", -1)
    msg = conn.recv_match(type="PARAM_VALUE", blocking=True, timeout=5.0)
    if msg and msg.param_id.strip("\x00") == "ARMING_CHECK":
        print(f"ARMING_CHECK = {msg.param_value} "
              f"({'all checks enabled -- arming may fail on precondition' if msg.param_value != 0 else 'checks disabled'})")
    else:
        print("Could not read ARMING_CHECK param.")


def upload_mission(conn, waypoints):
    """Standard MAVLink mission upload handshake: announce count, respond
    to each MISSION_REQUEST(_INT) with the corresponding waypoint, wait
    for final MISSION_ACK."""
    n = len(waypoints)
    print(f"Uploading mission: {n} waypoints...")
    conn.mav.mission_count_send(conn.target_system, conn.target_component, n)

    sent = 0
    timeout = time.time() + 15
    while sent < n and time.time() < timeout:
        msg = conn.recv_match(
            type=["MISSION_REQUEST", "MISSION_REQUEST_INT"],
            blocking=True, timeout=3.0)
        if msg is None:
            continue
        seq = msg.seq
        lat, lon = waypoints[seq]
        conn.mav.mission_item_int_send(
            conn.target_system, conn.target_component, seq,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
            0, 1,  # current, autocontinue
            0, 0, 0, 0,  # param1-4 (hold time, accept radius, pass radius, yaw)
            int(lat * 1e7), int(lon * 1e7), 0)
        print(f"  Sent waypoint {seq}: ({lat:.6f}, {lon:.6f})")
        sent += 1

    ack = conn.recv_match(type="MISSION_ACK", blocking=True, timeout=5.0)
    if ack and ack.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
        print("Mission upload ACCEPTED.")
        return True
    else:
        print(f"Mission upload FAILED or no ACK received: {ack}")
        return False


def start_mission(conn):
    """Switch to AUTO mode and arm -- from this point on, ArduPilot
    navigates the uploaded mission with zero manual input."""
    mode_id = conn.mode_mapping().get("AUTO")
    if mode_id is None:
        print(f"AUTO mode not found. Available: {list(conn.mode_mapping().keys())}")
        return
    conn.mav.set_mode_send(
        conn.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode_id)
    print("Mode set to AUTO.")
    time.sleep(1)

    conn.mav.command_long_send(
        conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 1, 0, 0, 0, 0, 0, 0)
    ack = conn.recv_match(type="COMMAND_ACK", blocking=True, timeout=5.0)
    print(f"Arm command result: {ack}")
    print("\nVessel should now navigate the uploaded mission autonomously.")
    print("Watch the dashboard, or monitor MISSION_CURRENT / GLOBAL_POSITION_INT "
          "to confirm it advances through waypoints with no further input from this script.")


def monitor_mission(conn, duration_s=120):
    """Prints MISSION_CURRENT (which waypoint is active) and position
    periodically, so progress is visible without needing the dashboard."""
    print(f"\nMonitoring for {duration_s}s (Ctrl+C to stop early)...")
    end = time.time() + duration_s
    last_seq = None
    try:
        while time.time() < end:
            msg = conn.recv_match(
                type=["MISSION_CURRENT", "GLOBAL_POSITION_INT"],
                blocking=True, timeout=2.0)
            if msg is None:
                continue
            if msg.get_type() == "MISSION_CURRENT":
                if msg.seq != last_seq:
                    print(f"[MISSION] now navigating to waypoint seq={msg.seq}")
                    last_seq = msg.seq
            elif msg.get_type() == "GLOBAL_POSITION_INT":
                print(f"[POSITION] lat={msg.lat/1e7:.6f}, lon={msg.lon/1e7:.6f}")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    conn = connect()
    check_arming_checks(conn)
    actual_lat, actual_lon = get_actual_position(conn)
    WP1 = offset_latlon(actual_lat, actual_lon, 50, 0)   # 50m north of ACTUAL position
    WP2 = offset_latlon(actual_lat, actual_lon, 50, 50)  # 50m north, 50m east
    WAYPOINTS = [WP1, WP2]
    if upload_mission(conn, WAYPOINTS):
        start_mission(conn)
        monitor_mission(conn)
    else:
        print("Aborting -- mission upload did not succeed.")
