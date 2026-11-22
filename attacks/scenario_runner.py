"""
Multi-Stage Cyber Attack Campaign Scenario Runner.

A schema-driven, Qt-free player engine that drives the live console's
``AttackExecutionManager`` and ``MarineDynamicsEngine`` through a timed
sequence of attack stages, while continuously scoring operational resilience.

Unlike ``application/scaleup/scenario`` (an offline SITL batch engine), this
runner is designed to be stepped in lock-step with the live 10 Hz console
telemetry loop so the operator can Load / Play / Pause / Scrub / Reset a
campaign and watch it unfold on the real workstation instruments.

Resilience scoring (per IACS UR E26 evidence requirements):
  * TTD  -- Time-to-Detection, measured per attack stage from injection to the
            first tripwire breach.
  * XTE  -- Cross-Track Error against the planned fairway track (max observed).
  * CPA  -- Closest Point of Approach margin to the nearest contact.

Stdlib only.
"""
import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SCENARIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios")

# Detection thresholds (shared with the autonomous-defence tripwires)
INNOVATION_SIGMA_TRIP = 3.5     # EKF3 innovation gate (sigma)
XTE_WARN_DEFAULT_M = 50.0       # default fairway half-width


def list_scenarios(directory: str = SCENARIO_DIR) -> List[Dict[str, str]]:
    """Return [{id, name, path}] for every scenario JSON in ``directory``."""
    out = []
    if not os.path.isdir(directory):
        return out
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(directory, fn)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            out.append({
                "id": data.get("id", os.path.splitext(fn)[0]),
                "name": data.get("name", fn),
                "path": path,
            })
        except (OSError, ValueError):
            continue
    return out


def load_scenario(ref: str, directory: str = SCENARIO_DIR) -> Dict[str, Any]:
    """Load a scenario by id, filename, or absolute path."""
    if os.path.isabs(ref) and os.path.exists(ref):
        path = ref
    else:
        path = os.path.join(directory, ref if ref.endswith(".json") else ref + ".json")
        if not os.path.exists(path):
            # Try matching by declared id
            for meta in list_scenarios(directory):
                if meta["id"] == ref:
                    path = meta["path"]
                    break
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@dataclass
class StageScore:
    index: int
    name: str
    attack: Optional[str]
    injected_at_s: Optional[float] = None
    detected_at_s: Optional[float] = None

    @property
    def ttd_s(self) -> Optional[float]:
        if self.injected_at_s is None or self.detected_at_s is None:
            return None
        return max(0.0, self.detected_at_s - self.injected_at_s)

    @property
    def detected(self) -> bool:
        return self.detected_at_s is not None


@dataclass
class ResilienceScore:
    """Accumulates the resilience evidence for a scenario run."""
    xte_limit_m: float = XTE_WARN_DEFAULT_M
    max_xte_m: float = 0.0
    min_cpa_m: Optional[float] = None
    stages: List[StageScore] = field(default_factory=list)
    xte_breached: bool = False

    def stage(self, index: int) -> Optional[StageScore]:
        for s in self.stages:
            if s.index == index:
                return s
        return None

    @property
    def mean_ttd_s(self) -> Optional[float]:
        vals = [s.ttd_s for s in self.stages if s.ttd_s is not None]
        return sum(vals) / len(vals) if vals else None

    @property
    def detection_rate(self) -> float:
        attacked = [s for s in self.stages if s.attack]
        if not attacked:
            return 1.0
        return sum(1 for s in attacked if s.detected) / len(attacked)

    def grade(self) -> str:
        """A/B/C/D resilience grade from detection rate, TTD and XTE."""
        dr = self.detection_rate
        mttd = self.mean_ttd_s if self.mean_ttd_s is not None else 99.0
        if dr >= 0.99 and mttd <= 5.0 and not self.xte_breached:
            return "A — FULLY RESILIENT"
        if dr >= 0.99 and mttd <= 10.0:
            return "B — RESILIENT"
        if dr >= 0.6:
            return "C — DEGRADED"
        return "D — VULNERABLE"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "grade": self.grade(),
            "detection_rate": round(self.detection_rate, 3),
            "mean_ttd_s": round(self.mean_ttd_s, 2) if self.mean_ttd_s is not None else None,
            "max_xte_m": round(self.max_xte_m, 2),
            "xte_limit_m": self.xte_limit_m,
            "xte_breached": self.xte_breached,
            "min_cpa_m": round(self.min_cpa_m, 1) if self.min_cpa_m is not None else None,
            "stages": [
                {
                    "index": s.index,
                    "name": s.name,
                    "attack": s.attack,
                    "injected_at_s": s.injected_at_s,
                    "detected_at_s": s.detected_at_s,
                    "ttd_s": round(s.ttd_s, 2) if s.ttd_s is not None else None,
                    "detected": s.detected,
                }
                for s in self.stages
            ],
        }


