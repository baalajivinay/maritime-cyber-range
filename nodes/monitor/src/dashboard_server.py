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

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "detection"))
import constants
from detectors import DetectorSuite  # WO-24: live attack -> alert loop

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

# WO-24: one shared detector suite for the whole dashboard. The single AIS
# listener (ais_thread) feeds it, and so does the MAVLink detector loop -- so
# nothing double-binds the AIS UDP port.
_det_suite = DetectorSuite(constants.DOMAIN, cfg={"known_mmsi": constants.VESSEL_MMSI})


def _push_alerts(alerts):
    for a in alerts:
        socketio.emit('attack_alert', a.as_dict())


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
                        # same feed -> AIS detectors (ghost / impersonation)
                        _push_alerts(_det_suite.update({
                            "type": "ais", "t": time.time(),
                            "mmsi": decoded.mmsi, "lat": float(lat), "lon": float(lon)}))
            except Exception as e:
                # ignore decode errors
                pass
    except Exception as e:
        print(f"AIS thread error: {e}")

def detector_thread():
    """WO-24: run the domain's blind detectors on the live MAVLink feed and push
    each Alert to the browser as an 'attack_alert' event -- closing the
    attack->alert loop. Taps a spare ArduPilot MAVLink port (SERIAL2 tcp:5763) so
    it does not contend with the dashboard's own MAVLink feed. AIS events are fed
    to the same shared suite from ais_thread. Never reads ground truth."""
    suite = _det_suite
    push = _push_alerts

    label = f"{constants.DOMAIN.title()} — {constants.PROFILE_NAME} ({constants.ARDUPILOT_VEHICLE_TYPE})"
    while True:
        try:
            m = mavutil.mavlink_connection("tcp:127.0.0.1:5763")
            m.wait_heartbeat(timeout=15)
            m.mav.request_data_stream_send(m.target_system, m.target_component,
                                           mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
            mode_map = {v: k for k, v in m.mode_mapping().items()} if m.mode_mapping() else {}
            socketio.emit('status_update', {'vehicle': label})
            while True:
                msg = m.recv_match(blocking=True, timeout=1)
                if msg is None:
                    continue
                t = time.time()
                mt = msg.get_type()
                if mt == "GLOBAL_POSITION_INT":
                    push(suite.update({"type": "believed_pos", "t": t, "lat": msg.lat / 1e7, "lon": msg.lon / 1e7}))
                    socketio.emit('status_update', {'depth': msg.relative_alt / 1000.0})
                elif mt == "LOCAL_POSITION_NED":
                    push(suite.update({"type": "local_pos", "t": t, "n": msg.x, "e": msg.y, "d": msg.z, "vx": msg.vx, "vy": msg.vy}))
                elif mt == "VFR_HUD":
                    socketio.emit('status_update', {'speed': msg.groundspeed})
                elif mt == "HEARTBEAT" and msg.type != mavutil.mavlink.MAV_TYPE_GCS:
                    armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    push(suite.update({"type": "armed", "t": t, "armed": armed}))
                    socketio.emit('status_update', {'armed': armed, 'mode': mode_map.get(msg.custom_mode, str(msg.custom_mode))})
                elif mt == "RC_CHANNELS":
                    driven = [getattr(msg, f"chan{i}_raw", 0) for i in (1, 3)]
                    if any(900 < v < 2100 and abs(v - 1500) > 100 for v in driven):
                        push(suite.update({"type": "rc_override", "t": t, "domain": constants.DOMAIN}))
        except Exception as e:
            print(f"detector thread error: {e}; retrying in 3s")
            time.sleep(3)


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

    t_det = threading.Thread(target=detector_thread, daemon=True)  # WO-24
    t_det.start()

    socketio.run(app, host='0.0.0.0', port=8080, allow_unsafe_werkzeug=True)
    
    node.destroy_node()
    rclpy.shutdown()
