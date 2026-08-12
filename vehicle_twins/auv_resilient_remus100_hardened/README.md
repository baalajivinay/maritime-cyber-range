# AUV twin — resilient — REMUS-100 (hardened)

Same real REMUS-100 hull/actuation digital twin as `auv_vulnerable_remus100`
(see that twin's README for the full hull-sourcing and disclosed-actuation-
mismatch writeup) — the only difference is this vehicle's GCS-link security
config: `MAV_GCS_SYSID 77` + `MAV_OPTIONS 1` (`GCS_SYSID_ENFORCE`), the same
mechanism and exact values already live-verified against this project's
original hardened BlueROV2 twin (since removed in favor of this REMUS-100
pair — see `docs/EXECUTION_STATE.md`'s dated removal entry).

## Expected result against all 3 attacks

| Attack | Vulnerability | Why |
|---|---|---|
| GPS spoof | **N/A** | Real physics -- RF/GPS doesn't penetrate water. |
| AIS spoof | **N/A** | Platform fact -- ArduPilot never consumes AIS. |
| C2 replay -- mode-change | **RESILIENT** | `post_mode` stayed `MANUAL` (forged `ALT_HOLD` from sysid 255 refused). |
| C2 replay -- RC-override | **INCONCLUSIVE** | Attacker (sysid 255) can't even arm under `MAV_OPTIONS=1` -- `armed_confirmed=false`, so per this tool's own preconditions-not-met rule (see `docs/TARGET_TESTING.md`) this is INCONCLUSIVE, not RESILIENT (never move can't-arm and won't-obey into the same bucket). |

## Verified live result (2026-08-08, `tools/test_target.py`)

```
mode_change: RESILIENT    (forged ALT_HOLD refused -- post_mode stayed MANUAL)
rc_override: INCONCLUSIVE (armed_confirmed=false -- attacker sysid 255 can't arm)
detectability: c2_replay=0.0 (no forged command ever took effect to detect)
```

Exact verdict-shape and evidence parity with this project's original hardened
BlueROV2 twin's own already-verified result -- same hardening mechanism, same
outcome, on the new hull. Full evidence:
`target_runs/auv_resilient_remus100_hardened/20260808T232839/verdicts.json`.

## Boot it

```bash
tools/run_vehicle.sh vehicle_twins/auv_resilient_remus100_hardened up
python3 tools/test_target.py --target vehicle_twins/auv_resilient_remus100_hardened/target.json
tools/run_vehicle.sh vehicle_twins/auv_resilient_remus100_hardened down
```

See `docs/TWIN_DEMO_GUIDE.md` for the full walkthrough and dashboard usage.

## Known limitation: click-to-navigate

This twin arms and enters AUTO correctly, but does not reliably track a
clicked destination (oscillates at long range, diverges at short range) --
open bug, root-caused but not fixed, see `docs/EXECUTION_STATE.md`'s
2026-08-10 entry. Doesn't affect any of the 3 attacks above or the CLI
verdicts, which don't depend on waypoint tracking. Use the CUSV twins for a
live navigation demo.
