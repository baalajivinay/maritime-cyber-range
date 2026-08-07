# Target Testing — Vehicle-Agnostic Resilience Tester

Point this at **any** ArduPilot-based AUV/USV -- one of this repo's own
reference vehicles, or someone else's SITL instance entirely -- run the same
3 attacks the rest of this range uses (GPS spoof, AIS spoof, C2
replay/override), and get back a report answering the question a Navy
reviewer actually asks: **is this vehicle vulnerable, and is it safe to
deploy?**

This is a separate, additive tool alongside the dashboard/demo covered in
`docs/DESIGNER_GUIDE.md`. Nothing here changes `profiles/*.json`,
`tools/run_sim.sh`, or the dashboard -- see "How this relates to the rest of
the range" below.

## What's in the box

| Layer | Where | What it does |
|---|---|---|
| Target contract | `targets/*.json` | Connection-only description of a vehicle to test: how to reach it over MAVLink, which attacks to run, and consent (`authorized: true`). No SDF, no world file -- this repo doesn't need to boot it. |
| Loader | `targets/loader.py` | `load_target(name)`. Validates the contract, refuses to load unless `authorized: true`. |
| Contract check | `tools/validate_target.py` | Pre-flight validation: catches an invalid `gps_spoof.method`, warns on `allow_arm_and_actuate` against a non-loopback host, warns on a dead-end AIS impersonation config. |
| GPS injection (portable) | `attacks/gps_input_inject.py` | Sends standard MAVLink `GPS_INPUT` (#232) -- works on any ArduPilot (or PX4) build with `GPS_TYPE=14`, real hardware included. |
| Orchestrator | `tools/test_target.py` | Connects, baselines, runs the requested attacks, taps the live feed with `DetectorSuite` throughout, writes verdicts + evidence. |
| Report | `tools/generate_target_report.py` | Compiles every target's latest run into one HTML page: per-attack vulnerability + detectability, recommendations for anything VULNERABLE, and one synthesized deployment-readiness verdict per target. |

## Quick start

```bash
python3 tools/validate_target.py wamv_local        # contract check, no live connection needed
python3 tools/test_target.py --target wamv_local   # runs every attack enabled in the config
python3 tools/generate_target_report.py            # -> target_runs/resilience_report.html
```

Run a subset of attacks:

```bash
python3 tools/test_target.py --target wamv_local --attacks c2_replay,ais_spoof
```

Each run writes `target_runs/<name>/<run_ts>/{verdicts.json,alerts.jsonl,*_ground_truth.csv}`
-- deliberately outside `attack_logs/`/`evidence/`, so target runs never mix
with the existing reference-vehicle evidence trail. `generate_target_report.py`
walks every `target_runs/*/*/verdicts.json` and uses each target's most
recent run.

## Onboarding a new target

1. **Write `targets/<name>.json`.** Minimum viable contract:

   ```jsonc
   {
     "name": "some_external_rover",
     "description": "free text -- who/where, human-only",
     "domain": "surface",                        // "surface" | "underwater"
     "authorized": true,                          // REQUIRED -- explicit attestation you
                                                    // have authorization to attack this
                                                    // target. Loader refuses to run otherwise.
     "mavlink": {
       "connection": "udpout:203.0.113.5:14550",  // any pymavlink connection string
       "source_system": 255                        // default 255 -- see note below
     },
     "attacks": {
       "gps_spoof": {
         "enabled": true,
         "method": "gps_input",                   // "gps_input" (any target) |
                                                    // "fdm_relay" (loopback / our own only)
         "gps_id": 0,
         "profile": "ramp",                        // "step" | "ramp"
         "step_offset_m": 50.0,
         "ramp_rate_m_per_s": 0.5,
         "direction_deg": 90.0
       },
       "ais_spoof": {
         "enabled": true,
         "udp_addr": ["127.0.0.1", 10110],
         "own_mmsi": "123456789",                  // omit if no companion AIS transmitter
         "modes": ["ghost", "impersonate"]
       },
       "c2_replay": {
         "enabled": true,
         "target_mode_for_injection": "HOLD",      // must be a mode name valid for the
                                                     // target's own vehicle type/firmware
         "allow_arm_and_actuate": false,            // default false -- arming/actuating
                                                     // someone else's vehicle needs explicit
                                                     // opt-in
         "rc_throttle_pwm": 1700,
         "rc_steering_pwm": 1500,
         "duration_s": 8.0
       }
     },
     "timing": { "settle_s": 5.0, "window_s": 20.0 }
   }
   ```

2. **Pick the right `gps_spoof.method`:**
   - `gps_input` -- the portable, protocol-standard choice. Sends `GPS_INPUT`
     over MAVLink; works against any target with `GPS_TYPE`/`GPS1_TYPE`
     param set to `14` (`AP_GPS_MAV` driver), including real hardware later.
     Use this for anything you don't control the physics/launch of.
   - `fdm_relay` -- intercepts ArduPilot's own proprietary JSON SITL FDM
     protocol at the physics layer. Only valid when you own the target's
     Gazebo instance (loopback, our own reference vehicles) --
     `validate_target.py` FAILs this against a non-loopback host. Prefer
     this for our own vehicles: the EKF is fighting real water-induced
     motion while the spoof runs, which is the more meaningful test than a
     bare protocol injection with no physics engine behind it.

3. **`source_system: 255`.** ArduPilot only honors `RC_CHANNELS_OVERRIDE`
   (and other GCS-privileged traffic) from a sender system ID matching
   `SYSID_MYGCS`, which defaults to 255 -- a plain, unauthenticated header
   field, not a real control. Testing with the default expected GCS ID is
   the correct vulnerability test (it's what a real attacker would do); the
   loader defaults to it if omitted. A target that changed `SYSID_MYGCS`
   away from its default would legitimately show RESILIENT here.

4. **Validate, then run:**

   ```bash
   python3 tools/validate_target.py <name>
   python3 tools/test_target.py --target <name>
   ```

## Reading the verdicts

Every attack sub-check returns one of **four** outcomes, not a binary
pass/fail. Binary vulnerable-vs-resilient is wrong for an unknown target:
"nothing moved" is ambiguous between "it resisted" and "it never even
ingested the attack," and conflating those in front of a reviewer is a
credibility problem.

- **VULNERABLE** -- the target accepted the forged input and its own
  reported state changed accordingly.
- **RESILIENT** -- the attack was confirmed delivered/ingested, but the
  target's fused state didn't materially move.
- **N/A** -- structurally inapplicable to this platform/config (e.g. AIS
  vulnerability on a bare ArduPilot autopilot -- it doesn't consume AIS in
  this architecture, transmit-only; or C2 RC-override when
  `allow_arm_and_actuate: false`).
- **INCONCLUSIVE** -- can't be determined safely (preconditions weren't met
  -- e.g. never confirmed armed; ingestion couldn't be confirmed either way;
  or the target stopped heartbeating entirely after injection, which could
  indicate a crash/DoS -- a separate, more interesting finding than
  "resilient").

**GPS spoof**: baselines `GLOBAL_POSITION_INT` for `settle_s`, then injects
for `window_s` while tracking **raw** (`GPS_RAW_INT`) and **fused**
(`GLOBAL_POSITION_INT`) peak displacement *separately*. Raw confirms
ingestion; fused confirms whether the EKF/GPS-blend actually trusted it.
Fused tracking ≥~60% of the injected offset -> VULNERABLE; raw ingestion
confirmed but fused stays flat -> RESILIENT (EKF innovation gating did its
job); neither raw nor fused moves -> N/A (target likely doesn't have
`GPS_TYPE=14` set, or `gps_id` mismatch).

**AIS spoof**: vulnerability is **structurally N/A, always**, for a bare
ArduPilot autopilot -- nothing in its own state consumes AIS. Detectability
is still a full, real test (does a blind monitor watching the wire notice
the ghost/impersonation).

**C2 replay**: two independent sub-checks -- mode-change forgery (always
runs) and RC-override (only if `allow_arm_and_actuate: true`, gated on
confirmed ARMED state before ever returning RESILIENT, since ArduPilot
ignores `RC_CHANNELS_OVERRIDE` while disarmed by design and a naive check
would misreport that as resilience).

Every attack window is also tapped live by `DetectorSuite` (the same blind
rule-based detectors the dashboard uses), so each verdict comes with a
**detectability** companion answer: would a passive monitor have caught
this, independent of whether the target itself was vulnerable.

## The report

```bash
python3 tools/generate_target_report.py     # -> target_runs/resilience_report.html
```

One HTML page, compiled from every target's latest run:

- A **vulnerability + detectability table per attack family**, same style as
  `evidence/evaluation_report.html`.
- A **recommendation next to every VULNERABLE finding** -- concrete, not
  generic (e.g. enable MAVLink2 message signing for C2 forgery; add GPS
  innovation gating / GPS blending for a GPS-spoof VULNERABLE result).
- A **detectability-gap note per attack family** where relevant (e.g. the
  C2-override detector watches RC-override traffic, not mode-change
  forgery; the GPS-jump detector catches sudden jumps, not slow ramps) --
  documented so a RESILIENT-but-undetected combination isn't misread as
  full coverage.
- One **synthesized deployment-readiness verdict per target**: any
  VULNERABLE finding -> "NOT READY TO DEPLOY"; else any INCONCLUSIVE ->
  "CONDITIONALLY READY -- retest needed"; else -> "READY (against the
  attacks tested)".