class ScenarioRunner:
    """
    Stateful player for one multi-stage campaign.

    The runner never owns the physics or attack engines; the console passes them
    in on :meth:`step` so the exact same engines that render the live workstation
    are driven, keeping the scored run and the displayed run identical.
    """

    STATE_IDLE = "idle"
    STATE_PLAYING = "playing"
    STATE_PAUSED = "paused"
    STATE_FINISHED = "finished"

    def __init__(self, scenario: Dict[str, Any]):
        self.scenario = scenario
        self.name: str = scenario.get("name", "Unnamed Scenario")
        self.scenario_id: str = scenario.get("id", "scenario")
        self.twin: str = scenario.get("twin", "interceptor_usv")
        self.site: str = scenario.get("site", "kochi")
        self.domain: str = scenario.get("domain", "surface")
        self.duration_s: float = float(scenario.get("duration_s", 90.0))

        track = scenario.get("planned_track", {})
        self.track_origin = (
            float(track.get("origin_east_m", 0.0)),
            float(track.get("origin_north_m", 0.0)),
        )
        self.track_course_deg = float(track.get("course_deg", 45.0))
        self.xte_limit_m = float(track.get("xte_limit_m", XTE_WARN_DEFAULT_M))

        self.stages: List[Dict[str, Any]] = sorted(
            scenario.get("stages", []), key=lambda s: s.get("t_start", 0.0)
        )

        self.state = self.STATE_IDLE
        self.elapsed_s = 0.0
        self._active_stage_idx: Optional[int] = None
        self._applied_attack: Optional[Tuple[str, dict]] = None

        self.score = ResilienceScore(xte_limit_m=self.xte_limit_m)
        for st in self.stages:
            self.score.stages.append(StageScore(
                index=int(st.get("index", self.stages.index(st))),
                name=st.get("name", "Stage"),
                attack=st.get("attack"),
            ))

    # ------------------------------------------------------------------ control
    def play(self):
        if self.state in (self.STATE_IDLE, self.STATE_PAUSED):
            self.state = self.STATE_PLAYING

    def pause(self):
        if self.state == self.STATE_PLAYING:
            self.state = self.STATE_PAUSED

    def reset(self):
        self.state = self.STATE_IDLE
        self.elapsed_s = 0.0
        self._active_stage_idx = None
        self._applied_attack = None
        self.score = ResilienceScore(xte_limit_m=self.xte_limit_m)
        for st in self.stages:
            self.score.stages.append(StageScore(
                index=int(st.get("index", self.stages.index(st))),
                name=st.get("name", "Stage"),
                attack=st.get("attack"),
            ))

    def seek(self, t_s: float):
        """Scrub the timeline to ``t_s`` (clamped). Stage/attack re-evaluated on
        the next :meth:`step`."""
        self.elapsed_s = max(0.0, min(self.duration_s, float(t_s)))
        if self.state == self.STATE_FINISHED and self.elapsed_s < self.duration_s:
            self.state = self.STATE_PAUSED

    @property
    def progress(self) -> float:
        return 0.0 if self.duration_s <= 0 else min(1.0, self.elapsed_s / self.duration_s)

    # ------------------------------------------------------------------ queries
    def stage_at(self, t_s: float) -> Optional[Dict[str, Any]]:
        for st in self.stages:
            if st.get("t_start", 0.0) <= t_s < st.get("t_end", self.duration_s):
                return st
        if self.stages and t_s >= self.stages[-1].get("t_end", self.duration_s):
            return None
        return self.stages[0] if self.stages else None

    @property
    def active_stage(self) -> Optional[Dict[str, Any]]:
        return self.stage_at(self.elapsed_s)

    def cross_track_error(self, east_m: float, north_m: float) -> float:
        """Signed-magnitude perpendicular distance from the planned fairway track."""
        course = math.radians(self.track_course_deg)
        # Track direction unit vector in (East, North)
        te = math.sin(course)
        tn = math.cos(course)
        de = east_m - self.track_origin[0]
        dn = north_m - self.track_origin[1]
        # Cross product magnitude = perpendicular distance
        return abs(de * tn - dn * te)

    # --------------------------------------------------------------------- step
    def step(self, dt: float, attack_mgr, physics=None) -> Dict[str, Any]:
        """Advance the campaign by ``dt`` seconds and reconcile the live attack
        engine with the active stage. Returns a status overlay for the UI."""
        if self.state == self.STATE_PLAYING:
            self.elapsed_s = min(self.duration_s, self.elapsed_s + dt)
            if self.elapsed_s >= self.duration_s:
                self.state = self.STATE_FINISHED

        stage = self.active_stage
        self._reconcile_attack(stage, attack_mgr, physics)
        return {
            "scenario": self.name,
            "state": self.state,
            "elapsed_s": self.elapsed_s,
            "duration_s": self.duration_s,
            "progress": self.progress,
            "stage_index": None if stage is None else int(stage.get("index", -1)),
            "stage_name": "Campaign Complete" if stage is None else stage.get("name", ""),
            "stage_narrative": "" if stage is None else stage.get("narrative", ""),
        }

    def _reconcile_attack(self, stage: Optional[Dict[str, Any]], attack_mgr, physics=None):
        """Ensure the live attack engine matches the attack the active stage
        prescribes, starting/stopping only on transitions. Keyed on
        (stage_index, attack_name) so an attack is launched exactly once per
        stage entry and never re-armed (which would reset its accumulated
        state) while the stage remains active."""
        if stage is not None and stage.get("attack"):
            key = (int(stage.get("index", -1)), stage["attack"])
        else:
            key = (None, None)

        if key == self._applied_attack:
            return

        _, name = key
        if name is None:
            attack_mgr.stop_attack()
        else:
            params = dict(stage.get("params", {}))
            # Anchor contact/offset geometry to the vessel's LIVE position so
            # injected threats are relevant wherever the vessel has travelled.
            if physics is not None and "own_pos" not in params:
                params["own_pos"] = (physics.east_m, physics.north_m)
                params["own_hdg"] = math.degrees(physics.psi) % 360.0
            self._launch(attack_mgr, name, params)
            ss = self.score.stage(int(stage.get("index", -1)))
            if ss and ss.injected_at_s is None:
                ss.injected_at_s = self.elapsed_s
        self._applied_attack = key

    @staticmethod
    def _launch(attack_mgr, name: str, params: dict):
        if name == "gps_spoof":
            attack_mgr.start_gps_attack(
                mode=params.get("mode", "ramp"),
                drift_rate=float(params.get("drift_rate", 2.5)),
                bearing_deg=float(params.get("bearing_deg", 45.0)),
            )
        elif name == "ais_spoof":
            own = params.get("own_pos", (0.0, 0.0))
            attack_mgr.start_ais_attack(
                scenario=params.get("scenario", "crossing"),
                own_pos=own,
                own_hdg=float(params.get("own_hdg", 45.0)),
            )
        elif name == "c2_replay":
            attack_mgr.start_c2_attack(cmd_type=params.get("cmd_type", "rc_override"))
        elif name in ("acoustic_spoof", "acoustic_jam"):
            rate = 0.0 if name == "acoustic_jam" else float(params.get("rate", 1.5))
            attack_mgr.start_acoustic_attack(delay_rate=rate)

    # ------------------------------------------------------------------- scoring
    def record(self, state: Dict[str, Any]):
        """Feed one live telemetry sample into the resilience scorer."""
        east = float(state.get("east_m", 0.0) or 0.0)
        north = float(state.get("north_m", 0.0) or 0.0)
        xte = self.cross_track_error(east, north)
        if xte > self.score.max_xte_m:
            self.score.max_xte_m = xte
        if xte > self.xte_limit_m:
            self.score.xte_breached = True

        cpa = state.get("cpa_m")
        if cpa is not None:
            if self.score.min_cpa_m is None or cpa < self.score.min_cpa_m:
                self.score.min_cpa_m = float(cpa)

        stage = self.active_stage
        if stage is None or not stage.get("attack"):
            return
        ss = self.score.stage(int(stage.get("index", -1)))
        if ss is None or ss.detected:
            return
        if self._detection_tripped(stage, state):
            ss.detected_at_s = self.elapsed_s

    @staticmethod
    def _detection_tripped(stage: Dict[str, Any], state: Dict[str, Any]) -> bool:
        detect = stage.get("detect", {})
        metric = detect.get("metric", "innovation")
        if metric == "innovation":
            thr = float(detect.get("threshold", INNOVATION_SIGMA_TRIP))
            return float(state.get("simulated_innovation", 0.0) or 0.0) > thr
        if metric == "collision_risk":
            return bool(state.get("collision_risk", False))
        if metric == "c2_override":
            mode = str(state.get("mode", ""))
            return state.get("active_attack") == "c2_replay" or "HIJACK" in mode.upper()
        return False
