"""
Target loader -- the connection-only contract for the resilience tester
(tools/test_target.py). A "target" is ANY ArduPilot vehicle (ours or someone
else's), described purely by how to reach it: a MAVLink connection string +
per-attack injection config. No SDF model, no world file, nothing this repo
needs to boot.

Deliberately separate from constants.py/profiles/*.json (which describe
vehicles THIS repo owns and boots via tools/run_sim.sh) -- this module never
imports constants.py, and profiles/*.json is never read here. Keeping these
two systems apart means nothing in this file can regress the existing
dashboard/demo/checkpoint trail, and vice versa.

Schema: see docs/TARGET_TESTING.md and any targets/*.json for worked
examples.

Safety: a target config MUST set "authorized": true. This is not a
technical control (a determined operator can edit the file), it is a
required, explicit, in-the-file attestation that the operator has
authorization to attack this target -- attacking a vehicle you don't own or
have permission to test is not something a config flag can prevent, only
make deliberate rather than accidental. load_target() refuses to return a
target that doesn't have it set.
"""
import json
import os

TARGETS_DIR = os.path.dirname(os.path.abspath(__file__))

_REQUIRED_KEYS = ("name", "domain", "authorized", "mavlink", "attacks")
_REQUIRED_MAVLINK_KEYS = ("connection",)
_VALID_DOMAINS = ("surface", "underwater")
_VALID_GPS_METHODS = ("gps_input", "fdm_relay")
_REQUIRED_FDM_RELAY_KEYS = ("bind", "gazebo_addr")


def _require(d, keys, context):
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"Target config '{context}' is missing required key(s): {missing}")


def load_target(name_or_path):
    """Loads and validates targets/<name>.json (or an explicit path ending
    in .json). Raises ValueError naming the specific problem -- a malformed
    or unauthorized target must fail loudly here, not partway through an
    attack."""
    path = name_or_path if name_or_path.endswith(".json") else os.path.join(TARGETS_DIR, f"{name_or_path}.json")
    if not os.path.exists(path):
        raise ValueError(f"No such target: '{name_or_path}' (expected {path})")

    with open(path) as f:
        target = json.load(f)

    _require(target, _REQUIRED_KEYS, name_or_path)

    if target["authorized"] is not True:
        raise ValueError(
            f"Target '{target.get('name', name_or_path)}' has authorized != true. "
            "Refusing to load. Set \"authorized\": true only if you have explicit "
            "authorization to attack this target."
        )

    if target["domain"] not in _VALID_DOMAINS:
        raise ValueError(f"Target '{name_or_path}': domain must be one of {_VALID_DOMAINS}, got '{target['domain']}'")

    _require(target["mavlink"], _REQUIRED_MAVLINK_KEYS, f"{name_or_path}.mavlink")
    # ArduPilot honors RC_CHANNELS_OVERRIDE (and possibly other GCS-privileged
    # traffic) only from the sender system ID matching SYSID_MYGCS, which
    # defaults to 255. That field is a plain, unauthenticated message header
    # value -- trivially spoofable, not a real control -- so testing with it
    # set to the DEFAULT expected GCS id is the correct vulnerability test (it
    # is exactly what a real attacker would do). Confirmed empirically:
    # source_system=250 makes ArduPilot silently drop the override with zero
    # error; 255 makes it take effect immediately. A target that changed
    # SYSID_MYGCS away from its default would legitimately show RESILIENT
    # here -- that IS a real (if lightweight) mitigation, and is exactly the
    # kind of candidate cause the RC-override verdict's evidence should note.
    target["mavlink"].setdefault("source_system", 255)

    attacks = target.get("attacks", {})
    if "gps_spoof" in attacks and attacks["gps_spoof"].get("enabled"):
        gcfg = attacks["gps_spoof"]
        method = gcfg.get("method", "gps_input")
        if method not in _VALID_GPS_METHODS:
            raise ValueError(f"Target '{name_or_path}': gps_spoof.method must be one of {_VALID_GPS_METHODS}, got '{method}'")
        if method == "fdm_relay":
            _require(gcfg, _REQUIRED_FDM_RELAY_KEYS, f"{name_or_path}.attacks.gps_spoof (method=fdm_relay)")

    if "c2_replay" in attacks and attacks["c2_replay"].get("enabled"):
        attacks["c2_replay"].setdefault("allow_arm_and_actuate", False)

    target.setdefault("timing", {})
    target["timing"].setdefault("settle_s", 5.0)
    target["timing"].setdefault("window_s", 20.0)

    return target


def list_targets():
    """Names of every targets/*.json file (not validated -- use
    load_target()/validate_target.py for that)."""
    return sorted(
        fn[:-5] for fn in os.listdir(TARGETS_DIR)
        if fn.endswith(".json")
    )
