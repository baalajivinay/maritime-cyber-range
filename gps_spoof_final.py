"""
GPS fault-injection module -- FINAL, based on verified findings:
- Relay binds 9002 (ArduPilot's fixed send target), forwards to Gazebo
  at 9100 (see 00_inspect_fdm_protocol_v2.py, confirmed working)
- FDM packets are JSON (ArduPilot's JSON/SIM_JSON backend), position
  field is [N, E, D] meters -- confirmed via two independent checks:
  matches documented ArduPilot JSON protocol convention, AND matches
  measured vx/vy from GLOBAL_POSITION_INT during a real throttle test
  (position[0] rate ~= vx/North, position[1] rate ~= vy/East, same
  throttle setting, same magnitude to within measurement noise)
- Spoofing works by adding a computed north/east meters offset directly
  onto position[0]/position[1] -- no HOME lat/lon math needed, since
  ArduPilot tracks its own origin from whatever position values it
  receives; perturbing the same values it already trusts is simpler
  and more robust than reconstructing absolute lat/lon.

SETUP (one-time, already done if you followed prior work orders):
  wamv_ardupilot.sdf's ArduPilotPlugin <fdm_port_in> must be 9100
  (Gazebo's real listening port, moved off the default 9002 so this
  relay can occupy that address instead).

USAGE:
  python3 gps_spoof.py
Then start VRX and SITL as usual. Use the interactive prompt (step/ramp/
off/quit) to control spoofing during a live run.
"""

import socket
import json
import time
import threading
import math
import csv
import os

# --- Fixed network config (verified working, do not change without re-testing) --
RELAY_BIND = ("127.0.0.1", 9002)     # ArduPilot always sends here
GAZEBO_ADDR = ("127.0.0.1", 9100)    # real Gazebo, moved off 9002 via SDF edit

ATTACK_LOG_PATH = os.path.expanduser("~/Maritime-sim/attack_logs/gps_spoof_ground_truth.csv")

# Approximate home, used ONLY for human-readable ground-truth logging
# (converting the injected meters offset to an approximate lat/lon for
# the log file) -- NOT used in the actual injection, which operates
# directly on position[0]/position[1] in their native meters frame.
HOME_LAT_APPROX = -33.724223
HOME_LON_APPROX = 150.679736

# --- Ground truth logging (private -- see docs/ARCHITECTURE.md) -------

os.makedirs(os.path.dirname(ATTACK_LOG_PATH), exist_ok=True)
_log_lock = threading.Lock()


def log_attack_event(wall_ts, attack_type, true_n, true_e, forged_n, forged_e):
    with _log_lock:
        write_header = not os.path.exists(ATTACK_LOG_PATH)
        with open(ATTACK_LOG_PATH, "a", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["wall_ts", "attack_type", "true_north_m", "true_east_m",
                            "forged_north_m", "forged_east_m",
                            "approx_true_lat", "approx_true_lon",
                            "approx_forged_lat", "approx_forged_lon"])
            # Rough lat/lon for human readability only -- see note above.
            true_lat = HOME_LAT_APPROX + true_n / 111320.0
            true_lon = HOME_LON_APPROX + true_e / (111320.0 * math.cos(math.radians(HOME_LAT_APPROX)))
            forged_lat = HOME_LAT_APPROX + forged_n / 111320.0
            forged_lon = HOME_LON_APPROX + forged_e / (111320.0 * math.cos(math.radians(HOME_LAT_APPROX)))
            w.writerow([wall_ts, attack_type, true_n, true_e, forged_n, forged_e,
                        true_lat, true_lon, forged_lat, forged_lon])


# --- Spoof state ---------------------------------------------------------

class SpoofState:
    def __init__(self):
        self.active = False
        self.mode = None              # "step" or "ramp"
        self.start_time = None
        self.step_offset_m = 50.0
        self.ramp_rate_m_per_s = 0.5
        self.direction_deg = 90.0     # bearing to forge the offset toward (0=N, 90=E)


