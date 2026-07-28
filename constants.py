"""
Single source of truth for values that used to be duplicated (and had
drifted) across the attack/node scripts: home coordinates, the vessel's
AIS identity, and the UDP/MAVLink ports each component binds to.

Import with:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import constants
"""

import math

# --- Sim world origin (sydney_regatta) --------------------------------
HOME_LAT = -33.724223
HOME_LON = 150.679736

# Meters-per-degree-latitude is ~constant everywhere; meters-per-degree
# longitude shrinks with cos(latitude). Previously ais_emulator.py used
# 111111.0 while every other script used 111320.0 -- 111320.0 is the
# standard WGS84 approximation and is now the only value in the codebase.
M_PER_DEG_LAT = 111320.0


def m_per_deg_lon(lat=HOME_LAT):
    return M_PER_DEG_LAT * math.cos(math.radians(lat))


# --- AIS identity (was duplicated as int in ais_spoof.py and str in
# ais_emulator.py -- pyais accepts either, but a single shared value
# means the two can never drift apart) ---------------------------------
VESSEL_MMSI = "123456789"
VESSEL_NAME = "WAMV-CYBER"
AIS_UDP_ADDR = ("127.0.0.1", 10110)

# --- FDM relay topology (Gazebo <-> ArduPilot SITL) --------------------
# ArduPilot always sends FDM requests to 9002. The relay binds 9002 and
# forwards to Gazebo, which must have its ArduPilotPlugin <fdm_port_in>
# pointed at 9100 (see sim_config/wamv_ardupilot.sdf) so the relay can
# occupy 9002 instead of Gazebo talking to ArduPilot directly.
FDM_RELAY_BIND = ("127.0.0.1", 9002)
FDM_GAZEBO_ADDR = ("127.0.0.1", 9100)

# --- MAVLink endpoints -----------------------------------------------
# Each consumer needs its own "output add 127.0.0.1:<port>" in the
# MAVProxy console (once per SITL session) so they don't collide on the
# same UDP port. These three MUST stay distinct.
MAVLINK_DASHBOARD_PORT = 14551
MAVLINK_AUTO_MISSION_PORT = 14552
MAVLINK_C2_REPLAY_PORT = 14553
