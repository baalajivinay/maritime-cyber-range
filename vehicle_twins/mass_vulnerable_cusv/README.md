# MASS twin — vulnerable — Textron Fleet-class CUSV (unhardened)

**Real hardware digital twin**: Textron Systems' Fleet-class Common
Unmanned Surface Vessel (CUSV) — a real, currently-active US Navy
mine-countermeasures / anti-submarine-warfare USV. Sourced physical data
(displacement 7.7 t, length 12 m, beam 3.4 m, semi-planing monohull, top
speed 35 kn) via Wikipedia's "Fleet-class unmanned surface vessel" page,
itself sourced to Textron/naval-technology.com. See
`sim_config/models/cusv/model.sdf`'s header comment for the full physics
derivation, the disclosed propulsion-configuration assumption (Textron has
not published CUSV's engine/thruster layout), and the disclosed
simplification that this simulation does not attempt to reproduce the real
vehicle's 35 kn top speed (the drag model used has no planing-lift term).

This is the out-of-the-box configuration — no GCS-link hardening, no
external-GPS EKF cross-check.

## Verified live result against all 3 attacks

| Attack | Sub-check | Verdict | Why |
|---|---|---|---|
| GPS spoof | vulnerability | **VULNERABLE** | Verified live (`fdm_relay` method): the forged position reaches the FDM/EKF path unfiltered, same mechanism as WAM-V. |
| AIS spoof | vulnerability | **N/A** | Platform fact — same on every twin in this set. |
| C2 replay | mode-change | **VULNERABLE** | Verified live: forged mode-change from the attacker's default sysid took effect (MANUAL → HOLD). |
| C2 replay | RC-override | **VULNERABLE** | Verified live: forged throttle override moved `servo3` from 1500 → 1680 (forged value 1700) while armed — confirmed via the real `tools/test_target.py` attack path (a raw hand-written probe first showed flat servos; that was a methodology gap in the probe's send rate, not a vehicle bug — see `docs/EXECUTION_STATE.md`'s dated entry for the full diagnosis). |

Detectability: `{"ais_spoof": 1.0, "c2_replay": 1.0, "gps_spoof": 1.0}` — a
blind rule-based monitor caught every attack in this run.

Deployment verdict: **NOT READY TO DEPLOY** (multiple VULNERABLE findings).

## Boot it

```bash
tools/run_vehicle.sh vehicle_twins/mass_vulnerable_cusv up
python3 tools/test_target.py --target vehicle_twins/mass_vulnerable_cusv/target.json
tools/run_vehicle.sh vehicle_twins/mass_vulnerable_cusv down
```

See `docs/TWIN_DEMO_GUIDE.md` for the full walkthrough and dashboard usage.
