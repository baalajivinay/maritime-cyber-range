"""
Harbor Traffic & Background Merchant Fleet + Multi-Contact COLREGS (Task 5).

Simulates 5-8 background vessels (cargo ships, pilot boats, passenger ferries)
transiting the Traffic Separation Schemes (TSS) of the supported harbours, and
a multi-contact COLREGS evaluator that lets own-ship compute CPA/TCPA for every
contact simultaneously and apply Rules 8, 13, 14, 15, 16 and 17 when several
crossing vessels are encountered at once.

Stdlib only; Qt-free so it is unit-testable in isolation.
"""
import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi

# Collision-risk gates for the COLREGS evaluator
SAFE_CPA_M = 120.0          # closest point of approach we will defend
TCPA_HORIZON_S = 200.0      # only contacts closing within this horizon matter
GIVE_WAY_STBD_DEG = 30.0    # substantial starboard alteration (Rule 8/16)

# Per-site Traffic Separation Scheme: lane axis bearing (deg true) and the
# lateral offset of the two opposing lanes (metres, +stbd of axis).
SITE_TSS = {
    "kochi":        {"axis_deg": 30.0,  "lane_offset_m": 130.0, "span_m": 650.0},
    "mumbai":       {"axis_deg": 345.0, "lane_offset_m": 160.0, "span_m": 720.0},
    "visakhapatnam": {"axis_deg": 70.0,  "lane_offset_m": 140.0, "span_m": 680.0},
}

VESSEL_TYPES = [
    ("cargo", 6.5, "Cargo"),
    ("cargo", 5.5, "Bulk Carrier"),
    ("tanker", 4.8, "Product Tanker"),
    ("ferry", 7.5, "Passenger Ferry"),
    ("pilot", 8.5, "Pilot Boat"),
    ("container", 6.0, "Container Ship"),
    ("coaster", 5.0, "Coaster"),
    ("tug", 4.0, "Harbour Tug"),
]


@dataclass
class TrafficVessel:
    mmsi: int
    name: str
    vtype: str
    east_m: float
    north_m: float
    course_deg: float
    speed_mps: float
    lane: int                     # 0 = inbound lane, 1 = outbound lane
    # live encounter assessment vs own-ship
    cpa_m: Optional[float] = None
    tcpa_s: Optional[float] = None
    risk: bool = False

    def velocity_ne(self) -> Tuple[float, float]:
        """Velocity as (East, North) m/s to match the (E, N) position order."""
        return (self.speed_mps * math.sin(self.course_deg * DEG_TO_RAD),
                self.speed_mps * math.cos(self.course_deg * DEG_TO_RAD))


def cpa_tcpa(own_pos, own_vel, tgt_pos, tgt_vel) -> Tuple[float, float]:
    """(CPA metres, TCPA seconds). Positions (E,N); velocities (Ve,Vn)."""
    dx = tgt_pos[0] - own_pos[0]
    dy = tgt_pos[1] - own_pos[1]
    dvx = tgt_vel[0] - own_vel[0]
    dvy = tgt_vel[1] - own_vel[1]
    vrel2 = dvx * dvx + dvy * dvy
    if vrel2 < 1e-6:
        return math.hypot(dx, dy), 0.0
    tcpa = -(dx * dvx + dy * dvy) / vrel2
    if tcpa < 0.0:
        return math.hypot(dx, dy), tcpa
    cx = dx + dvx * tcpa
    cy = dy + dvy * tcpa
    return math.hypot(cx, cy), tcpa


def relative_bearing(own_hdg_deg: float, own_pos, tgt_pos) -> float:
    """Bearing of target relative to own heading, in (-180, 180];
    positive = starboard side."""
    de = tgt_pos[0] - own_pos[0]
    dn = tgt_pos[1] - own_pos[1]
    abs_brg = math.degrees(math.atan2(de, dn)) % 360.0
    rel = (abs_brg - own_hdg_deg + 540.0) % 360.0 - 180.0
    return rel


