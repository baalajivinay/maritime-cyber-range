"""
Diagnostic: tests whether accel_body's Z-axis sign is inverted relative
to what ArduPilot expects, which is the leading hypothesis for the
persistent "AHRS: DCM Roll/Pitch inconsistent ~179 deg" pre-arm failure.

Evidence for this hypothesis:
- ArduPilot's own SIM_Aircraft.h defines the expected at-rest accel_body
  as (0, 0, -GRAVITY_MSS) -- negative Z.
- Every FDM packet captured throughout this project has shown accel_body
  z as positive (~+9.7 to +9.9).
- The frame transform config (modelXYZToAirplaneXForwardZDown) already
  matches ArduPilot's own official rover/boat reference examples exactly,
  so the bug is likely not there -- more likely the IMU sensor's own
  orientation in the SDF, or how the plugin packs accel specifically
  (separately from position/quaternion, which we've confirmed are correct).

This is PURELY DIAGNOSTIC -- same relay architecture as
00_inspect_fdm_protocol_v2.py, but negates accel_body's Z component
(and prints both original and corrected values) before forwarding. If
the pre-arm error disappears with this running, the hypothesis is
confirmed and we know exactly what to fix permanently (most likely the
IMU sensor's <pose> in wamv_ardupilot.sdf, so this relay isn't needed
long-term).

SETUP: same as before -- wamv_ardupilot.sdf's ArduPilotPlugin
<fdm_port_in> must be 9100 (Gazebo moved off the default 9002).
"""

import socket
import json
import threading

RELAY_BIND = ("127.0.0.1", 9002)
GAZEBO_ADDR = ("127.0.0.1", 9100)

# Toggle this to test different hypotheses without editing more code.
FLIP_Z = True
FLIP_X = False
FLIP_Y = False


def run_relay():
    ardupilot_facing = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ardupilot_facing.bind(RELAY_BIND)
    gazebo_facing = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ardupilot_facing.settimeout(0.01)
    gazebo_facing.settimeout(0.01)

    print(f"Diagnostic relay: bound {RELAY_BIND}, Gazebo at {GAZEBO_ADDR}")
    print(f"FLIP_Z={FLIP_Z}, FLIP_X={FLIP_X}, FLIP_Y={FLIP_Y}")
    print("Watch MAVProxy and try 'arm throttle' while this runs.\n")

    ardupilot_addr = None
    packet_count = 0

    while True:
        try:
            data, addr = ardupilot_facing.recvfrom(65535)
            if ardupilot_addr != addr:
                ardupilot_addr = addr
                print(f"ArduPilot address: {addr}")
            gazebo_facing.sendto(data, GAZEBO_ADDR)
        except socket.timeout:
            pass

        try:
            reply, _ = gazebo_facing.recvfrom(65535)
            try:
                payload = json.loads(reply.decode("utf-8"))
                orig = list(payload["imu"]["accel_body"])
                if FLIP_X:
                    payload["imu"]["accel_body"][0] *= -1
                if FLIP_Y:
                    payload["imu"]["accel_body"][1] *= -1
                if FLIP_Z:
                    payload["imu"]["accel_body"][2] *= -1

                packet_count += 1
                if packet_count % 250 == 0:
                    print(f"packet {packet_count}: orig accel_body={orig} "
                          f"-> corrected={payload['imu']['accel_body']}")

                out_bytes = json.dumps(payload).encode("utf-8") + b"\n"
            except (json.JSONDecodeError, KeyError):
                out_bytes = reply

            if ardupilot_addr:
                ardupilot_facing.sendto(out_bytes, ardupilot_addr)
        except socket.timeout:
            pass


if __name__ == "__main__":
    run_relay()
