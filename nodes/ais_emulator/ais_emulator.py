#!/usr/bin/env python3
import json
import os
import sys
import socket
import shutil
import subprocess
import re
import math
import time
import threading
from pyais.encode import encode_dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import constants

# AIS Emulator Node
# Assumptions:
# - Phase-1 Simplification: Subscribing to TRUE Gazebo pose directly for AIS rather than noisy GPS + filtering.
# - Broadcasts NMEA AIVDM sentences over UDP to 127.0.0.1:10110

UDP_IP, UDP_PORT = constants.AIS_UDP_ADDR

# World origin (per active vehicle profile)
WORLD_LAT = constants.HOME_LAT
WORLD_LON = constants.HOME_LON
M_PER_DEG_LAT = constants.M_PER_DEG_LAT
M_PER_DEG_LON = constants.m_per_deg_lon(WORLD_LAT)

MMSI = constants.VESSEL_MMSI
VESSEL_NAME = constants.VESSEL_NAME

# Model + world name come from the active profile's "world" config (same
# pattern dashboard_server.py and run_attack_suite.py use) -- NOT hardcoded
# to "wamv"/"sydney_regatta". Confirmed bug (2026-08-08): this used to be
# hardcoded, so with MCR_VEHICLE_PROFILE=blueboat (model "blueboat", world
# "surface_harbor") this emulator subscribed to a Gazebo topic that never
# existed, silently broadcasting a fixed, non-moving position at the world
# origin for the entire session instead of the vessel's real pose.
try:
    _world = json.load(open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "profiles", constants.PROFILE_NAME + ".json"))).get("world", {})
except Exception:
    _world = {}
MODEL_NAME = _world.get("model_name", constants.PROFILE_NAME)
WORLD_NAME = _world.get("world_name", "sydney_regatta")
GZ_POSE_TOPIC = f"/world/{WORLD_NAME}/dynamic_pose/info"
POSE_STALE_WARN_S = 10.0  # warn if no live pose update arrives within this long