state = SpoofState()


def compute_offset_m():
    """Returns (north_offset_m, east_offset_m) to ADD to the real position."""
    if not state.active:
        return 0.0, 0.0
    elapsed = time.time() - state.start_time
    bearing_rad = math.radians(state.direction_deg)
    if state.mode == "step":
        magnitude = state.step_offset_m
    elif state.mode == "ramp":
        magnitude = state.ramp_rate_m_per_s * elapsed
    else:
        return 0.0, 0.0
    north = magnitude * math.cos(bearing_rad)
    east = magnitude * math.sin(bearing_rad)
    return north, east


# --- Relay loop (same verified structure as 00_inspect_fdm_protocol_v2.py) --

def run_relay():
    ardupilot_facing = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ardupilot_facing.bind(RELAY_BIND)
    gazebo_facing = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    ardupilot_facing.settimeout(0.01)
    gazebo_facing.settimeout(0.01)

    print(f"GPS spoof relay: bound {RELAY_BIND}, Gazebo at {GAZEBO_ADDR}")
    print("Spoofing OFF by default. Commands: step | ramp | off | quit\n")

    ardupilot_addr = None
    packet_count = 0

    while True:
        # ArduPilot -> Gazebo (servo commands, pass through unmodified)
        try:
            data, addr = ardupilot_facing.recvfrom(65535)
            if ardupilot_addr != addr:
                ardupilot_addr = addr
                print(f"ArduPilot address: {addr}")
            gazebo_facing.sendto(data, GAZEBO_ADDR)
        except socket.timeout:
            pass

        # Gazebo -> ArduPilot (FDM/JSON reply -- THIS is where we inject)
        try:
            reply, _ = gazebo_facing.recvfrom(65535)
            try:
                payload = json.loads(reply.decode("utf-8"))
                true_n, true_e = payload["position"][0], payload["position"][1]

                if state.active:
                    off_n, off_e = compute_offset_m()
                    forged_n = true_n + off_n
                    forged_e = true_e + off_e
                    payload["position"][0] = forged_n
                    payload["position"][1] = forged_e
                    log_attack_event(time.time(), state.mode, true_n, true_e, forged_n, forged_e)
                    out_bytes = json.dumps(payload).encode("utf-8") + b"\n"
                else:
                    out_bytes = reply  # pass through unmodified, byte-identical

                packet_count += 1
                if packet_count % 250 == 0:
                    tag = f"[SPOOFING: {state.mode}]" if state.active else "[passthrough]"
                    print(f"{tag} packet {packet_count}, true_pos=({true_n:.2f},{true_e:.2f})")

            except (json.JSONDecodeError, KeyError):
                out_bytes = reply  # unparseable/unexpected packet, pass through untouched

            if ardupilot_addr:
                ardupilot_facing.sendto(out_bytes, ardupilot_addr)
        except socket.timeout:
            pass


def control_cli():
    print("Commands: 'step' | 'ramp' | 'off' | 'quit'")
    while True:
        cmd = input("> ").strip().lower()
        if cmd == "step":
            state.mode = "step"
            state.active = True
            state.start_time = time.time()
            print(f"STEP spoof ON: +{state.step_offset_m}m at bearing {state.direction_deg} deg")
        elif cmd == "ramp":
            state.mode = "ramp"
            state.active = True
            state.start_time = time.time()
            print(f"RAMP spoof ON: {state.ramp_rate_m_per_s} m/s drift at bearing {state.direction_deg} deg")
        elif cmd == "off":
            state.active = False
            print("Spoof OFF -- real position passed through unmodified")
        elif cmd == "quit":
            os._exit(0)
        else:
            print("Unknown command. Use: step | ramp | off | quit")


if __name__ == "__main__":
    t = threading.Thread(target=run_relay, daemon=True)
    t.start()
    control_cli()
