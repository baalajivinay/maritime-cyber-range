import os
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_SDF = os.path.join(SCRIPT_DIR, 'wamv.sdf')
OUTPUT_SDF = os.path.join(SCRIPT_DIR, 'wamv_ardupilot.sdf')

tree = ET.parse(SOURCE_SDF)
root = tree.getroot()

model = root.find('model')

# Find base_link
base_link = None
for link in model.findall('link'):
    if link.get('name') == 'wamv/base_link':
        base_link = link
        break

if base_link is None:
    print("base_link not found")
    exit(1)

# Add IMU
imu = ET.SubElement(base_link, 'sensor', {'name': 'imu_sensor', 'type': 'imu'})
ET.SubElement(imu, 'always_on').text = '1'
ET.SubElement(imu, 'update_rate').text = '250'

# Add GPS
navsat = ET.SubElement(base_link, 'sensor', {'name': 'navsat_sensor', 'type': 'navsat'})
ET.SubElement(navsat, 'always_on').text = '1'
ET.SubElement(navsat, 'update_rate').text = '10'

# Add ArduPilotPlugin
plugin = ET.SubElement(model, 'plugin', {'name': 'ArduPilotPlugin', 'filename': 'ArduPilotPlugin'})
ET.SubElement(plugin, 'fdm_addr').text = '127.0.0.1'
# 9100, NOT ArduPilot's default 9002 -- the GPS-spoof relay (attacks/gps_spoof.py)
# needs to occupy 9002 itself, forwarding to Gazebo here at 9100. See
# docs/ARCHITECTURE.md for the full port topology.
ET.SubElement(plugin, 'fdm_port_in').text = '9100'
ET.SubElement(plugin, 'connectionTimeoutMaxCount').text = '5'
ET.SubElement(plugin, 'lock_step').text = '1'
ET.SubElement(plugin, 'modelXYZToAirplaneXForwardZDown', {'degrees': 'true'}).text = '0 0 0 180 0 0'
ET.SubElement(plugin, 'gazeboXYZToNED', {'degrees': 'true'}).text = '0 0 0 180 0 90'
ET.SubElement(plugin, 'imuName').text = 'wamv/base_link::imu_sensor'

# Left Throttle (Channel 0)
ctrl_left = ET.SubElement(plugin, 'control', {'channel': '0'})
ET.SubElement(ctrl_left, 'jointName').text = 'wamv/left_engine_propeller_joint'
ET.SubElement(ctrl_left, 'useForce').text = '1'
ET.SubElement(ctrl_left, 'multiplier').text = '100'
ET.SubElement(ctrl_left, 'offset').text = '-0.5'
ET.SubElement(ctrl_left, 'servo_min').text = '1000'
ET.SubElement(ctrl_left, 'servo_max').text = '2000'
ET.SubElement(ctrl_left, 'type').text = 'VELOCITY'
ET.SubElement(ctrl_left, 'p_gain').text = '10.0'
ET.SubElement(ctrl_left, 'i_gain').text = '0.0'
ET.SubElement(ctrl_left, 'd_gain').text = '0.0'
ET.SubElement(ctrl_left, 'i_max').text = '1'
ET.SubElement(ctrl_left, 'i_min').text = '-1'
ET.SubElement(ctrl_left, 'cmd_max').text = '100.0'
ET.SubElement(ctrl_left, 'cmd_min').text = '-100.0'

# Right Throttle (Channel 2)
ctrl_right = ET.SubElement(plugin, 'control', {'channel': '2'})
ET.SubElement(ctrl_right, 'jointName').text = 'wamv/right_engine_propeller_joint'
ET.SubElement(ctrl_right, 'useForce').text = '1'
ET.SubElement(ctrl_right, 'multiplier').text = '100'
ET.SubElement(ctrl_right, 'offset').text = '-0.5'
ET.SubElement(ctrl_right, 'servo_min').text = '1000'
ET.SubElement(ctrl_right, 'servo_max').text = '2000'
ET.SubElement(ctrl_right, 'type').text = 'VELOCITY'
ET.SubElement(ctrl_right, 'p_gain').text = '10.0'
ET.SubElement(ctrl_right, 'i_gain').text = '0.0'
ET.SubElement(ctrl_right, 'd_gain').text = '0.0'
ET.SubElement(ctrl_right, 'i_max').text = '1'
ET.SubElement(ctrl_right, 'i_min').text = '-1'
ET.SubElement(ctrl_right, 'cmd_max').text = '100.0'
ET.SubElement(ctrl_right, 'cmd_min').text = '-100.0'

tree.write(OUTPUT_SDF, encoding='utf-8', xml_declaration=True)
print(f"Saved to {OUTPUT_SDF}")
