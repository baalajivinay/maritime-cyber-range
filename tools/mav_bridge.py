#!/usr/bin/env python3
"""
Standalone MAVLink fan-out bridge (WO-14).

Replaces MAVProxy's `output add` for headless/automated boots: MAVProxy needs
an interactive tty and exits immediately without one, so this project's SITL is
launched as a bare binary and this bridge provides the GCS link + fan-out.

Connects to ArduPilot's default GCS TCP link (tcp:127.0.0.1:5760) and mirrors
traffic bidirectionally to the UDP endpoints the attack/dashboard scripts expect
(see docs/ARCHITECTURE.md port map). Ports come from the active vehicle profile
via constants.py, so it is domain-agnostic (same 14551/14552/14553 for the WAM-V
and the BlueROV2 unless a profile overrides them).

Usage:  python3 tools/mav_bridge.py            # ports from MCR_VEHICLE_PROFILE
        python3 tools/mav_bridge.py 14551 14552 14553   # explicit override
"""
import os
import sys
import time
from pymavlink import mavutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import constants

MASTER_ADDR = os.environ.get("MCR_MAVLINK_MASTER", "tcp:127.0.0.1:5760")

if len(sys.argv) > 1:
    OUT_PORTS = [int(p) for p in sys.argv[1:]]
else:
    OUT_PORTS = [
        constants.MAVLINK_DASHBOARD_PORT,
        constants.MAVLINK_AUTO_MISSION_PORT,
        constants.MAVLINK_C2_REPLAY_PORT,
        constants.MAVLINK_TEST_TARGET_PORT,
        constants.MAVLINK_GPS_FEEDER_PORT,
        constants.MAVLINK_VISION_FEEDER_PORT,
    ]


def main():
    print(f"[mav_bridge] connecting to {MASTER_ADDR} (as GCS id {constants.GCS_SOURCE_SYSTEM}) ...", flush=True)
    master = mavutil.mavlink_connection(MASTER_ADDR, source_system=constants.GCS_SOURCE_SYSTEM)
    if master.wait_heartbeat(timeout=30) is None:
        print("[mav_bridge] ERROR: no heartbeat from ArduPilot within 30s", flush=True)
        sys.exit(1)
    print(f"[mav_bridge] heartbeat from system {master.target_system} "
          f"component {master.target_component}", flush=True)

    # Ask for a full telemetry stream so the dashboard/attacks see position etc.
    master.mav.request_data_stream_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)

    outs = {}
    for p in OUT_PORTS:
        c = mavutil.mavlink_connection(f"udpout:127.0.0.1:{p}")
        c.port.settimeout(0.0)
        outs[p] = c
    print(f"[mav_bridge] fanning out to UDP ports: {OUT_PORTS}", flush=True)

    down = up = 0
    last_report = time.time()
    while True:
        msg = master.recv_match(blocking=False)
        if msg is not None:
            raw = msg.get_msgbuf()
            for c in outs.values():
                try:
                    c.write(raw)
                except OSError:
                    pass
            down += 1

        for c in outs.values():
            try:
                data = c.port.recv(4096)
                if data:
                    master.write(data)
                    up += 1
            except (BlockingIOError, OSError):
                pass

        if time.time() - last_report > 30:
            print(f"[mav_bridge] down={down} up={up}", flush=True)
            last_report = time.time()

        if msg is None:
            time.sleep(0.005)


if __name__ == "__main__":
    main()
