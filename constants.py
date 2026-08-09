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
# ArduPilot SITL only exposes 3 raw serial-emulated TCP ports (5760/5762/5763)
# and won't heartbeat a 2nd simultaneous client on the same one, so
# tools/test_target.py needs its own fan-out port to run concurrently with
# the dashboard (which already holds 5762/5763). .get() so existing
# profile.json files without this key keep working.
MAVLINK_TEST_TARGET_PORT = _profile["ports"]["mavlink"].get("test_target", MAVLINK_C2_REPLAY_PORT + 1)
# Dedicated port for the dashboard's own always-on "legitimate GPS_INPUT
# feeder" (see dashboard_server.py's legit_gps_feeder thread) -- a resilient
# twin's GPS1_TYPE=14 hardening means it has NO ambient GPS source at all
# unless something feeds it GPS_INPUT continuously, so without this it
# can never get a fix and can never arm (confirmed live 2026-08-09:
# GPS_RAW_INT.fix_type==1/no-fix, satellites_visible==0, on a freshly
# booted mass_resilient_cusv with nothing else running). Needs its own
# port, not a shared one -- reusing auto_mission's transient per-click
# connection would hit the same SO_REUSEADDR silent-port-stealing issue
# already root-caused and fixed once for goto() this session.
MAVLINK_GPS_FEEDER_PORT = _profile["ports"]["mavlink"].get("gps_feeder", MAVLINK_TEST_TARGET_PORT + 1)
# Same idea, underwater: EK3_SRC1_POSXY=6 (ExternalNav) on BOTH REMUS-100
# twins (vulnerable and hardened alike -- confirmed by reading both parm
# files, not assumed) means neither one has ANY ambient horizontal position
# source unless something feeds VISION_POSITION_ESTIMATE continuously.
# Previously that only happened when the dashboard's "Acoustic Spoof" button
# was clicked (attacks/acoustic_spoof.py's run_feed()) -- confirmed live
# 2026-08-09 that without it, GLOBAL_POSITION_INT never leaves HOME and
# goto() silently fails to enter AUTO (ArduSub rejects the mode switch, then
# arms into whatever mode it's actually in instead -- looks like "it armed
# but never moved" on the dashboard). Own dedicated port for the same
# SO_REUSEADDR reason as MAVLINK_GPS_FEEDER_PORT.
MAVLINK_VISION_FEEDER_PORT = _profile["ports"]["mavlink"].get("vision_feeder", MAVLINK_GPS_FEEDER_PORT + 1)

# --- Legitimate-operator GCS identity -----------------------------------
# The source_system this project's OWN legitimate control paths (MAVLink
# fan-out bridge, the dashboard's live-telemetry tap, its "sail to this
# point" navigation) should present as. Defaults to 255 (ArduPilot's
# out-of-the-box SYSID_MYGCS/MAV_GCS_SYSID convention), matching every
# vehicle's behavior before this field existed. A hardened vehicle profile
# sets this to whatever its own MAV_GCS_SYSID/MAV_OPTIONS=1 (GCS_SYSID_ENFORCE)
# defaults file configures as trusted (see vehicle_twins/*_resilient_*/), so
# this project's own legitimate tooling keeps working against it.
#
# Deliberately NOT used by anything that simulates an attacker
# (nodes/monitor/src/dashboard_server.py's cmd_conn(), tools/test_target.py's
# target connection) -- those stay at the plain ArduPilot default (255) on
# purpose, since that's what a real attacker without insider knowledge of a
# hardened vehicle's real GCS id would use. Whether that default gets
# accepted or rejected IS the security property being demonstrated.
GCS_SOURCE_SYSTEM = _profile.get("gcs_source_system", 255)

# --- Gazebo model name ---------------------------------------------------
# The <model name="..."> in this vehicle's own model.sdf, i.e. the
# "/model/<this>/..." prefix on its Gazebo topics. Mirrors run_sim.sh's own
# world.model_name read (falls back to the profile name, true for every
# vehicle so far since none renamed its Gazebo model away from its profile
# name). Needed by anything that taps a vehicle-specific Gazebo topic
# directly (e.g. attacks/acoustic_spoof.py's odometry read) instead of
# going through MAVLink, so a second underwater vehicle doesn't have to
# hardcode another vehicle's model name.
MODEL_NAME = _profile.get("world", {}).get("model_name", PROFILE_NAME)
