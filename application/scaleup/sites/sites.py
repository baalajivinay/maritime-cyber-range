"""Test-site model: loads a site's cited environment data and computes its
derived physics with the exact formulas in oceanography.py.

A SITE is an ENVIRONMENT overlay (current, density, sound-speed, depth) applied
to any twin running any attack -- it is orthogonal to the attack set. Pick a
site to change the water the vehicle sits in, not what you can do to it.
"""
import json
import math
import os
from dataclasses import dataclass, field
from . import oceanography as O

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


@dataclass
class Site:
    id: str
    name: str
    establishment: str
    position: list              # [lat, lon]
    region: str
    water: dict
    current: dict
    sea_state: dict
    acoustics: dict
    notes: str = ""

    # --- derived physics (exact equations, representative inputs) -----------
    def density(self):
        return O.density_eos80(self.water["surface_temp_c"], self.water["salinity_psu"])

    def sound_speed_profile(self):
        w = self.water
        return O.sound_speed_profile(
            surface_temp=w["surface_temp_c"], deep_temp=w["deep_temp_c"],
            salinity_psu=w["salinity_psu"], max_depth_m=w["max_depth_m"],
            mixed_layer_m=w.get("mixed_layer_m", 20), thermocline_bottom_m=w.get("thermocline_bottom_m", 150))

    def surface_sound_speed(self):
        return O.sound_speed_mackenzie(self.water["surface_temp_c"], self.water["salinity_psu"], 0.0)

    def sound_speed_at(self, depth_m=0.0):
        w = self.water
        t = O.temperature_at_depth(depth_m, w["surface_temp_c"], w["deep_temp_c"],
                                   w.get("mixed_layer_m", 20), w.get("thermocline_bottom_m", 150))
        return O.sound_speed_mackenzie(t, w["salinity_psu"], depth_m)

    def sonic_layer_depth(self):
        return O.sonic_layer_depth(self.sound_speed_profile())

    def usbl_detection_range(self):
        a = self.acoustics
        return O.detection_range_m(a["source_level_db"], a["det_threshold_db"], a["usbl_freq_khz"])

    def current_ne(self):
        """Current as (north, east) m/s from speed + bearing."""
        b = math.radians(self.current["bearing_deg"])
        v = self.current["speed_mps"]
        return (v * math.cos(b), v * math.sin(b))

    def environment(self):
        """One dict summarising the computed environment (for reports/JSON)."""
        prof = self.sound_speed_profile()
        return {
            "site": self.id, "name": self.name, "establishment": self.establishment,
            "position": self.position, "region": self.region,
            "water_density_kg_m3": round(self.density(), 2),
            "surface_sound_speed_mps": round(self.surface_sound_speed(), 2),
            "sonic_layer_depth_m": self.sonic_layer_depth(),
            "usbl_freq_khz": self.acoustics["usbl_freq_khz"],
            "usbl_detection_range_m": self.usbl_detection_range(),
            "current_speed_mps": self.current["speed_mps"],
            "current_bearing_deg": self.current["bearing_deg"],
            "current_type": self.current["type"],
            "max_depth_m": self.water["max_depth_m"],
            "sig_wave_height_m": self.sea_state.get("sig_wave_height_m"),
            "fidelity": self.water.get("fidelity", "A"),
            "sources": {
                "water": self.water.get("source"),
                "current": self.current.get("source"),
            },
            "profile": prof,
        }


def _from_dict(d):
    return Site(id=d["id"], name=d["name"], establishment=d.get("establishment", ""),
                position=d["position"], region=d.get("region", ""),
                water=d["water"], current=d["current"], sea_state=d.get("sea_state", {}),
                acoustics=d.get("acoustics", {}), notes=d.get("notes", ""))


def load_site(id_or_path):
    path = id_or_path if os.path.sep in id_or_path or id_or_path.endswith(".json") \
        else os.path.join(DATA_DIR, f"{id_or_path}.json")
    with open(path) as f:
        return _from_dict(json.load(f))


def list_sites():
    out = []
    for fn in sorted(os.listdir(DATA_DIR)):
        if fn.endswith(".json"):
            out.append(load_site(os.path.join(DATA_DIR, fn)))
    return out
