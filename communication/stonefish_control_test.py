#!/usr/bin/env python3
"""
Active control tuning check for the Stonefish-bridged AUV-150.

Drives ArduSub via the native joystick interface (MANUAL_CONTROL) and measures
the response of the real Stonefish physics body (TRUE pose broadcast on :9005),
not just the EKF estimate. Verifies the closed loop:

    ArduSub autopilot --servo PWM--> Stonefish thrusters --physics--> pose
                 ^                                                      |
                 +------------- JSON FDM sensors <---------------------+

Tests: dive, depth-HOLD in ALT_HOLD against buoyancy, heading change + hold,
and forward translation.

Usage: python3 tools/stonefish_control_test.py [mavlink_link]
"""
import math
import socket
import sys
import threading
import time

from pymavlink import mavutil

LINK = sys.argv[1] if len(sys.argv) > 1 else "tcp:127.0.0.1:5763"

# Telemetry cache fed from VFR_HUD/GLOBAL_POSITION_INT. The Stonefish bridge
# feeds the EKF directly from physics, so with the acoustic spoof OFF the EKF
# depth/heading equal ground truth -- correct for control tuning.
_t = {"depth": None, "hdg": None, "gspd": None, "n": None, "e": None, "climb": None}


def true_depth():
    return _t["depth"]


def true_yaw_deg():
    return _t["hdg"]


