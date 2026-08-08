# AUV twin — resilient — BlueROV2 (hardened)

**Real hardware digital twin**: the exact same physical BlueROV2
hardware/hydrodynamics as `auv_vulnerable_bluerov2` -- same hull, same
6-thruster vectored frame, same buoyancy trim. The **only** difference is
its onboard GCS-link security configuration
(`MAV_GCS_SYSID`/`MAV_OPTIONS=1`, see `hardened.parm`), verified live
against this exact vehicle. This is a deliberate, real-world-realistic
pairing: a fleet operator hardening one unit's link security without
changing the hardware at all.

## Verified live result against all 3 attacks

| Attack | Sub-check | Verdict | Why |
|---|---|---|---|
| GPS spoof | vulnerability | **N/A** | Real physics -- same as the vulnerable AUV twin, unaffected by GCS-link hardening (a different attack surface entirely; RF doesn't penetrate water regardless of config). |
| AIS spoof | vulnerability | **N/A** | Platform fact -- same on every twin in this set. |
| C2 replay | mode-change | **RESILIENT** | Verified live: forged mode-change from the attacker's default sysid has no effect. |
| C2 replay | RC-override | **INCONCLUSIVE** | Verified live: the attacker can't even arm the vehicle, so the check correctly declines to call the override itself RESILIENT rather than assume. See `vehicle_twins/mass_resilient_blueboat/README.md` for the full reasoning -- identical mechanism, same result pattern. |

Deployment verdict: **CONDITIONALLY READY** (zero VULNERABLE findings, but
not a clean READY either, since rc_override was never conclusively
exercised -- the attacker couldn't get far enough to test it).

## Boot it

```bash
tools/run_vehicle.sh vehicle_twins/auv_resilient_bluerov2_hardened up
python3 tools/test_target.py --target vehicle_twins/auv_resilient_bluerov2_hardened/target.json
tools/run_vehicle.sh vehicle_twins/auv_resilient_bluerov2_hardened down
```

See `docs/TWIN_DEMO_GUIDE.md` for the full walkthrough and dashboard usage.
