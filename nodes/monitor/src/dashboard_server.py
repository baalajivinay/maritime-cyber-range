import os
import sys
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix
from flask import Flask, render_template
from flask_socketio import SocketIO
import threading
import time
from pymavlink import mavutil
from pyais.stream import UDPReceiver
from pyais.messages import MessageType1, MessageType2, MessageType3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
import constants

app = Flask(__name__)
# Force threading mode so rclpy and standard threads work correctly
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

class GPSMonitorNode(Node):
    def __init__(self):
        super().__init__('gps_monitor_dashboard')
        self.subscription = self.create_subscription(
            NavSatFix,
            '/wamv/sensors/gps/gps/fix',
            self.listener_callback,
            10)

    def listener_callback(self, msg):
        server_recv_time = time.time()
        
        # Log side-by-side on server
        timestamp_str = f"{msg.header.stamp.sec}.{msg.header.stamp.nanosec:09d}"
        
        # Forward to Flask-SocketIO clients
        socketio.emit('gps_true_update', {
            'lat': msg.latitude,
            'lon': msg.longitude,
            'timestamp': timestamp_str,
            'server_recv_time': server_recv_time
        })

def mavlink_thread():
    try:
        master = mavutil.mavlink_connection(f'udpin:127.0.0.1:{constants.MAVLINK_DASHBOARD_PORT}')
        while True:
            msg = master.recv_match(type='GLOBAL_POSITION_INT', blocking=True)
            if msg:
                lat = msg.lat / 1e7
                lon = msg.lon / 1e7
                server_recv_time = time.time()
                socketio.emit('gps_believed_update', {
                    'lat': lat,
                    'lon': lon,
                    'server_recv_time': server_recv_time
                })
    except Exception as e:
        print(f"MAVLink thread error: {e}")

def ais_thread():
    try:
        ais_ip, ais_port = constants.AIS_UDP_ADDR
        for msg in UDPReceiver(ais_ip, ais_port):
            try:
                decoded = msg.decode()
                # Check if it has lat/lon
                if hasattr(decoded, 'lat') and hasattr(decoded, 'lon'):
                    lat = decoded.lat
                    lon = decoded.lon
                    if lat and lon: # Sometimes they can be None or default
                        socketio.emit('ais_update', {
                            'mmsi': decoded.mmsi,
                            'lat': float(lat),
                            'lon': float(lon)
                        })
            except Exception as e:
                # ignore decode errors
                pass
    except Exception as e:
        print(f"AIS thread error: {e}")

@app.route('/')
def index():
    return render_template('index.html')

def ros_spin_thread(node):
    rclpy.spin(node)

if __name__ == '__main__':
    rclpy.init()
    node = GPSMonitorNode()
    t_ros = threading.Thread(target=ros_spin_thread, args=(node,), daemon=True)
    t_ros.start()
    
    t_mav = threading.Thread(target=mavlink_thread, daemon=True)
    t_mav.start()
    
    t_ais = threading.Thread(target=ais_thread, daemon=True)
    t_ais.start()
    
    socketio.run(app, host='0.0.0.0', port=8080, allow_unsafe_werkzeug=True)
    
    node.destroy_node()
    rclpy.shutdown()