def classify_encounter(own_hdg_deg: float, own_pos, tgt: TrafficVessel) -> str:
    """Classify the COLREGS encounter type from geometry.

    Returns one of: 'head_on' (R14), 'crossing_give_way' (R15/16),
    'crossing_stand_on' (R17), 'overtaking' (R13), 'none'.
    """
    rel = relative_bearing(own_hdg_deg, own_pos, (tgt.east_m, tgt.north_m))
    # Aspect: difference between courses
    course_diff = (tgt.course_deg - own_hdg_deg + 540.0) % 360.0 - 180.0

    if abs(rel) <= 15.0 and abs(abs(course_diff) - 180.0) <= 35.0:
        return "head_on"                       # Rule 14 reciprocal, ahead
    if abs(rel) > 112.5:
        # Target is abaft own beam; if it is faster and overtaking us it's R13.
        return "overtaking" if tgt.speed_mps > 0 else "none"
    # Crossing: give-way if target is on our starboard bow (Rule 15/16),
    # stand-on if on our port bow (Rule 17).
    if 15.0 < rel <= 112.5:
        return "crossing_give_way"
    if -112.5 <= rel < -15.0:
        return "crossing_stand_on"
    return "none"


@dataclass
class COLREGSDirective:
    action: str = "maintain"          # maintain | give_way | stand_on | alter
    rule: str = ""
    course_change_deg: float = 0.0    # +starboard
    worst_mmsi: Optional[int] = None
    worst_cpa_m: Optional[float] = None
    risk_count: int = 0


def evaluate_colregs(own_pos, own_hdg_deg: float, own_speed_mps: float,
                     contacts: List[TrafficVessel]) -> COLREGSDirective:
    """Assess every contact and return the governing own-ship action.

    When multiple crossing vessels are in risk simultaneously, the most
    imminent risk (smallest TCPA) governs, and a give-way obligation always
    dominates a stand-on one (Rules 8 & 16: take early, substantial action)."""
    own_vel = (own_speed_mps * math.sin(own_hdg_deg * DEG_TO_RAD),
               own_speed_mps * math.cos(own_hdg_deg * DEG_TO_RAD))

    risky: List[Tuple[TrafficVessel, str]] = []
    for c in contacts:
        cpa, tcpa = cpa_tcpa(own_pos, own_vel,
                             (c.east_m, c.north_m), c.velocity_ne())
        c.cpa_m, c.tcpa_s = cpa, tcpa
        c.risk = (cpa < SAFE_CPA_M and 0.0 <= tcpa <= TCPA_HORIZON_S)
        if c.risk:
            risky.append((c, classify_encounter(own_hdg_deg, own_pos, c)))

    d = COLREGSDirective(risk_count=len(risky))
    if not risky:
        return d

    # Prioritise give-way/head-on obligations; among those the most imminent.
    def priority(item):
        c, enc = item
        give = enc in ("head_on", "crossing_give_way", "overtaking")
        return (0 if give else 1, c.tcpa_s if c.tcpa_s is not None else 1e9)

    risky.sort(key=priority)
    worst, enc = risky[0]
    d.worst_mmsi = worst.mmsi
    d.worst_cpa_m = worst.cpa_m

    if enc == "head_on":
        d.action, d.rule, d.course_change_deg = "give_way", "Rule 14 (Head-On)", GIVE_WAY_STBD_DEG
    elif enc == "crossing_give_way":
        d.action, d.rule, d.course_change_deg = "give_way", "Rule 15/16 (Crossing Give-Way)", GIVE_WAY_STBD_DEG
    elif enc == "overtaking":
        d.action, d.rule, d.course_change_deg = "give_way", "Rule 13 (Overtaking)", GIVE_WAY_STBD_DEG
    elif enc == "crossing_stand_on":
        # Rule 17: hold course/speed, unless in extremis (very small CPA) then act.
        if worst.cpa_m is not None and worst.cpa_m < SAFE_CPA_M * 0.4:
            d.action, d.rule, d.course_change_deg = "alter", "Rule 17(b) (Stand-On In Extremis)", GIVE_WAY_STBD_DEG
        else:
            d.action, d.rule, d.course_change_deg = "stand_on", "Rule 17 (Stand-On)", 0.0
    return d


