#!/usr/bin/env python3
"""
Autonomous COLREGs Collision Avoidance Engine for Unmanned Surface Vessels.

Eliminates the "AIS vulnerability N/A" limitation by providing the autonomous
decision-making layer that consumes AIS broadcasts, calculates Closest Point of
Approach (CPA / TCPA), and executes IMO COLREGs compliance maneuvers (Rule 14
Head-on and Rule 15 Crossing Give-Way).

When an attacker spoofs an AIS ghost vessel on a collision trajectory, this
engine detects the breach of the safety domain and computes the physical
course deflection (turning to starboard) required to avoid collision, proving
the cyber-physical impact of AIS spoofing on USV navigation.
"""

import math
import time
from typing import Dict, List, Optional, Tuple

_M_PER_DEG_LAT = 111320.0


def _m_per_deg_lon(lat: float) -> float:
    return _M_PER_DEG_LAT * math.cos(math.radians(lat))


def calculate_cpa_tcpa(
    own_n: float, own_e: float, own_vn: float, own_ve: float,
    tgt_n: float, tgt_e: float, tgt_vn: float, tgt_ve: float
) -> Tuple[float, float]:
    """Computes Distance at Closest Point of Approach (DCPA, meters) and

    Time to Closest Point of Approach (TCPA, seconds).
    """
    rel_n = tgt_n - own_n
    rel_e = tgt_e - own_e
    rel_vn = tgt_vn - own_vn
    rel_ve = tgt_ve - own_ve

    rel_speed_sq = rel_vn**2 + rel_ve**2
    if rel_speed_sq < 0.01:
        # Stationary or parallel matched speed
        dist = math.hypot(rel_n, rel_e)
        return dist, 0.0

    # TCPA = - (r . v_rel) / |v_rel|^2
    tcpa = - (rel_n * rel_vn + rel_e * rel_ve) / rel_speed_sq
    if tcpa <= 0.0:
        dist = math.hypot(rel_n, rel_e)
        return dist, 0.0

    cpa_n = rel_n + rel_vn * tcpa
    cpa_e = rel_e + rel_ve * tcpa
    dcpa = math.hypot(cpa_n, cpa_e)
    return dcpa, tcpa


class AisAvoidanceEngine:
    def __init__(
        self,
        cpa_safety_radius_m: float = 120.0,
        tcpa_horizon_s: float = 60.0,
        evasion_course_delta_deg: float = 30.0,
    ):
        self.cpa_radius = cpa_safety_radius_m
        self.tcpa_horizon = tcpa_horizon_s
        self.evasion_course_delta = evasion_course_delta_deg
        self.targets: Dict[str, dict] = {}  # mmsi -> target state
        self.last_evasion_maneuver = None

    def update_target_ais(
        self, mmsi: str, lat: float, lon: float,
        speed_mps: float = 2.0, course_deg: float = 0.0,
        t: Optional[float] = None
    ):
        """Ingests an AIS position report."""
        now = t if t is not None else time.time()
        rad = math.radians(course_deg)
        vn = speed_mps * math.cos(rad)
        ve = speed_mps * math.sin(rad)
        self.targets[str(mmsi)] = {
            "lat": lat,
            "lon": lon,
            "vn": vn,
            "ve": ve,
            "speed_mps": speed_mps,
            "course_deg": course_deg,
            "t": now,
        }

    def evaluate_threats(
        self, own_lat: float, own_lon: float,
        own_speed_mps: float = 1.5, own_course_deg: float = 90.0
    ) -> Dict[str, any]:
        """Evaluates all tracked AIS targets against COLREGs collision criteria.

        Returns collision assessment and commanded course alteration.
        """
        rad_own = math.radians(own_course_deg)
        own_vn = own_speed_mps * math.cos(rad_own)
        own_ve = own_speed_mps * math.sin(rad_own)

        min_dcpa = float("inf")
        threat_mmsi = None
        threat_tcpa = None
        colregs_rule = "None"
        commanded_delta = 0.0

        for mmsi, tgt in self.targets.items():
            # Relative position in meters
            dn = (tgt["lat"] - own_lat) * _M_PER_DEG_LAT
            de = (tgt["lon"] - own_lon) * _m_per_deg_lon(own_lat)
            dist = math.hypot(dn, de)

            dcpa, tcpa = calculate_cpa_tcpa(
                0.0, 0.0, own_vn, own_ve,
                dn, de, tgt["vn"], tgt["ve"]
            )

            # Check for breach of safety domain
            if tcpa > 0.0 and tcpa <= self.tcpa_horizon and dcpa < self.cpa_radius:
                if dcpa < min_dcpa:
                    min_dcpa = dcpa
                    threat_mmsi = mmsi
                    threat_tcpa = tcpa

                    # Relative bearing to target
                    bearing_to_tgt = (math.degrees(math.atan2(de, dn))) % 360.0
                    rel_bearing = (bearing_to_tgt - own_course_deg) % 360.0

                    # COLREGs Rule 14: Head-on situation
                    if rel_bearing <= 15.0 or rel_bearing >= 345.0:
                        colregs_rule = "Rule 14 (Head-on)"
                        commanded_delta = self.evasion_course_delta  # Starboard turn
                    # COLREGs Rule 15: Crossing give-way (starboard bow)
                    elif 15.0 < rel_bearing <= 112.5:
                        colregs_rule = "Rule 15 (Crossing Give-Way)"
                        commanded_delta = self.evasion_course_delta  # Alter to starboard to pass astern
                    else:
                        colregs_rule = "Rule 16/17 (Precautionary Evasion)"
                        commanded_delta = self.evasion_course_delta

        evasion_active = threat_mmsi is not None
        result = {
            "evasion_active": evasion_active,
            "threat_mmsi": threat_mmsi,
            "dcpa_m": round(min_dcpa, 2) if evasion_active else None,
            "tcpa_s": round(threat_tcpa, 1) if evasion_active else None,
            "colregs_rule": colregs_rule,
            "commanded_course_delta_deg": commanded_delta,
            "commanded_heading_deg": (own_course_deg + commanded_delta) % 360.0,
        }
        self.last_evasion_maneuver = result
        return result
