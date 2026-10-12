"""Executors run a scenario's timeline and return a telemetry time-series the
consequence evaluators then grade.

Two executors behind one interface so the SAME scenario files and consequence
logic work in both:

  * SimExecutor  -- a first-order synthetic model. No live sim, no Docker, no
                    hardware; deterministic, instant. Used for authoring
                    scenarios, CI, and demonstrating consequence logic. It
                    models the real causal chain of a position-spoof: the
                    autopilot steers its BELIEVED position onto the planned
                    track, so the forged offset pushes the TRUE position off
                    track -- toward whatever hazard the scenario places there.

  * LiveExecutor -- wires the same timeline to the real stack (tools/test_target
                    machinery + Gazebo true pose). Scaffolded here; running it
                    needs a booted twin, so it is intentionally inert in this
                    prototype and raises a clear message pointing at sim mode.
"""
from . import geo


class Executor:
    def run(self, scenario):
        raise NotImplementedError


def _offset_ne_at(timeline, t):
    """Forged position offset (north_m, east_m) in effect at time t, derived
    from the active gps_spoof / acoustic_spoof step (cancelled by stop_attacks)."""
    off_n = off_e = 0.0
    import math
    active = None
    for step in timeline:
        if step.at_s > t:
            break
        if step.action in ("gps_spoof", "acoustic_spoof"):
            active = step
        elif step.action == "stop_attacks":
            active = None
    if active is None:
        return 0.0, 0.0
    p = active.params
    bearing = math.radians(p.get("bearing_deg", 90.0))
    if p.get("profile", "ramp") == "step":
        mag = p.get("step_offset_m", 50.0)
    else:
        mag = p.get("rate_mps", 0.5) * (t - active.at_s)
    return mag * math.cos(bearing), mag * math.sin(bearing)


class SimExecutor(Executor):
    def run(self, scenario):
        m = scenario.mission
        if not m or "start" not in m or "goal" not in m:
            raise ValueError("SimExecutor needs mission.start and mission.goal in the scenario")
        slat, slon = m["start"]
        glat, glon = m["goal"]
        speed = m.get("speed_mps", 3.0)
        total = geo.horiz_m(slat, slon, glat, glon) or 1.0

        dur = scenario.sim.get("duration_s", 120)
        hz = scenario.sim.get("rate_hz", 5)
        n_steps = int(dur * hz) + 1

        telemetry = []
        for i in range(n_steps):
            t = i / hz
            # autopilot holds BELIEVED position on the planned straight track
            frac = min(speed * t / total, 1.0)
            blat = slat + frac * (glat - slat)
            blon = slon + frac * (glon - slon)
            # forged offset makes TRUE drift opposite to the injected shift
            off_n, off_e = _offset_ne_at(scenario.timeline, t)
            tlat, tlon = geo.offset_m(blat, blon, -off_n, -off_e)
            telemetry.append({
                "t": t,
                "true_lat": tlat, "true_lon": tlon,
                "believed_lat": blat, "believed_lon": blon,
                "armed": True,
            })
        return telemetry


class LiveExecutor(Executor):
    """Runs the timeline against a real booted twin. Integration points:
      1. connect to scenario.target (tools/test_target.load + mavlink)
      2. command the mission (goto start->goal)
      3. at each timeline step, trigger the matching attack primitive
         (attacks/gps_spoof.py FIFO, c2_replay inject_*, acoustic_spoof feed)
      4. sample BELIEVED via GLOBAL_POSITION_INT and TRUE via `gz topic` pose
      5. return the same telemetry dict list SimExecutor produces
    Deliberately inert in this prototype (needs a running sim)."""
    def run(self, scenario):
        raise NotImplementedError(
            "LiveExecutor needs a booted twin and is not wired in this prototype. "
            "Use --mode sim to exercise the scenario + consequence logic, or wire "
            "steps 1-5 in scaleup/scenario/executors.py against tools/test_target.py.")