class AISEmulator:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        self.x = 0.0
        self.y = 0.0
        self.lat = WORLD_LAT
        self.lon = WORLD_LON
        self.heading = 0.0
        
        self.speed_knots = 0.0
        self.course_deg = 0.0
        self.rot_deg_min = 0.0
        
        self.last_pos_time = time.time()
        self.last_x = 0.0
        self.last_y = 0.0
        self.last_heading = 0.0
        
        self.last_type1_time = 0
        self.last_type5_time = 0

        self.running = True
        self._stale_warned = False

    def calculate_heading(self, x, y, z, w):
        # Yaw from quaternion
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        
        heading_deg = (math.degrees(yaw) * -1) + 90
        if heading_deg < 0:
            heading_deg += 360
        return heading_deg % 360

    def parse_gz_pose(self):
        # We spawn gz topic to get true pose
        if shutil.which('gz') is None:
            print("ERROR: 'gz' binary not found on PATH -- the AIS emulator "
                  "cannot read the vessel's true pose and will keep broadcasting "
                  "a fixed position at the world origin. Is Gazebo installed and "
                  "on PATH in this shell?")
            return
        proc = subprocess.Popen(
            ['gz', 'topic', '-e', '-t', GZ_POSE_TOPIC],
            stdout=subprocess.PIPE, text=True
        )
        
        current_block = ""
        in_wamv = False
        
        for line in proc.stdout:
            if not self.running:
                break
                
            if f'name: "{MODEL_NAME}"' in line:
                in_wamv = True
                current_block = line
                continue
                
            if in_wamv:
                current_block += line
                if 'orientation {' in current_block and 'w:' in line: # End of wamv block roughly
                    # Parse block
                    px = re.search(r'position {\s*x:\s*([-\d\.e]+)', current_block)
                    py = re.search(r'position {.*y:\s*([-\d\.e]+)', current_block.replace('\n', ''))
                    
                    ox = re.search(r'orientation {\s*x:\s*([-\d\.e]+)', current_block)
                    oy = re.search(r'orientation {.*y:\s*([-\d\.e]+)', current_block.replace('\n', ''))
                    oz = re.search(r'orientation {.*z:\s*([-\d\.e]+)', current_block.replace('\n', ''))
                    ow = re.search(r'orientation {.*w:\s*([-\d\.e]+)', current_block.replace('\n', ''))
                    
                    if px and py and ox and oy and oz and ow:
                        self.update_pose(
                            float(px.group(1)), float(py.group(1)),
                            float(ox.group(1)), float(oy.group(1)), float(oz.group(1)), float(ow.group(1))
                        )
                    
                    in_wamv = False
                    current_block = ""

    def update_pose(self, x, y, ox, oy, oz, ow):
        now = time.time()
        dt = now - self.last_pos_time
        if dt < 0.1:
            return # rate limit processing
            
        self.x = x
        self.y = y
        self.lat = WORLD_LAT + (y / M_PER_DEG_LAT)
        self.lon = WORLD_LON + (x / M_PER_DEG_LON)
        self.heading = self.calculate_heading(ox, oy, oz, ow)
        
        # Calculate velocity and course
        dx = x - self.last_x
        dy = y - self.last_y
        dist = math.sqrt(dx*dx + dy*dy)
        
        if dt > 0:
            speed_ms = dist / dt
            self.speed_knots = speed_ms * 1.94384
            
            if speed_ms > 0.1:
                # Course over ground
                course_rad = math.atan2(dx, dy)
                self.course_deg = math.degrees(course_rad)
                if self.course_deg < 0: self.course_deg += 360
                
            # ROT (Rate of Turn)
            dheading = self.heading - self.last_heading
            if dheading > 180: dheading -= 360
            if dheading < -180: dheading += 360
            self.rot_deg_min = (dheading / dt) * 60.0
            
        self.last_x = x
        self.last_y = y
        self.last_heading = self.heading
        self.last_pos_time = now

    def get_report_interval(self):
        # ITU-R M.1371 dynamic intervals for Class A
        if self.speed_knots <= 3.0:
            return 180.0
        elif self.speed_knots <= 14.0:
            return 3.33 if abs(self.rot_deg_min) > 10 else 10.0
        elif self.speed_knots <= 23.0:
            return 2.0 if abs(self.rot_deg_min) > 10 else 6.0
        else:
            return 2.0

    def broadcast(self, sentences):
        for s in sentences:
            self.sock.sendto(s.encode(), (UDP_IP, UDP_PORT))

    def run(self):
        t = threading.Thread(target=self.parse_gz_pose, daemon=True)
        t.start()
        
        print(f"AIS Emulator started. Broadcasting on {UDP_IP}:{UDP_PORT}")
        
        while self.running:
            now = time.time()

            if now - self.last_pos_time > POSE_STALE_WARN_S:
                if not self._stale_warned:
                    print(f"WARNING: no live pose update from '{GZ_POSE_TOPIC}' in "
                          f"{POSE_STALE_WARN_S:.0f}s -- is Gazebo/VRX actually running? "
                          f"Broadcasting stale/default position until it recovers.")
                    self._stale_warned = True
            else:
                self._stale_warned = False

            # Type 1 Message
            interval = self.get_report_interval()
            if now - self.last_type1_time >= interval:
                data1 = {
                    'type': 1,
                    'mmsi': MMSI,
                    'status': 0, # Under way using engine
                    'turn': min(max(int(self.rot_deg_min), -126), 126) if abs(self.rot_deg_min) < 708 else -127,
                    'speed': min(self.speed_knots, 102.2),
                    'accuracy': 1, # High accuracy
                    'lon': self.lon,
                    'lat': self.lat,
                    'course': self.course_deg,
                    'heading': int(self.heading),
                    'second': int(time.gmtime().tm_sec),
                    'maneuver': 0,
                    'radio': 0
                }
                try:
                    encoded1 = encode_dict(data1)
                    self.broadcast(encoded1)
                    self.last_type1_time = now
                except Exception as e:
                    print("Encode error Type 1:", e)

            # Type 5 Message (Static Data)
            # Normally 6 mins (360s), using 30s for verification test per requirements
            if now - self.last_type5_time >= 30:
                data5 = {
                    'type': 5,
                    'mmsi': MMSI,
                    'ais_version': 2,
                    'imo': 0,
                    'callsign': 'W1234',
                    'shipname': VESSEL_NAME,
                    'shiptype': 31, # Towing
                    'to_bow': 2,
                    'to_stern': 3,
                    'to_port': 1,
                    'to_starboard': 1,
                    'epfd': 1, # GPS
                    'month': 0,
                    'day': 0,
                    'hour': 24,
                    'minute': 60,
                    'draught': 0.1,
                    'destination': 'SYDNEY REGATTA',
                    'dte': 0
                }
                try:
                    encoded5 = encode_dict(data5)
                    self.broadcast(encoded5)
                    self.last_type5_time = now
                except Exception as e:
                    print("Encode error Type 5:", e)
                    
            time.sleep(0.5)

if __name__ == '__main__':
    emulator = AISEmulator()
    try:
        emulator.run()
    except KeyboardInterrupt:
        emulator.running = False