## Known limitations

- **`fdm_relay` GPS-spoof pollutes the shared `attack_logs/gps_spoof_ground_truth.csv`.**
  The relay is a separate, already-running process (`attacks/gps_spoof.py`,
  explicitly "verified working, do not change without re-testing") with its
  own internal ground-truth logging outside this tool's control. Target-run
  evidence itself stays correctly isolated under `target_runs/`; only the
  shared CSV needs periodic trimming back to its legitimate row count if
  you run `fdm_relay` tests repeatedly.
- **C2 RC-override is gated to INCONCLUSIVE for `domain: "underwater"`.**
  The channel/servo mapping the check uses (chan1/chan3 throttle/steering,
  watching `servo3`) is Rover-specific and unvalidated against ArduSub's
  different thruster layout -- confirmed empirically against BlueROV2 (the
  override registered in `RC_CHANNELS` but the watched servo never moved,
  which would have produced a false RESILIENT without the gate). Extending
  this to a real ArduSub-aware check is a follow-up, not yet done.
- **`gps_input` needs `GPS_TYPE`/`GPS1_TYPE=14` set on the target already.**
  This tool can't set that param remotely for an external target it doesn't
  control the boot of -- if both raw and fused GPS stay flat through the
  whole injection window, that's an N/A verdict pointing at this, not a
  security finding.

## How this relates to the rest of the range

This tool is the vehicle-agnostic **testing product**; the rest of the range
(`docs/DESIGNER_GUIDE.md`) is the fixed 3-vehicle demo/evaluation harness
used to build and validate the underlying attacks and detectors in the first
place. They share the same attack and detection code paths (`attacks/*.py`,
`detection/detectors.py`) but are otherwise fully separate: different config
namespace (`targets/*.json` vs `profiles/*.json`), different entry points,
different evidence directories (`target_runs/` vs `attack_logs/`/`evidence/`).
Running one never affects the other. See `~/.claude/plans/crystalline-frolicking-thompson.md`
(or its summary in `docs/EXECUTION_STATE.md`) for the full rationale behind
the pivot from demo to testing tool.
