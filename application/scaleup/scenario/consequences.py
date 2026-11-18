"""Consequence evaluators -- turn a telemetry time-series into operational
mission-impact findings. Pure functions over a list of samples; no I/O, no
dependency on the live stack, so they're unit-testable offline (see
scaleup/tests/).

A telemetry sample is a dict:
   {"t": float,
    "true_lat": float, "true_lon": float,       # ground truth (Gazebo pose)
    "believed_lat": float, "believed_lon": float,# what the autopilot thinks
    "armed": bool}

Each evaluator returns a ConsequenceResult.
"""
from dataclasses import dataclass, asdict
from . import geo


@dataclass
class ConsequenceResult:
    type: str
    severity: str
    triggered: bool
    metric: float          # the headline number (metres, usually)
    at_s: float            # when it first occurred (relative to run start), -1 if n/a
    detail: str

    def as_dict(self):
        return asdict(self)


def _t0(telemetry):
    return telemetry[0]["t"] if telemetry else 0.0


def position_divergence(telemetry, threshold_m, severity):
    """Peak separation between the vehicle's TRUE and BELIEVED position -- the
    core 'the autopilot has been lied to' metric."""
    peak, at = 0.0, -1.0
    t0 = _t0(telemetry)
    for s in telemetry:
        d = geo.horiz_m(s["true_lat"], s["true_lon"], s["believed_lat"], s["believed_lon"])
        if d > peak:
            peak, at = d, s["t"] - t0
    trig = peak > threshold_m
    return ConsequenceResult(
        "position_divergence", severity, trig, round(peak, 1), round(at, 1) if trig else -1.0,
        f"peak true-vs-believed divergence {peak:.0f} m "
        f"({'exceeds' if trig else 'within'} {threshold_m:.0f} m tolerance)")


def nogo_breach(telemetry, zone, severity):
    """Did the vehicle's TRUE position enter a no-go polygon -- while its
    BELIEVED position stayed outside it (i.e. it was steered in blind)?"""
    poly = zone.polygon
    t0 = _t0(telemetry)
    for s in telemetry:
        if geo.point_in_polygon(s["true_lat"], s["true_lon"], poly):
            believed_in = geo.point_in_polygon(s["believed_lat"], s["believed_lon"], poly)
            return ConsequenceResult(
                "nogo_breach", severity, True, 0.0, round(s["t"] - t0, 1),
                f"TRUE position entered no-go zone '{zone.name}'"
                + ("" if believed_in else " while the autopilot still believed it was clear"))
    return ConsequenceResult("nogo_breach", severity, False, -1.0, -1.0,
                             f"stayed clear of no-go zone '{zone.name}'")


def grounding(telemetry, shoal, severity):
    """Did the TRUE position come within a shoal/obstacle's radius?"""
    closest, at = float("inf"), -1.0
    t0 = _t0(telemetry)
    plat, plon = shoal.point
    for s in telemetry:
        d = geo.horiz_m(s["true_lat"], s["true_lon"], plat, plon)
        if d < closest:
            closest, at = d, s["t"] - t0
    trig = closest <= shoal.radius_m
    return ConsequenceResult(
        "grounding", severity, trig, round(closest, 1), round(at, 1) if trig else -1.0,
        f"closest TRUE approach to '{shoal.name}' was {closest:.0f} m "
        f"(hazard radius {shoal.radius_m:.0f} m) -- {'GROUNDING' if trig else 'no contact'}")


def cpa_violation(telemetry, contact, threshold_m, severity):
    """Closest Point of Approach between the vehicle's TRUE track and a moving
    contact -- below threshold = a collision-risk / COLREG breach the spoof
    induced."""
    cstart_lat, cstart_lon = contact.start
    vn, ve = contact.velocity_ne_mps
    closest, at = float("inf"), -1.0
    t0 = _t0(telemetry)
    for s in telemetry:
        dt = s["t"] - t0
        clat, clon = geo.offset_m(cstart_lat, cstart_lon, vn * dt, ve * dt)
        d = geo.horiz_m(s["true_lat"], s["true_lon"], clat, clon)
        if d < closest:
            closest, at = d, dt
    trig = closest <= threshold_m
    return ConsequenceResult(
        "cpa_violation", severity, trig, round(closest, 1), round(at, 1) if trig else -1.0,
        f"CPA to contact '{contact.name}' was {closest:.0f} m "
        f"(min safe {threshold_m:.0f} m) -- {'COLLISION RISK' if trig else 'safe'}")


_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def evaluate(consequence, telemetry, scenario):
    """Dispatch one declared consequence to its evaluator."""
    c = consequence
    if c.type == "position_divergence":
        return position_divergence(telemetry, c.threshold_m, c.severity)
    if c.type == "nogo_breach":
        z = scenario.hazard(c.zone)
        if z is None:
            return ConsequenceResult(c.type, c.severity, False, -1.0, -1.0,
                                     f"no-go zone '{c.zone}' not defined in scenario")
        return nogo_breach(telemetry, z, c.severity)
    if c.type == "grounding":
        h = scenario.hazard(c.hazard)
        if h is None or h.point is None:
            return ConsequenceResult(c.type, c.severity, False, -1.0, -1.0,
                                     f"shoal '{c.hazard}' not defined in scenario")
        return grounding(telemetry, h, c.severity)
    if c.type == "cpa_violation":
        k = scenario.contact(c.contact)
        if k is None:
            return ConsequenceResult(c.type, c.severity, False, -1.0, -1.0,
                                     f"contact '{c.contact}' not defined in scenario")
        return cpa_violation(telemetry, k, c.threshold_m, c.severity)
    return ConsequenceResult(c.type, c.severity, False, -1.0, -1.0,
                             f"unknown consequence type '{c.type}'")


def overall_severity(results):
    """Worst severity among TRIGGERED consequences (the mission verdict)."""
    hit = [r for r in results if r.triggered]
    if not hit:
        return "none"
    return max(hit, key=lambda r: _SEVERITY_RANK.get(r.severity, 0)).severity
