# MASS twin — resilient — BlueBoat (hardened)

**Real hardware digital twin**: Blue Robotics' BlueBoat USV, full Gazebo
hydrodynamics -- physically distinct hull/thruster layout from the WAM-V
twin in this set, so this is genuinely different real hardware, not a
reskin. On top of that: **two real, current ArduPilot hardening
mechanisms**, verified live against this exact vehicle (see
`hardened.parm` for the full verification notes), not assumed from
documentation:

- `GPS1_TYPE=14` -- GPS becomes an externally-fused sensor the EKF
  cross-checks against real IMU data, instead of being embedded in the
  same physics feed the IMU is derived from.
- `MAV_GCS_SYSID=77` + `MAV_OPTIONS=1` (`GCS_SYSID_ENFORCE`) -- the vehicle
  only accepts GCS-privileged commands (arm, mode-change, RC-override)
  from sender id 77. This project's own legitimate tooling (dashboard,
  MAVLink bridge) already knows to use 77 for this vehicle
  (`constants.GCS_SOURCE_SYSTEM`, read from this folder's `profile.json`).
  An attacker using ArduPilot's plain default (255) -- which is also what
  `target.json` deliberately uses, representing an attacker with no
  insider knowledge -- gets rejected outright.

## Verified live result against all 3 attacks

| Attack | Sub-check | Verdict | Why |
|---|---|---|---|
| GPS spoof | vulnerability | **N/A** | `GCS_SYSID_ENFORCE` blocks the attacker's GPS_INPUT traffic before it ever reaches the wire (same enforcement mechanism as C2, see below) -- the test tool correctly reports N/A ("never showed any sign of ingesting the forged position") rather than overclaiming RESILIENT for a path it couldn't actually exercise. Tested in isolation (GPS1_TYPE=14 alone, no enforcement) this same EKF genuinely rejects a 50m spoof via IMU cross-check (fused delta 0.00m, raw ingestion 50.00m confirmed) -- see `hardened.parm`'s notes. |
| AIS spoof | vulnerability | **N/A** | Platform fact -- same on every twin in this set. |
| C2 replay | mode-change | **RESILIENT** | Verified live: forged mode-change from the attacker's default sysid has no effect. |
| C2 replay | RC-override | **INCONCLUSIVE** | Verified live: the attacker can't even arm the vehicle, so the check correctly declines to call the override itself RESILIENT (its own design rule: "nothing moved" only counts as resilience if armed was confirmed first -- see `tools/test_target.py`'s `run_c2_rc_override_test`). Being unable to arm at all is arguably *stronger* evidence of resilience than a clean RESILIENT verdict would be, but the tool reports it honestly as INCONCLUSIVE rather than assuming that. |

**Net effect**: `GCS_SYSID_ENFORCE` is thorough enough to block the attacker
before GPS spoofing or RC-override can even be attempted -- the tool's
conservative verdicts (N/A / INCONCLUSIVE rather than a blanket RESILIENT)
are a feature, not a gap: it never claims more than it actually observed.
Deployment verdict: **CONDITIONALLY READY** (zero VULNERABLE findings, but
not a clean READY either, since rc_override was never conclusively
exercised).

## Boot it

```bash
tools/run_vehicle.sh vehicle_twins/mass_resilient_blueboat up
python3 tools/test_target.py --target vehicle_twins/mass_resilient_blueboat/target.json
tools/run_vehicle.sh vehicle_twins/mass_resilient_blueboat down
```

See `docs/TWIN_DEMO_GUIDE.md` for the full walkthrough and dashboard usage.
