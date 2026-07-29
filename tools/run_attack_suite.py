#!/usr/bin/env python3
"""
WO-15: domain-aware attack suite.

Runs each attack in the ACTIVE PROFILE's applicable-attack set against a running
stack, verifies its effect the same independent way this project verifies attacks
by hand (MAVLink/telemetry vs. TRUE Gazebo pose), and reports PASS/FAIL/SKIP per
attack plus a written evidence log. Never reads the private attack_logs/*.csv
ground truth -- verification uses only live feeds.

The profile drives which attacks run (constants.ATTACKS):
  surface  (wamv):     gps_spoof, ais_spoof (ghost+impersonate), c2_replay
  underwater (bluerov2): gps_spoof, acoustic_spoof (WO-16, SKIP until built),
                         c2_replay   -- AIS omitted (N/A submerged, by design)

Usage:
  # against an already-running stack (tools/run_sim.sh <profile> up):
  MCR_VEHICLE_PROFILE=<profile> python3 tools/run_attack_suite.py

  # self-contained (boot + run + teardown), one process:
  python3 tools/run_attack_suite.py --profile <profile> --boot
"""
import argparse
import json
import math
import os
import re
import socket
import subprocess
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "attacks"))

# --- CLI (profile must be set BEFORE importing constants) --------------------
_ap = argparse.ArgumentParser()
_ap.add_argument("--profile", default=os.environ.get("MCR_VEHICLE_PROFILE", "wamv"))
_ap.add_argument("--boot", action="store_true",
                 help="boot the stack via tools/run_sim.sh, run, then tear down")
_ap.add_argument("--evidence", default=None, help="path for the evidence log")
ARGS = _ap.parse_args()
os.environ["MCR_VEHICLE_PROFILE"] = ARGS.profile

import constants  # noqa: E402
from pymavlink import mavutil  # noqa: E402

PROFILE = constants.PROFILE_NAME
DOMAIN = constants.DOMAIN
ATTACKS = constants.ATTACKS
RUN_DIR = os.environ.get("MCR_RUN_DIR", f"/tmp/mcr_run/{PROFILE}")
RELAY_FIFO = os.path.join(RUN_DIR, "relay.fifo")

# Model + true-pose topic come from the profile's "world" config, so a new
# vehicle in a new world is handled without editing this file.
_world = {}
try:
    with open(os.path.join(REPO, "profiles", PROFILE + ".json")) as _f:
        _world = json.load(_f).get("world", {})
except Exception:
    pass
MODEL = _world.get("model_name", "bluerov2" if DOMAIN == "underwater" else "wamv")
_world_name = _world.get("world_name",
                         "underwater_harbor" if DOMAIN == "underwater" else "sydney_regatta")
POSE_TOPIC = f"/world/{_world_name}/pose/info"

MAV_ENDPOINT = f"udpin:127.0.0.1:{constants.MAVLINK_AUTO_MISSION_PORT}"