class HarborTrafficSim:
    """Background merchant fleet transiting a site's TSS lanes."""

    def __init__(self, site: str = "kochi", n_vessels: int = 6, seed: int = 7):
        self.rng = random.Random(seed)
        self.site = site
        self.n_vessels = max(5, min(8, n_vessels))
        self.vessels: List[TrafficVessel] = []
        self._spawn(site)

    def set_site(self, site: str):
        self.site = site
        self._spawn(site)

    def _tss(self) -> Dict[str, float]:
        return SITE_TSS.get(self.site, SITE_TSS["kochi"])

    def _spawn(self, site: str):
        self.vessels = []
        tss = self._tss()
        axis = tss["axis_deg"]
        span = tss["span_m"]
        off = tss["lane_offset_m"]
        axis_rad = axis * DEG_TO_RAD
        # Unit vectors: along-lane and across-lane
        ae, an = math.sin(axis_rad), math.cos(axis_rad)
        xe, xn = math.cos(axis_rad), -math.sin(axis_rad)

        for i in range(self.n_vessels):
            lane = i % 2                       # alternate inbound / outbound
            along = self.rng.uniform(-span, span)
            lateral = (off if lane == 0 else -off) + self.rng.uniform(-25, 25)
            e = along * ae + lateral * xe
            n = along * an + lateral * xn
            course = axis if lane == 0 else (axis + 180.0) % 360.0
            vt, base_spd, label = VESSEL_TYPES[i % len(VESSEL_TYPES)]
            speed = base_spd + self.rng.uniform(-0.6, 0.6)
            self.vessels.append(TrafficVessel(
                mmsi=419_100_000 + i,
                name=f"{label}-{i+1}",
                vtype=vt,
                east_m=e, north_m=n,
                course_deg=course, speed_mps=speed, lane=lane))

    def step(self, dt: float):
        tss = self._tss()
        span = tss["span_m"] * 1.1
        for v in self.vessels:
            ve, vn = v.velocity_ne()
            v.north_m += vn * dt
            v.east_m += ve * dt
            # Recycle a vessel that has run past the scheme extent
            if math.hypot(v.east_m, v.north_m) > span:
                self._recycle(v)

    def _recycle(self, v: TrafficVessel):
        tss = self._tss()
        axis_rad = tss["axis_deg"] * DEG_TO_RAD
        ae, an = math.sin(axis_rad), math.cos(axis_rad)
        xe, xn = math.cos(axis_rad), -math.sin(axis_rad)
        off = tss["lane_offset_m"]
        span = tss["span_m"]
        along = -span if v.lane == 0 else span
        lateral = off if v.lane == 0 else -off
        v.east_m = along * ae + lateral * xe
        v.north_m = along * an + lateral * xn
        v.cpa_m = v.tcpa_s = None
        v.risk = False

    # --------------------------------------------------------------- accessors
    def ais_tracks(self) -> List[Dict[str, Any]]:
        return [
            {"mmsi": v.mmsi, "name": v.name, "type": v.vtype,
             "east_m": v.east_m, "north_m": v.north_m,
             "course": v.course_deg, "speed": v.speed_mps,
             "cpa_m": v.cpa_m, "tcpa_s": v.tcpa_s, "risk": v.risk}
            for v in self.vessels
        ]

    def radar_tracks(self) -> List[Dict[str, Any]]:
        """Independent radar truth (not synthetic): real traffic is seen by
        radar as well as AIS, so it corroborates AIS contacts."""
        return [{"east_m": v.east_m, "north_m": v.north_m, "synthetic": False}
                for v in self.vessels]

    def evaluate(self, own_pos, own_hdg_deg, own_speed_mps) -> COLREGSDirective:
        return evaluate_colregs(own_pos, own_hdg_deg, own_speed_mps, self.vessels)
