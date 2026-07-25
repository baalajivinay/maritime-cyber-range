"""
CORRECTED VERSION. Run this after moving Gazebo's fdm_port_in to 9100
(see SDF edit instructions). This replaces the earlier version, which
incorrectly assumed Gazebo's fdm_port_in was a redirectable "send to"
port -- source inspection showed ArduPilot's SIM_JSON.cpp never binds a
fixed local port at all; its socket is unbound and gets an ephemeral
port on first send(). The only fixed rendezvous point in the whole
system is ArduPilot's send target: 127.0.0.1:9002 (target_ip/control_port
in SIM_JSON.h). So the relay now sits AT 9002 (where Gazebo used to be),
and forwards to the real Gazebo, now moved to 9100.

Purely observational still -- prints packets in both directions,
modifies nothing. Confirms the relay placement is correct before
gps_spoof.py (also being corrected) does anything with the data.
"""

import socket
import json

RELAY_BIND = ("127.0.0.1", 9002)     # ArduPilot always sends here -- we take this spot
GAZEBO_ADDR = ("127.0.0.1", 9100)    # Gazebo moved here via SDF edit

ardupilot_facing = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
ardupilot_facing.bind(RELAY_BIND)

gazebo_facing = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print(f"Relay bound at {RELAY_BIND} (ArduPilot's expected target)")
print(f"Forwarding to real Gazebo at {GAZEBO_ADDR}")
print("Waiting for first packet from ArduPilot...\n")

ardupilot_addr = None
packet_count = 0

ardupilot_facing.settimeout(0.01)
gazebo_facing.settimeout(0.01)

while True:
    # Direction 1: ArduPilot -> relay -> Gazebo (servo/control packets)
    try:
        data, addr = ardupilot_facing.recvfrom(65535)
        if ardupilot_addr != addr:
            ardupilot_addr = addr
            print(f"ArduPilot address learned/updated: {addr}")
        packet_count += 1
        if packet_count <= 3:
            print(f"[ArduPilot->Gazebo] packet #{packet_count}, {len(data)} bytes "
                  f"(this is a servo_packet, binary, NOT JSON -- expected)")
        gazebo_facing.sendto(data, GAZEBO_ADDR)
    except socket.timeout:
        pass

    # Direction 2: Gazebo -> relay -> ArduPilot (FDM/sensor reply -- THIS is what
    # carries GPS data, and this is what gps_spoof.py will need to modify)
    try:
        reply, _ = gazebo_facing.recvfrom(65535)
        if packet_count % 250 == 0:
            try:
                payload = json.loads(reply.decode("utf-8"))
                print(f"[Gazebo->ArduPilot] FDM packet, parsed as JSON:")
                print(json.dumps(payload, indent=2)[:2000])
                print()
            except json.JSONDecodeError:
                print(f"[Gazebo->ArduPilot] {len(reply)} bytes, NOT valid JSON -- "
                      f"first 80 bytes: {reply[:80]!r}")
        if ardupilot_addr:
            ardupilot_facing.sendto(reply, ardupilot_addr)
    except socket.timeout:
        pass

# WHAT TO DO WITH THE OUTPUT:
# The [Gazebo->ArduPilot] direction is what matters -- find the lat/lon
# (or NED position) field structure in that printed JSON, same as before.
# Report it back before I finalize the corrected gps_spoof.py.
