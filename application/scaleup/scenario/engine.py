"""Scenario engine: load -> run timeline (via an executor) -> evaluate
consequences -> structured result. No I/O beyond what the executor does;
report rendering lives in report.py."""
from dataclasses import dataclass, field
from . import consequences as C
from . import geo


@dataclass
class ScenarioResult:
    scenario_name: str
    description: str
    target: str
    domain: str
    executor: str
    overall_severity: str
    results: list                      # [ConsequenceResult]
    attacks_run: list                  # [{"at_s","action","params"}]
    telemetry_summary: dict
    telemetry: list = field(default_factory=list)   # full series (optional, for plots)


def _summary(telemetry):
    if not telemetry:
        return {"samples": 0}
    peak = 0.0
    for s in telemetry:
        d = geo.horiz_m(s["true_lat"], s["true_lon"], s["believed_lat"], s["believed_lon"])
        peak = max(peak, d)
    return {
        "samples": len(telemetry),
        "duration_s": round(telemetry[-1]["t"] - telemetry[0]["t"], 1),
        "peak_divergence_m": round(peak, 1),
    }


def run_scenario(scenario, executor, keep_telemetry=False):
    telemetry = executor.run(scenario)
    results = [C.evaluate(c, telemetry, scenario) for c in scenario.consequences]
    attacks = [{"at_s": s.at_s, "action": s.action, "params": s.params}
               for s in scenario.timeline if s.action not in ("baseline", "stop_attacks")]
    return ScenarioResult(
        scenario_name=scenario.name,
        description=scenario.description,
        target=scenario.target,
        domain=scenario.domain,
        executor=type(executor).__name__,
        overall_severity=C.overall_severity(results),
        results=results,
        attacks_run=attacks,
        telemetry_summary=_summary(telemetry),
        telemetry=telemetry if keep_telemetry else [],
    )
