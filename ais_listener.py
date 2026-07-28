import socket
import time
from pyais import decode

UDP_IP = "127.0.0.1"
UDP_PORT = 10110

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))
print(f"Listening on {UDP_IP}:{UDP_PORT}...")

while True:
    data, addr = sock.recvfrom(1024)
    ts = time.time()
    sentences = data.decode("ascii").strip().split('\r\n')
    for sentence in sentences:
        if not sentence:
            continue
        try:
            msg = decode(sentence)
            print(f"[{ts:.3f}] Type: {msg.msg_type} | MMSI: {msg.mmsi} | Lat: {getattr(msg, 'lat', 'N/A')} | Lon: {getattr(msg, 'lon', 'N/A')}")
        except Exception as e:
            print(f"[{ts:.3f}] Error decoding {sentence}: {e}")
