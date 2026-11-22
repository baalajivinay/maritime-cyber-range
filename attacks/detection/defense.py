"""
Autonomous Defense & Failover Autopilot (Task 3).

Turns the passive tripwires into active counter-measures. Given the live
vessel state, the attack overlay and the correlating radar/optical tracks, the
controller emits a *defense directive* that the hydrodynamics autopilot and the
BAM banner consume:

  1. Dynamic Sensor Fusion Failover
       EKF3 innovation above the gate (default 3.5 sigma) while a positioning
       spoof is active -> isolate the primary positioning sensor and fall back
       to DVL + Dead-Reckoning (+ USBL when submerged). Latches with hysteresis.

  2. COLREGS Verification Gate
       Before authorising an evasive manoeuvre against an AIS contact, the
       bearing/range is cross-correlated with radar/optical tracks. A contact
       seen only in AIS (a phantom) is a ghost: course is maintained, an
       IEC 62320-1 anomaly is logged and the false evasion is suppressed.

  3. Failsafe Actuator Quarantine & Loiter
       A failed MAVLink 2.0 HMAC verification / RC-override anomaly severs the
       hijacked control channel and commands an autonomous station-keeping
       loiter circle.

Stdlib only; Qt-free so it is unit-testable in isolation.
"""
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

INNOVATION_SIGMA_GATE = 3.5     # EKF3 innovation gate (sigma)
RADAR_CORRELATION_M = 150.0     # AIS<->radar association gate (metres)


@dataclass
class DefenseDirective:
    gnss_isolated: bool = False
    nav_source: str = "GNSS/INS"
    suppress_ais_evasion: bool = False
    ais_phantom: bool = False
    actuator_quarantine: bool = False
    loiter: bool = False
    banner: Optional[str] = None            # BAM banner text when defending
    new_events: List[Tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "gnss_isolated": self.gnss_isolated,
            "nav_source": self.nav_source,
            "suppress_ais_evasion": self.suppress_ais_evasion,
            "ais_phantom": self.ais_phantom,
            "actuator_quarantine": self.actuator_quarantine,
            "loiter": self.loiter,
            "defense_banner": self.banner,
        }


class DefenseController:
    """Stateful autonomous-defense logic. Call :meth:`update` once per tick."""

    def __init__(self, innovation_gate: float = INNOVATION_SIGMA_GATE, enabled: bool = False):
        self.innovation_gate = innovation_gate
        self.enabled = enabled           # autonomous defense armed?
        self.gnss_isolated = False
        self.actuator_quarantine = False
        self._prev_attack: Optional[str] = None
        self._logged_phantom = False

    def set_enabled(self, on: bool):
        self.enabled = bool(on)
        if not on:
            self.reset()

    def reset(self):
        self.gnss_isolated = False
        self.actuator_quarantine = False
        self._prev_attack = None
        self._logged_phantom = False

    def update(
        self,
        dt: float,
        state: Dict[str, Any],
        attack_overlay: Dict[str, Any],
        radar_tracks: Optional[List[Dict[str, Any]]] = None,
    ) -> DefenseDirective:
        d = DefenseDirective()
        if not self.enabled:
            return d
        radar_tracks = radar_tracks or []
        attack = attack_overlay.get("active_attack")
        innov = float(attack_overlay.get("simulated_innovation", 0.0) or 0.0)
        domain = state.get("domain", "surface")

        # On a fresh attack transition, drop stale latches
        if attack != self._prev_attack:
            if attack is None:
                self.gnss_isolated = False
                self.actuator_quarantine = False
                self._logged_phantom = False
        self._prev_attack = attack

        # --- 1. Sensor fusion failover ------------------------------------
        positioning_spoof = attack in ("gps_spoof", "acoustic_spoof")
        if positioning_spoof and innov > self.innovation_gate:
            if not self.gnss_isolated:
                d.new_events.append((
                    "DEFENSE",
                    f"Innovation {innov:.1f}sigma > {self.innovation_gate:.1f} gate: "
                    f"isolating primary positioning sensor, failing over to "
                    f"{'DVL+DR+USBL' if domain == 'underwater' else 'DVL+DR'}"))
            self.gnss_isolated = True
        if self.gnss_isolated:
            d.gnss_isolated = True
            if domain == "underwater":
                d.nav_source = "DVL + DR + USBL"
                d.banner = "DEFENSE: ACOUSTIC ISOLATED — SENSOR FAILOVER ACTIVE"
            else:
                d.nav_source = "DVL + DR (GNSS ISOLATED)"
                d.banner = "DEFENSE: GNSS ISOLATED — SENSOR FAILOVER ACTIVE"

        # --- 2. COLREGS verification gate ---------------------------------
        if attack == "ais_spoof":
            ghost = attack_overlay.get("ghost_vessel")
            correlated = self._radar_correlated(ghost, radar_tracks)
            if ghost is not None and not correlated:
                d.ais_phantom = True
                d.suppress_ais_evasion = True
                if not self._logged_phantom:
                    d.new_events.append((
                        "IEC62320-1",
                        "AIS contact has no radar/optical correlation — classified "
                        "PHANTOM; maintaining course, evasive manoeuvre suppressed"))
                    self._logged_phantom = True
                # Preserve any failover banner; only set if none
                if d.banner is None:
                    d.banner = "DEFENSE: AIS PHANTOM REJECTED — HOLDING COURSE"
            else:
                self._logged_phantom = False

        # --- 3. Actuator quarantine & loiter ------------------------------
        if attack == "c2_replay":
            if not self.actuator_quarantine:
                d.new_events.append((
                    "DEFENSE",
                    "MAVLink HMAC/RC-override anomaly: severing hijacked control "
                    "channel, commanding autonomous station-keeping loiter"))
            self.actuator_quarantine = True
        if self.actuator_quarantine:
            d.actuator_quarantine = True
            d.loiter = True
            d.banner = "DEFENSE: C2 QUARANTINED — AUTONOMOUS LOITER ENGAGED"

        return d

    @staticmethod
    def _radar_correlated(ghost: Optional[Dict[str, Any]], radar_tracks: List[Dict[str, Any]]) -> bool:
        """True if an AIS contact has a radar/optical track within the gate.

        Note: synthetic ARPA blips (``synthetic=True``) are themselves injected
        and do NOT count as independent corroboration."""
        if not ghost:
            return False
        gpos = ghost.get("pos")
        if not gpos:
            return False
        for t in radar_tracks:
            if t.get("synthetic"):
                continue
            de = float(t.get("east_m", 0.0)) - gpos[0]
            dn = float(t.get("north_m", 0.0)) - gpos[1]
            if math.hypot(de, dn) <= RADAR_CORRELATION_M:
                return True
        return False
