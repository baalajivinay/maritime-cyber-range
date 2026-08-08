# AUV twin — resilient — REMUS-100 (hardened)

Same real REMUS-100 hull/actuation digital twin as `auv_vulnerable_remus100`
(see that twin's README for the full hull-sourcing and disclosed-actuation-
mismatch writeup) — the only difference is this vehicle's GCS-link security
config: `MAV_GCS_SYSID 77` + `MAV_OPTIONS 1` (`GCS_SYSID_ENFORCE`), the same
mechanism and exact values already live-verified against
`auv_resilient_bluerov2_hardened`.

## Expected result against all 3 attacks

| Attack | Vulnerability | Why |
|---|---|---|
| GPS spoof | **N/A** | Real physics -- RF/GPS doesn't penetrate water. |
| AIS spoof | **N/A** | Platform fact -- ArduPilot never consumes AIS. |
| C2 replay -- mode-change | **RESILIENT** | `post_mode` stayed `MANUAL` (forged `ALT_HOLD` from sysid 255 refused). |
| C2 replay -- RC-override | **INCONCLUSIVE** | Attacker (sysid 255) can't even arm under `MAV_OPTIONS=1` -- `armed_confirmed=false`, so per this tool's own `preconditions_met` gate this is INCONCLUSIVE, not RESILIENT (never move can't-arm and won't-obey into the same bucket). |

## Verified live result (2026-08-08, `tools/test_target.py`)

```
mode_change: RESILIENT    (forged ALT_HOLD refused -- post_mode stayed MANUAL)
rc_override: INCONCLUSIVE (armed_confirmed=false -- attacker sysid 255 can't arm)
detectability: c2_replay=0.0 (no forged command ever took effect to detect)
```

Exact verdict-shape and evidence parity with `auv_resilient_bluerov2_hardened`'s
own already-verified result -- same hardening mechanism, same outcome, on the
new hull. Full evidence:
`target_runs/auv_resilient_remus100_hardened/20260808T232839/verdicts.json`.

## Boot it

```bash
tools/run_vehicle.sh vehicle_twins/auv_resilient_remus100_hardened up
python3 tools/test_target.py --target vehicle_twins/auv_resilient_remus100_hardened/target.json
tools/run_vehicle.sh vehicle_twins/auv_resilient_remus100_hardened down
```

See `docs/TWIN_DEMO_GUIDE.md` for the full walkthrough and dashboard usage.
