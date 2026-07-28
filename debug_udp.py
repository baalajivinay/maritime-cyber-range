import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", 9002))
print("Bound to 9002")

while True:
    data, addr = sock.recvfrom(65535)
    print(f"Received {len(data)} bytes from {addr}: {data!r}")
