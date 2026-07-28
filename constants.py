"""
Vehicle profile loader -- single source of truth for values that used to
be duplicated (and had drifted) across the attack/node scripts: home
coordinates, the vessel's AIS identity, and the UDP/MAVLink ports each
component binds to.

WO-08: this used to be one hardcoded set of values for the WAM-V. It's now
a loader over profiles/<name>.json, selected via the MCR_VEHICLE_PROFILE
env var (defaults to "wamv"), so a second vehicle (e.g. an underwater
profile, see docs/ROADMAP.md Track U) can be added as a new JSON file
without touching this module or any of its callers.

The public attribute surface below (HOME_LAT, VESSEL_MMSI, FDM_RELAY_BIND,
etc.) is unchanged from before this loader existed -- every existing
`import constants; constants.HOME_LAT` call site keeps working as-is.

Import with:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import constants
"""

import json
import math
import os

PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")

# Meters-per-degree-latitude is ~constant everywhere (WGS84 approximation);
# meters-per-degree-longitude shrinks with cos(latitude). This is geodesy,
# not vehicle data, so it stays a true global constant rather than
# per-profile.
M_PER_DEG_LAT = 111320.0


def m_per_deg_lon(lat):
    return M_PER_DEG_LAT * math.cos(math.radians(lat))


_REQUIRED_KEYS = ("name", "domain", "ardupilot_vehicle_type", "home", "attacks", "ports")
_REQUIRED_HOME_KEYS = ("lat", "lon")
_REQUIRED_PORTS_KEYS = ("fdm_relay_bind", "fdm_gazebo_addr", "mavlink")
_REQUIRED_MAVLINK_KEYS = ("dashboard", "auto_mission", "c2_replay")
_REQUIRED_AIS_KEYS = ("mmsi", "vessel_name", "udp_addr")


def _require(d, keys, context):
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(
            f"Vehicle profile '{context}' is missing required key(s): {missing}"
        )


def load_profile(name):
    """Loads and validates profiles/<name>.json. Raises ValueError with a
    specific missing-key message on a malformed profile, rather than
    letting some downstream attack script fail on a confusing
    AttributeError/KeyError."""
    path = os.path.join(PROFILES_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise ValueError(f"No such vehicle profile: '{name}' (expected {path})")

    with open(path) as f:
        profile = json.load(f)

    _require(profile, _REQUIRED_KEYS, name)
    _require(profile["home"], _REQUIRED_HOME_KEYS, f"{name}.home")
    _require(profile["ports"], _REQUIRED_PORTS_KEYS, f"{name}.ports")
    _require(profile["ports"]["mavlink"], _REQUIRED_MAVLINK_KEYS, f"{name}.ports.mavlink")
    if profile.get("ais") is not None:
        _require(profile["ais"], _REQUIRED_AIS_KEYS, f"{name}.ais")

    return profile


_PROFILE_NAME = os.environ.get("MCR_VEHICLE_PROFILE", "wamv")
_profile = load_profile(_PROFILE_NAME)

# --- Profile metadata --------------------------------------------------
PROFILE_NAME = _profile["name"]
DOMAIN = _profile["domain"]                              # "surface" | "underwater"
ARDUPILOT_VEHICLE_TYPE = _profile["ardupilot_vehicle_type"]  # "Rover" | "Sub"
ATTACKS = _profile["attacks"]                             # applicable attack set

# --- Home coordinates ---------------------------------------------------
HOME_LAT = _profile["home"]["lat"]
HOME_LON = _profile["home"]["lon"]

# --- AIS identity (surface only -- None/omitted underwater, since AIS
# doesn't function while submerged) --------------------------------------
_ais = _profile.get("ais")
VESSEL_MMSI = _ais["mmsi"] if _ais else None
VESSEL_NAME = _ais["vessel_name"] if _ais else None
AIS_UDP_ADDR = tuple(_ais["udp_addr"]) if _ais else None

# --- FDM relay topology (Gazebo <-> ArduPilot SITL) --------------------
# ArduPilot always sends FDM requests to fdm_relay_bind's port. The relay
# binds there and forwards to Gazebo at fdm_gazebo_addr, whose
# ArduPilotPlugin <fdm_port_in> must match (see sim_config/*.sdf) so the
# relay can occupy the ArduPilot-facing port instead of Gazebo talking to
# ArduPilot directly.
FDM_RELAY_BIND = tuple(_profile["ports"]["fdm_relay_bind"])
FDM_GAZEBO_ADDR = tuple(_profile["ports"]["fdm_gazebo_addr"])

# --- MAVLink endpoints -----------------------------------------------
# Each consumer needs its own "output add 127.0.0.1:<port>" in the
# MAVProxy console (once per SITL session) so they don't collide on the
# same UDP port. These three MUST stay distinct.
MAVLINK_DASHBOARD_PORT = _profile["ports"]["mavlink"]["dashboard"]
MAVLINK_AUTO_MISSION_PORT = _profile["ports"]["mavlink"]["auto_mission"]
MAVLINK_C2_REPLAY_PORT = _profile["ports"]["mavlink"]["c2_replay"]
