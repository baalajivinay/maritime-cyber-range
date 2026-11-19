"""
Target loader for maritime resilience testbed.
Resolves target profiles from application/twins/<name>/target.json or explicit paths.
"""
import os
import json

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TWINS_DIR = os.path.join(REPO, "application", "twins")

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
    """Loads and validates target json from path or twin name."""
    if os.path.exists(name_or_path):
        path = name_or_path
    else:
        # Check application/twins/<name>/target.json
        candidate = os.path.join(TWINS_DIR, name_or_path, "target.json")
        if os.path.exists(candidate):
            path = candidate
        else:
            candidate2 = os.path.join(TWINS_DIR, f"{name_or_path}.json")
            if os.path.exists(candidate2):
                path = candidate2
            else:
                raise ValueError(f"No such target: '{name_or_path}' (searched {candidate})")

    with open(path) as f:
        target = json.load(f)

    _require(target, _REQUIRED_KEYS, name_or_path)

    if target.get("authorized") is not True:
        raise ValueError(
            f"Target '{target.get('name', name_or_path)}' has authorized != true. "
            "Refusing to load. Set \"authorized\": true only if authorized."
        )

    if target["domain"] not in _VALID_DOMAINS:
        raise ValueError(f"Target '{name_or_path}': domain must be in {_VALID_DOMAINS}, got '{target['domain']}'")

    _require(target["mavlink"], _REQUIRED_MAVLINK_KEYS, f"{name_or_path}.mavlink")
    target["mavlink"].setdefault("source_system", 255)

    attacks = target.get("attacks", {})
    if "gps_spoof" in attacks and attacks["gps_spoof"].get("enabled"):
        gcfg = attacks["gps_spoof"]
        method = gcfg.get("method", "gps_input")
        if method not in _VALID_GPS_METHODS:
            raise ValueError(f"Target '{name_or_path}': invalid gps_spoof.method '{method}'")
        if method == "fdm_relay":
            _require(gcfg, _REQUIRED_FDM_RELAY_KEYS, f"{name_or_path}.attacks.gps_spoof")

    if "c2_replay" in attacks and attacks["c2_replay"].get("enabled"):
        attacks["c2_replay"].setdefault("allow_arm_and_actuate", False)

    target.setdefault("timing", {})
    target["timing"].setdefault("settle_s", 5.0)
    target["timing"].setdefault("window_s", 20.0)

    return target


def list_targets():
    out = []
    if os.path.isdir(TWINS_DIR):
        for entry in os.listdir(TWINS_DIR):
            if os.path.exists(os.path.join(TWINS_DIR, entry, "target.json")):
                out.append(entry)
    return sorted(out)