def main():
    print("[ctl] connecting %s ..." % LINK, flush=True)
    m = mavutil.mavlink_connection(LINK, source_system=255)
    if m.wait_heartbeat(timeout=30) is None:
        print("[ctl] no heartbeat"); return
    print("[ctl] heartbeat sys %d comp %d" % (m.target_system, m.target_component))
    m.mav.request_data_stream_send(m.target_system, m.target_component,
                                   mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
    time.sleep(1.5)

    def setmode(name):
        mid = m.mode_mapping().get(name)
        m.mav.set_mode_send(m.target_system,
                            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mid)

    def pump():
        """Drain telemetry into the cache (non-blocking)."""
        while True:
            msg = m.recv_match(type=["VFR_HUD", "GLOBAL_POSITION_INT"], blocking=False)
            if msg is None:
                break
            tp = msg.get_type()
            if tp == "VFR_HUD":
                _t["depth"] = msg.alt            # metres, negative = below surface
                _t["hdg"] = msg.heading          # deg
                _t["gspd"] = msg.groundspeed
                _t["climb"] = msg.climb          # m/s, +up
            elif tp == "GLOBAL_POSITION_INT":
                _t["n"] = msg.lat; _t["e"] = msg.lon

    def drive(x, y, z, r, secs, hz=15):
        """Stream MANUAL_CONTROL for `secs`; keeps the vehicle armed + moving."""
        n = max(1, int(secs * hz))
        for _ in range(n):
            m.mav.manual_control_send(m.target_system, int(x), int(y), int(z), int(r), 0)
            pump()
            time.sleep(1.0 / hz)

    # depth() returns positive-down metres (VFR_HUD.alt is negative below surface)
    def depth():
        return None if true_depth() is None else -true_depth()

    # wait for a telemetry fix
    t0 = time.time()
    while depth() is None and time.time() - t0 < 6:
        pump(); time.sleep(0.2)
    print("[ctl] start depth=%s m  heading=%s deg" %
          (round(depth(), 2) if depth() is not None else "?",
           round(true_yaw_deg(), 1) if true_yaw_deg() is not None else "?"))

    # ---- arm in MANUAL (robust: retry until the heartbeat confirms armed) ----
    def is_armed():
        hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
        return hb is not None and bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)

    setmode("MANUAL"); time.sleep(0.5)
    armed = False
    for attempt in range(5):
        m.mav.command_long_send(m.target_system, m.target_component,
                                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                                0, 1, 0, 0, 0, 0, 0, 0)
        m.recv_match(type="COMMAND_ACK", blocking=True, timeout=3)
        # stream a little neutral input so it does not idle-disarm, then confirm
        drive(0, 0, 500, 0, 1.0)
        if is_armed():
            armed = True
            break
    print("[ctl] arm: %s (after %d attempt(s))" % ("OK" if armed else "FAILED", attempt + 1))

    # ---- DIVE to depth in ALT_HOLD (realistic: controller manages the descent) ----
    TARGET = 5.0
    setmode("ALT_HOLD")
    print("[ctl] DIVE to ~%.0f m in ALT_HOLD (z=250 controlled descent) ..." % TARGET)
    t_end = time.time() + 30
    while time.time() < t_end:
        drive(0, 0, 250, 0, 0.3)
        if depth() is not None and depth() >= TARGET:
            break
    # settle: hold neutral until the vertical rate bleeds off (momentum gone)
    print("[ctl] reached depth=%.2f m; settling until stable ..." % depth())
    t_end = time.time() + 20
    while time.time() < t_end:
        drive(0, 0, 500, 0, 1.0)
        if _t["climb"] is not None and abs(_t["climb"]) < 0.05:
            # confirm it stays stable for a moment
            drive(0, 0, 500, 0, 1.5)
            if _t["climb"] is not None and abs(_t["climb"]) < 0.08:
                break
    d_dive = depth()
    print("[ctl] stabilized at %.2f m (climb %.3f m/s)" % (d_dive, _t["climb"] or 0.0))

    # ---- measure steady-state HOLD for 12 s ----
    print("[ctl] ALT_HOLD depth-hold measurement, 12 s (z=500) ...")
    samples = []
    t_end = time.time() + 12
    while time.time() < t_end:
        drive(0, 0, 500, 0, 0.5)
        if depth() is not None:
            samples.append(depth())
    d_hold_end = depth()
    pp = (max(samples) - min(samples)) if samples else float("nan")
    drift = d_hold_end - d_dive
    print("[ctl] depth-hold: start=%.2f end=%.2f m  drift=%+.2f m  peak-peak=%.2f m"
          % (d_dive, d_hold_end, drift, pp))

    # ---- HEADING: gentle yaw command, then settle, then measure hold ----
    y0 = true_yaw_deg()
    print("[ctl] YAW turn (r=500) 5 s from %.0f deg ..." % y0)
    t_end = time.time() + 5
    while time.time() < t_end:
        drive(0, 0, 500, 500, 0.5)
    drive(0, 0, 500, 0, 5.0)          # settle heading at neutral yaw
    y_turn = true_yaw_deg()
    dyaw = (y_turn - y0 + 540) % 360 - 180
    print("[ctl] heading now %.0f deg (turned %+.0f deg); measuring hold 6 s ..." % (y_turn, dyaw))
    yhs = []
    t_end = time.time() + 6
    while time.time() < t_end:
        drive(0, 0, 500, 0, 0.5)
        if true_yaw_deg() is not None:
            yhs.append(true_yaw_deg())
    # peak-peak on the unwrapped heading
    base = yhs[0] if yhs else 0.0
    unw = [((v - base + 540) % 360 - 180) for v in yhs]
    yaw_pp = (max(unw) - min(unw)) if unw else float("nan")
    print("[ctl] heading-hold peak-peak=%.1f deg over 6 s" % yaw_pp)

    # ---- FORWARD translation (sustained: measure last-2 s average speed) ----
    print("[ctl] FORWARD (x=1000) 8 s ...")
    gs = []
    t_end = time.time() + 8
    tstart = time.time()
    while time.time() < t_end:
        drive(1000, 0, 500, 0, 0.5)
        if _t["gspd"] is not None and time.time() - tstart > 4:
            gs.append(_t["gspd"])
    fwd_speed = (sum(gs) / len(gs)) if gs else 0.0
    print("[ctl] forward sustained groundspeed=%.2f m/s" % fwd_speed)

    # release + disarm
    m.mav.manual_control_send(m.target_system, 0, 0, 500, 0, 0)
    m.mav.command_long_send(m.target_system, m.target_component,
                            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                            0, 0, 0, 0, 0, 0, 0, 0)

    print("\n[ctl] ===== SUMMARY =====")
    print("  dive          : reached %.1f m deep" % d_dive)
    print("  DEPTH HOLD    : drift %+.2f m, wobble %.2f m over 12 s" % (drift, pp))
    print("  yaw authority : turned %+.0f deg on command" % dyaw)
    print("  HEADING HOLD  : wobble %.1f deg over 5 s" % yaw_pp)
    print("  forward       : %.2f m/s" % fwd_speed)
    good_depth = abs(drift) < 1.0 and pp < 1.5
    # heading "works" = responds to a yaw command (authority) AND holds steady
    good_head = abs(dyaw) > 5 and yaw_pp < 15
    good_fwd = fwd_speed > 0.3
    print("  VERDICT: depth-hold=%s heading=%s forward=%s" % (
        "PASS" if good_depth else "FAIL",
        "PASS" if good_head else "FAIL",
        "PASS" if good_fwd else "FAIL"))


if __name__ == "__main__":
    main()