# --- helpers -----------------------------------------------------------------
def true_pose():
    """(x, y, z) of the vehicle from Gazebo -- independent ground truth."""
    try:
        p = subprocess.run(["gz", "topic", "-e", "-t", POSE_TOPIC, "-n", "3"],
                           stdout=subprocess.PIPE, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return None
    out = None
    for b in p.stdout.split("pose {"):
        if f'name: "{MODEL}"' not in b:
            continue
        mx = re.search(r"position\s*\{\s*x:\s*([-\d.e]+)", b)
        my = re.search(r"position\s*\{[^}]*y:\s*([-\d.e]+)", b, re.S)
        mz = re.search(r"position\s*\{[^}]*z:\s*([-\d.e]+)", b, re.S)
        if mx and my and mz:
            out = (float(mx.group(1)), float(my.group(1)), float(mz.group(1)))
    return out


def relay_cmd(cmd):
    """Send a control command to the FDM relay (gps_spoof.py) via its FIFO."""
    with open(RELAY_FIFO, "w") as f:
        f.write(cmd + "\n")


def latest(conn, typ, d=1.5):
    last, end = None, time.time() + d
    while time.time() < end:
        m = conn.recv_match(type=typ, blocking=False)
        if m is not None and not (typ == "HEARTBEAT" and m.type == mavutil.mavlink.MAV_TYPE_GCS):
            last = m
        time.sleep(0.02)
    return last


def connect():
    conn = mavutil.mavlink_connection(MAV_ENDPOINT)
    for _ in range(6):
        hb = conn.wait_heartbeat(timeout=5)
        if hb is not None and conn.target_system not in (0, 255):
            return conn
    raise SystemExit(f"FATAL: no autopilot heartbeat on {MAV_ENDPOINT} -- is the stack up?")


def arm_manual(conn):
    for _ in range(5):
        conn.set_mode(conn.mode_mapping()["MANUAL"])
        time.sleep(1.0)
        hb = latest(conn, "HEARTBEAT")
        if hb and hb.custom_mode == conn.mode_mapping()["MANUAL"]:
            break
    for _ in range(6):
        conn.mav.command_long_send(conn.target_system, conn.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
        time.sleep(1.2)
        hb = latest(conn, "HEARTBEAT")
        if hb and (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            return True
    return False


def disarm(conn):
    conn.mav.command_long_send(conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 0, 0, 0, 0, 0, 0)


def horiz_m(dlat, dlon, lat):
    return math.hypot(dlat * constants.M_PER_DEG_LAT, dlon * constants.m_per_deg_lon(lat))


# --- attack checks: return (status, detail) ----------------------------------
def check_gps_spoof(conn):
    """Forge a GPS offset via the relay; PASS if MAVLink position jumps while
    the TRUE Gazebo position does not.

    Domain note: GPS is a surface/RF phenomenon -- it does NOT reach a SUBMERGED
    AUV (which navigates inertially/acoustically), so a submerged AUV shows no
    effect by design. For the underwater domain this attack is only meaningful
    during surfaced GPS-fix windows, whose live verification is a separate work
    order (WO-17); the submerged analog is acoustic spoofing (WO-16). So here we
    skip it for underwater rather than mis-report physically-correct no-effect as
    a failure."""
    if DOMAIN == "underwater":
        return "SKIP", ("GPS does not reach a submerged AUV; applies only during "
                        "surfaced windows -- live verification is WO-17 (submerged "
                        "analog is acoustic spoofing, WO-16)")
    relay_cmd("off"); time.sleep(2)
    p0 = true_pose(); g0 = latest(conn, "GLOBAL_POSITION_INT", 2.0)
    if p0 is None or g0 is None:
        return "FAIL", "no baseline pose/telemetry"
    relay_cmd("step"); time.sleep(4)
    p1 = true_pose(); g1 = latest(conn, "GLOBAL_POSITION_INT", 2.0)
    relay_cmd("off")
    if p1 is None or g1 is None:
        return "FAIL", "no post-spoof pose/telemetry"
    true_move = math.dist(p0[:2], p1[:2])
    mav_jump = horiz_m((g1.lat - g0.lat) / 1e7, (g1.lon - g0.lon) / 1e7, g0.lat / 1e7)
    ok = mav_jump > 20.0 and true_move < 5.0
    return ("PASS" if ok else "FAIL"), \
        f"MAVLink position jumped {mav_jump:.1f} m; TRUE pose moved {true_move:.2f} m"


def check_ais(conn):
    """Ghost (fabricated vessel) + impersonation (forged position under the real
    MMSI). PASS if both signatures land on the AIS UDP channel."""
    import ais_spoof
    from pyais.stream import IterMessages
    REAL = int(constants.VESSEL_MMSI)
    GHOST = 999999001
    ip, port = constants.AIS_UDP_ADDR

    lsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except OSError:
        pass
    lsock.bind(("127.0.0.1", port))
    lsock.settimeout(0.3)
    lines, stop = [], threading.Event()

    def listen():
        while not stop.is_set():
            try:
                d, _ = lsock.recvfrom(2048)
            except socket.timeout:
                continue
            for ln in d.decode("ascii", "ignore").splitlines():
                ln = ln.strip()
                if ln.startswith("!AIVD"):  # AIVDM and AIVDO both
                    lines.append(ln.encode())

    threading.Thread(target=listen, daemon=True).start()
    ssock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    g = threading.Event()
    threading.Thread(target=ais_spoof.run_ghost_vessel, args=(ssock, g, GHOST, 1.0), daemon=True).start()
    time.sleep(5); g.set()
    i = threading.Event()
    threading.Thread(target=ais_spoof.run_impersonation,
                     args=(ssock, i, lambda: (constants.HOME_LAT, constants.HOME_LON)),
                     kwargs={"interval_s": 1.0}, daemon=True).start()
    time.sleep(5); i.set()
    time.sleep(0.5); stop.set()

    seen = {}
    for msg in IterMessages(list(lines)):
        try:
            m = msg.decode().asdict().get("mmsi")
            if m is not None:
                seen[m] = seen.get(m, 0) + 1
        except Exception:
            pass
    ghost_ok = seen.get(GHOST, 0) > 0
    imp_ok = seen.get(REAL, 0) > 0
    detail = f"ghost {GHOST}: {seen.get(GHOST,0)} msgs; impersonation of real MMSI {REAL}: {seen.get(REAL,0)} msgs"
    return ("PASS" if (ghost_ok and imp_ok) else "FAIL"), detail


def check_c2_replay(conn):
    """Forged RC override must move the vehicle's TRUE Gazebo position/depth."""
    import c2_replay
    if not arm_manual(conn):
        return "FAIL", "could not arm (RC override is ignored while disarmed)"
    p0 = true_pose()
    # throttle drives forward (surface) / vertical (sub); either moves true pose
    c2_replay.inject_forged_rc_override(conn, throttle_pwm=1300, steering_pwm=1500, duration_s=8.0)
    p1 = true_pose()
    disarm(conn)
    if p0 is None or p1 is None:
        return "FAIL", "no pose reading"
    move = math.dist(p0, p1)  # full 3D (captures depth change for the AUV)
    return ("PASS" if move > 1.0 else "FAIL"), f"forged RC override moved TRUE pose {move:.2f} m"


def check_acoustic_spoof(conn):
    """Submerged analog of GPS spoofing (WO-16): the AUV's absolute position
    comes from the acoustic/ExternalNav channel (VISION_POSITION_ESTIMATE), not
    GPS. acoustic_spoof feeds that channel; PASS if the AUV's BELIEVED position
    walks away from its TRUE Gazebo position while spoofing, and tracks it when
    off."""
    if not os.path.exists(os.path.join(REPO, "attacks", "acoustic_spoof.py")):
        return "SKIP", "acoustic_spoof not implemented yet (WO-16)"
    import threading
    import acoustic_spoof as A

    feed = A.connect()
    threading.Thread(target=A.run_feed, args=(feed,), daemon=True).start()

    def believed_ne(d=2.5):
        last, end = None, time.time() + d
        while time.time() < end:
            m = conn.recv_match(type="LOCAL_POSITION_NED", blocking=False)
            if m is not None:
                last = m
            time.sleep(0.02)
        return (last.x, last.y) if last else None  # (N, E)

    def true_ne():
        p = true_pose()          # gazebo (x=E, y=N, z=U)
        return (p[1], p[0]) if p else None  # (N, E)

    time.sleep(8)  # let ExternalNav establish
    b0, t0 = believed_ne(), true_ne()
    if b0 is None or t0 is None:
        return "FAIL", "no position solution (ExternalNav feed not fusing?)"
    with A._lock:
        A.state.mode = "ramp"; A.state.start_time = time.time(); A.state.active = True
    time.sleep(16)
    b1, t1 = believed_ne(), true_ne()
    with A._lock:
        A.state.active = False
    if b1 is None or t1 is None:
        return "FAIL", "lost position solution under spoof"
    off_div = abs(b0[1] - t0[1])          # believed-vs-true East, no spoof
    spoof_div = abs(b1[1] - t1[1])        # believed-vs-true East, spoofing
    ok = off_div < 3.0 and spoof_div > 5.0
    return ("PASS" if ok else "FAIL"), \
        (f"believed-vs-true East divergence: {off_div:.1f} m when off, "
         f"{spoof_div:.1f} m while spoofing (belief walked off, true pose unmoved)")


CHECKS = {
    "gps_spoof": check_gps_spoof,
    "ais_spoof": check_ais,
    "c2_replay": check_c2_replay,
    "acoustic_spoof": check_acoustic_spoof,
}


# --- runner ------------------------------------------------------------------
def run_suite():
    conn = connect()
    print(f"[suite] profile={PROFILE} domain={DOMAIN} attacks={ATTACKS}", flush=True)
    results = []
    for attack in ATTACKS:
        check = CHECKS.get(attack)
        if check is None:
            results.append((attack, "SKIP", "no check registered"))
            continue
        print(f"[suite] running {attack} ...", flush=True)
        try:
            status, detail = check(conn)
        except Exception as e:
            status, detail = "FAIL", f"exception: {e!r}"
        results.append((attack, status, detail))
        print(f"[suite]   {attack}: {status} -- {detail}", flush=True)

    # AIS applicability note for underwater (correct N/A, not a gap)
    if DOMAIN == "underwater" and "ais_spoof" not in ATTACKS:
        results.append(("ais_spoof", "N/A", "AIS does not propagate underwater -- correctly excluded while submerged"))
    return results


def write_evidence(results):
    path = ARGS.evidence or os.path.join(REPO, "evidence", f"attack_suite_{PROFILE}.log")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(f"WO-15 attack suite -- profile={PROFILE} domain={DOMAIN}\n")
        f.write(f"run: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for attack, status, detail in results:
            f.write(f"[{status:4}] {attack}: {detail}\n")
    print(f"[suite] evidence written to {path}", flush=True)
    return path


def main():
    booted = False
    try:
        if ARGS.boot:
            print(f"[suite] booting stack via run_sim.sh {PROFILE} up ...", flush=True)
            r = subprocess.run([os.path.join(REPO, "tools", "run_sim.sh"), PROFILE, "up"])
            if r.returncode != 0:
                raise SystemExit("run_sim.sh up failed")
            booted = True
            time.sleep(3)
        results = run_suite()
        write_evidence(results)
    finally:
        if booted:
            print(f"[suite] tearing down via run_sim.sh {PROFILE} down ...", flush=True)
            subprocess.run([os.path.join(REPO, "tools", "run_sim.sh"), PROFILE, "down"])

    print("\n=== ATTACK SUITE SUMMARY ===")
    fails = 0
    for attack, status, detail in results:
        print(f"  {status:4}  {attack}")
        if status == "FAIL":
            fails += 1
    print(f"  {'PASS' if fails == 0 else 'FAIL'}: {fails} failure(s)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
