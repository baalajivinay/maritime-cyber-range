# MASS twin — resilient — Textron Fleet-class CUSV (hardened)

**Real hardware digital twin**: the exact same real Textron Fleet-class
CUSV hull/physics as `mass_vulnerable_cusv` (see that twin's README and
`sim_config/models/cusv/model.sdf`'s header comment for the sourced
physical data, the disclosed propulsion-configuration assumption, and the
disclosed top-speed simplification). The **only** difference here is its
onboard GCS-link and GPS-fusion security configuration (`hardened.parm`) —
the exact same two mechanisms already verified live against BlueBoat,
carried over unmodified in value and re-verified live against this hull.

- `GPS1_TYPE=14` — GPS becomes an externally-fused sensor the EKF
  cross-checks against real IMU data.
- `MAV_GCS_SYSID=77` + `MAV_OPTIONS=1` (`GCS_SYSID_ENFORCE`) — only
  accepts GCS-privileged commands from sender id 77; an attacker using
  ArduPilot's plain default (255) — what `target.json` deliberately uses —
  gets rejected outright.

## Verified live result against all 3 attacks

| Attack | Sub-check | Verdict | Why |
|---|---|---|---|
| GPS spoof | vulnerability | **N/A** | `GCS_SYSID_ENFORCE` blocks the attacker's GPS_INPUT traffic before it ever reaches the wire — the same effect already documented for BlueBoat, re-confirmed live on this hull. |
| AIS spoof | vulnerability | **N/A** | Platform fact — same on every twin in this set. |
| C2 replay | mode-change | **RESILIENT** | Verified live: forged mode-change from the attacker's default sysid has no effect. |
| C2 replay | RC-override | **INCONCLUSIVE** | Verified live: the attacker can't even arm the vehicle, so the check correctly declines to call the override itself RESILIENT — see `docs/TARGET_TESTING.md`'s verdict-outcomes section for the full reasoning (this is the tool's general rule, applied identically to every hardened twin). |

**Net effect**: identical to BlueBoat's — `GCS_SYSID_ENFORCE` is thorough
enough to block the attacker before GPS spoofing or RC-override can even be
attempted. This confirms the two hardening mechanisms (`GPS1_TYPE=14`,
`MAV_GCS_SYSID`/`MAV_OPTIONS`) are genuinely ArduPilot-parameter-level, not
hull-specific — they transferred from a 30 kg boat to a 7.7-tonne one with
zero changes and produced the same result.

Deployment verdict: **CONDITIONALLY READY** (zero VULNERABLE findings, but
not a clean READY either, since rc_override was never conclusively
exercised).

## Boot it

```bash
tools/run_vehicle.sh vehicle_twins/mass_resilient_cusv up
python3 tools/test_target.py --target vehicle_twins/mass_resilient_cusv/target.json
tools/run_vehicle.sh vehicle_twins/mass_resilient_cusv down
```

See `docs/TWIN_DEMO_GUIDE.md` for the full walkthrough and dashboard usage.
