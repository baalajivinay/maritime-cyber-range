import socket
import json

RELAY_BIND = ("127.0.0.1", 9002)
GAZEBO_ADDR = ("127.0.0.1", 9100)

ardupilot_facing = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
ardupilot_facing.bind(RELAY_BIND)
gazebo_facing = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print(f"Relay bound at {RELAY_BIND}")
print(f"Forwarding to real Gazebo at {GAZEBO_ADDR}")

ardupilot_addr = None
packet_count = 0

ardupilot_facing.settimeout(0.01)
gazebo_facing.settimeout(0.01)

while True:
    try:
        data, addr = ardupilot_facing.recvfrom(65535)
        if ardupilot_addr != addr:
            ardupilot_addr = addr
            print(f"ArduPilot address learned/updated: {addr}")
        packet_count += 1
        if packet_count <= 3:
            print(f"[ArduPilot->Gazebo] packet #{packet_count}, {len(data)} bytes: {data!r}")
        gazebo_facing.sendto(data, GAZEBO_ADDR)
    except socket.timeout:
        pass

    try:
        reply, _ = gazebo_facing.recvfrom(65535)
        if packet_count % 250 == 0:
            try:
                payload = json.loads(reply.decode("utf-8"))
                print(f"[Gazebo->ArduPilot] JSON: {json.dumps(payload)}")
            except Exception as e:
                print(f"[Gazebo->ArduPilot] not json: {reply[:80]!r}")
        if ardupilot_addr:
            ardupilot_facing.sendto(reply, ardupilot_addr)
    except socket.timeout:
        pass
