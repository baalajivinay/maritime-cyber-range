"""Scenario schema + JSON loader (stdlib only).

A scenario composes the project's EXISTING attacks into a timed mission and
declares the operational consequences that count as mission impact. Example:
see scenarios/*.json.

Schema (JSON):
{
  "name": "...", "description": "...",
  "target": "vehicle_twins/mass_vulnerable_cusv/target.json",
  "domain": "surface",
  "mission": {                         # the planned track the autonomy flies
     "start":  [lat, lon],
     "goal":   [lat, lon],
     "speed_mps": 3.0
  },
  "hazards": [                         # geometry used by consequence checks
     {"type": "nogo_zone", "name": "shipping_lane", "polygon": [[lat,lon],...]},
     {"type": "shoal",     "name": "sandbar", "point": [lat,lon], "radius_m": 60}
  ],
  "contacts": [                        # optional moving vessels for CPA checks
     {"name": "ferry", "start": [lat,lon], "velocity_ne_mps": [0.0, 2.0]}
  ],
  "timeline": [                        # attack steps, times relative to t0
     {"at_s": 0,  "action": "baseline"},
     {"at_s": 10, "action": "gps_spoof",
      "params": {"method": "fdm_relay", "profile": "ramp",
                 "bearing_deg": 270, "rate_mps": 0.6}},
     {"at_s": 90, "action": "stop_attacks"}
  ],
  "consequences": [
     {"type": "position_divergence", "threshold_m": 50, "severity": "high"},
     {"type": "nogo_breach", "zone": "shipping_lane", "severity": "critical"},
     {"type": "grounding",  "hazard": "sandbar", "severity": "critical"},
     {"type": "cpa_violation", "contact": "ferry", "threshold_m": 100, "severity": "critical"}
  ],
  "sim": {"duration_s": 120, "rate_hz": 5}   # used by the SimExecutor only
}
"""
import json
from dataclasses import dataclass, field
from ..sites import load_site


@dataclass
class TimelineStep:
    at_s: float
    action: str                       # baseline | gps_spoof | c2_mode | c2_rc | acoustic_spoof | stop_attacks
    params: dict = field(default_factory=dict)


@dataclass
class Hazard:
    type: str                         # nogo_zone | shoal
    name: str
    polygon: list = field(default_factory=list)      # nogo_zone
    point: list = None                               # shoal [lat,lon]
    radius_m: float = 0.0


@dataclass
class Contact:
    name: str
    start: list                       # [lat, lon]
    velocity_ne_mps: list             # [north, east]


@dataclass
class Consequence:
    type: str                         # position_divergence | nogo_breach | grounding | cpa_violation
    severity: str = "medium"          # low | medium | high | critical
    threshold_m: float = 0.0
    zone: str = None
    hazard: str = None
    contact: str = None


@dataclass
class Scenario:
    name: str
    description: str
    target: str
    domain: str
    mission: dict
    hazards: list
    contacts: list
    timeline: list
    consequences: list
    sim: dict
    site: object = None        # a sites.Site (its current/density/sound-speed apply), or None

    def hazard(self, name):
        return next((h for h in self.hazards if h.name == name), None)

    def contact(self, name):
        return next((c for c in self.contacts if c.name == name), None)


def apply_site(scenario, site):
    """Translate a scenario's whole geometry to a site's position and attach the
    site (so its current/density/sound-speed apply). Lets one scenario -- with
    its full attack timeline -- run unchanged at any of the 3 sites."""
    dlat = site.position[0] - scenario.mission["start"][0]
    dlon = site.position[1] - scenario.mission["start"][1]
    mv = lambda p: [p[0] + dlat, p[1] + dlon]
    scenario.mission["start"] = mv(scenario.mission["start"])
    scenario.mission["goal"] = mv(scenario.mission["goal"])
    for h in scenario.hazards:
        if h.polygon:
            h.polygon = [mv(v) for v in h.polygon]
        if h.point:
            h.point = mv(h.point)
    for c in scenario.contacts:
        c.start = mv(c.start)
    scenario.site = site
    return scenario


def load_scenario(path):
    with open(path) as f:
        d = json.load(f)
    return Scenario(
        name=d["name"],
        description=d.get("description", ""),
        target=d.get("target", ""),
        domain=d.get("domain", "surface"),
        mission=d.get("mission", {}),
        hazards=[Hazard(**h) for h in d.get("hazards", [])],
        contacts=[Contact(**c) for c in d.get("contacts", [])],
        timeline=sorted((TimelineStep(**s) for s in d.get("timeline", [])), key=lambda s: s.at_s),
        consequences=[Consequence(**c) for c in d.get("consequences", [])],
        sim=d.get("sim", {"duration_s": 120, "rate_hz": 5}),
        site=load_site(d["site"]) if d.get("site") else None,
    )
