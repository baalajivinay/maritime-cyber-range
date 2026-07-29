# Roadmap: from a surface-only demo to a dual-domain (AUV + MASS) simulator

## Where this picks up

The project's own stated goal (`docs/Maritime_Cyber_Range_Progress_Report.docx`)
was always "a cyber range for **AUV/MASS** vessels" -- underwater and surface,
both. In practice everything actually built so far is surface-only: VRX, the
WAM-V hull, ArduRover firmware, AIS-as-radio-broadcast. This session's
end-to-end verification proved that surface pipeline works and all three
attacks (GPS spoof, AIS ghost/impersonate, C2 replay/inject) visibly work
against it -- but that's one vehicle domain, not the whole brief.

**This is now corrected as a standing constraint, not a phase**: the
simulator is dual-domain going forward. Surface (MASS/USV) and underwater
(AUV) are both first-class, share the same attack/dashboard/scoring
infrastructure, and every work order below is written with both in mind.

Investigation this session found the underwater side isn't starting from
nothing:
- `~/ardupilot/build/sitl/bin/ardusub` **is already built** (ArduPilot's
  underwater firmware) -- same day as the rest of this work, no git history
  explaining who built it or why, but it's there and usable.
- Gazebo (`gz-sim8`) ships native `buoyancy-system` and
  `hydrodynamics-system` plugins -- the physics building blocks for
  submersion/underwater drag exist in the installed simulator already.
- **Nothing else underwater exists**: no vehicle model, no underwater
  world, no SDF wiring ArduSub to Gazebo the way `wamv_ardupilot.sdf` wires
  ArduRover to Gazebo today.

**Attack semantics differ by domain, deliberately** (this was a real
decision, not an oversight): GPS and AIS are physically surface/RF
phenomena -- no signal penetrates water. A submerged AUV navigates via
inertial/acoustic positioning and only gets real GPS/AIS during surfaced
windows. So for the underwater track:
- GPS spoofing applies during the AUV's surfaced GPS-fix windows, exactly
  as built for the WAM-V.
- A **new acoustic-positioning spoofing attack** is the submerged analog of
  GPS spoofing -- same "sit in the sensor path and inject a false position"
  shape, targeting whatever underwater positioning input ArduSub actually
  consumes while submerged (this needs investigating -- see WO-16).
- AIS spoofing only applies during surfaced windows (submerged AIS is N/A,
  correctly, not a gap).
- C2 replay/inject carries over unchanged -- it's MAVLink-level and
  medium-agnostic regardless of domain.

The reference AUV is a **BlueROV2-style model** -- the de facto standard
ArduSub platform, chosen to de-risk getting ArduSub + Gazebo buoyancy
working at all before worrying about a bespoke hull.

Work orders continue this project's existing `WO-##` numbering (WO-01
through WO-07 are already in the codebase's docstrings/history). New work
starts at **WO-08**. (The previous version of this roadmap used WO-08
through WO-19 for a surface-only plan; nothing under that numbering was
implemented, so it's superseded outright by the numbering below rather than
patched around.)

## How checkpoints work

A checkpoint is a **mandatory full regression gate covering both domains**
once the underwater track exists (Checkpoint 1 onward is surface-only by
necessity, since underwater doesn't exist until Phase B). On hitting one:

1. Tear down anything running, both domains.
2. Boot each domain's full stack from a clean slate. Surface: Gazebo/VRX ->
   relay -> SITL -> bridge -> AIS emulator -> dashboard, as validated this
   session. Underwater: Gazebo (underwater world) -> relay -> ArduSub SITL
   -> bridge -> dashboard, once it exists.
3. Exercise every attack valid for that domain (surface: GPS/AIS/C2;
   underwater: GPS-at-surface/acoustic-spoof/C2, AIS N/A while submerged)
   and confirm each still produces its expected, visible effect.
4. Diff against the last checkpoint's known-good behavior for **both**
   domains. Anything that changed track -- new error, silent behavior
   change, broken connection, a regression in the *other* domain caused by
   shared-infrastructure changes -- gets root-caused and fixed **before**
   any work order past the checkpoint starts.
5. Record the result at the bottom of this file before continuing.

Until WO-14 lands, run checkpoints manually. After WO-14, `tools/run_sim.sh`
+ `tools/run_attack_suite.py` (parameterized by domain) should make this a
single command per domain.

---

## Phase 0 -- Vehicle-domain abstraction (prerequisite for everything else)

Pulled forward from what would otherwise be a late "generalize" phase,
because the underwater track needs this scaffolding to exist *before* it
can be built, not after.

- **WO-08: Vehicle profile contract. DONE.** Defined the config shape a
  "vehicle profile" needs: domain (`surface` | `underwater`), ArduPilot
  vehicle type (`Rover` | `Sub`), home coordinates, applicable attack set,
  MMSI (surface only), FDM/MAVLink ports. `constants.py` evolved from one
  hardcoded global set of values into a loader over `profiles/<name>.json`
  (selected via `MCR_VEHICLE_PROFILE`, default `wamv`), with required-key
  validation on load. `profiles/wamv.json` is the WAM-V's values migrated
  as-is -- verified numerically identical to the pre-refactor constants,
  and all six consumer files (`attacks/*.py`, `nodes/*/*.py`) import
  unchanged. See `docs/ARCHITECTURE.md`'s "Vehicle profiles" section for
  the schema.

## Phase A (Track S -- Surface) -- Close out known gaps

- **WO-09: Apply the accel-sign fix. DONE.** Root cause confirmed
  precisely: `base_link` has zero rotation (Z-up, standard Gazebo
  convention) and the IMU sensor inherited that same unrotated frame, but
  `ArduPilotPlugin`'s `modelXYZToAirplaneXForwardZDown` (180 0 0, a roll
  that flips Y/Z into the Z-down aircraft convention) is applied to
  position/orientation read from the model root, never to the IMU
  sensor's own separately-sourced output. Fix: gave the IMU sensor the
  same `<pose degrees="true">0 0 0 180 0 0</pose>` in both
  `sim_config/modify_sdf.py` (generator) and the live
  `sim_config/wamv_ardupilot.sdf`. Verified empirically: `RAW_IMU.zacc`
  went from ~+970..+990 mG (wrong sign) to -1003 mG (correct); the vehicle
  armed successfully (`ARMED STATE: True`); and `attacks/auto_mission.py`
  completed a full AUTO-mode mission for the first time ever demonstrated
  in this project -- mission accepted, AUTO mode set, armed, autonomous
  navigation through both waypoints (`MISSION_CURRENT` advanced 0->1),
  final position converged to within a few meters of the target waypoint
  and held steady. Full run log: `evidence/wo09_auto_mission_run.log`.
- **WO-10: Finish C2 replay/inject verification. DONE.** Confirmed
  `inject_forged_rc_override` moves the vessel's *true* Gazebo position,
  not just what MAVLink reports. Booted the full stack (Gazebo/VRX, FDM
  relay, SITL invoked directly bypassing MAVProxy's tty requirement, a
  standalone MAVLink fan-out bridge to 14551/14552/14553 -- see
  `evidence/wo10_c2_rc_override_run.log` for the exact bring-up, since
  WO-14 hasn't formalized this yet), armed in MANUAL, and called the real
  `inject_forged_rc_override` unmodified. Captured the vessel's TRUE
  Gazebo position independently via the same `gz topic`-on-`dynamic_pose`
  technique `ais_emulator.py` uses, before/after: true position moved
  dist=1.628m, and MAVLink `GLOBAL_POSITION_INT` moved in matching
  direction/rough magnitude on the dominant axis. A first pass falsely
  showed zero MAVLink movement -- a test-script artifact (a single
  `recv_match()` right after the override's 10s send-only loop pops the
  *oldest* buffered message, not the latest), fixed by draining the
  buffer before reading; documented in the evidence log so it doesn't
  produce a false negative at Checkpoint 1. Full log:
  `evidence/wo10_c2_rc_override_run.log`.

## Phase A (Track U -- Underwater) -- Stand up AUV from zero

- **WO-11: BlueROV2-style vehicle model.** Build/source an SDF with the
  sensors ArduSub actually expects (IMU, barometer/depth -- not navsat;
  ArduSub doesn't assume GPS underwater), Gazebo's `buoyancy-system` +
  `hydrodynamics-system` plugins tuned for a submersible, and an
  ArduPilotPlugin wired to `ardusub` following the same FDM JSON pattern
  already proven for the rover (reuse the port-relay architecture from
  `attacks/gps_spoof.py`, don't reinvent it).
- **WO-12: Underwater world.** A world with actual water volume/depth for
  submersion (the surface track's `sydney_regatta` is a flat-surface world,
  not suited to this) -- either author one or adapt an existing Gazebo
  underwater example world.
- **WO-13: Confirm ArduSub boots and dives.** The underwater equivalent of
  this session's surface boot verification: arm, dive, hold depth, basic
  thruster control -- visually confirmed (dashboard depth readout or 3D
  view), not just log-inferred.

**CHECKPOINT 1** -- full regression: surface (all 3 attacks still pass,
AUTO-mode arming now succeeds, C2 true-position effect visible) +
underwater (boots, dives, holds depth, arms).

## Phase B (shared) -- Make the harness repeatable, domain-aware from the start

- **WO-14: `tools/run_sim.sh`.** One command, parameterized by vehicle
  profile (WO-08's contract), that launches either domain's full stack with
  real health checks (port-bound confirmation, heartbeat confirmation,
  topic-publishing confirmation) instead of sleep-and-hope. This session's
  manual bring-up (relay via FIFO, direct binary invocation bypassing
  MAVProxy's tty requirement, a standalone MAVLink bridge) becomes
  first-class supported code here, not throwaway `/tmp` scripts.
- **WO-15: `tools/run_attack_suite.py`.** Domain-aware attack runner: GPS/
  AIS/C2 for surface; GPS-at-surface/acoustic-spoof/C2 for underwater.
  Captures evidence, reports pass/fail per attack.

**CHECKPOINT 2** -- automated harness reproduces Checkpoint 1 results for
both domains, no regressions.

## Phase C (Track U) -- Underwater-specific attack adaptation

- **WO-16: Acoustic-positioning spoofing.** The submerged analog of GPS
  spoofing -- investigate what underwater positioning input ArduSub
  actually consumes while submerged (likely still the FDM JSON position
  field, possibly a dedicated DVL/USBL-style sensor bridge -- this needs
  determining, not assuming), then sit in that path and inject false
  position the same way `gps_spoof.py` does for surface GPS.
- **WO-17: GPS spoofing during surfaced windows.** Confirm the existing
  relay pattern applies when the AUV is at/near the surface taking real GPS
  fixes -- may need a mission profile that dives then surfaces periodically
  to create a real window to attack.
- **WO-18: AIS spoofing, surfaced windows only.** Reuse `ais_spoof.py`
  as-is; document (and enforce, e.g. in the attack runner) that it's a
  no-op / not applicable while submerged, since that's physically correct,
  not a gap.
- **WO-19: C2 replay/inject against ArduSub.** Same pattern as the WAM-V's
  C2 attack (arm/disarm, mode change, thruster override) -- confirm it
  moves the true Gazebo position/depth, matching WO-10's surface
  confirmation.

**CHECKPOINT 3** -- full regression, both domains, every attack in each
domain's applicable set.

## Phase D -- Generalize beyond one vehicle per domain

- **WO-20: Vehicle model contract + validation script.** Formalize what a
  designer's SDF/URDF must expose per domain (surface: IMU + navsat +
  correctly-mapped ArduPilotPlugin control channels; underwater: IMU +
  depth sensor + buoyancy/hydrodynamics config + control channels) so the
  harness can validate a new vehicle before attempting to run it.
- **WO-21: Prove it with a second surface vehicle.** Different hull/
  thruster layout. If it doesn't work first try, WO-20's contract is
  incomplete -- fix the contract, not just this one vehicle.
- **WO-22 (optional): Prove it with a second underwater vehicle.** Same
  idea, underwater side, if resources allow.

**CHECKPOINT 4** -- full regression across the now-larger vehicle set, both
domains.

## Phase E (shared) -- Detection + evaluation (progress report's stated "next plan")

- **WO-23: Rule-based detectors per domain.** Surface: GPS implausible-jump/
  velocity-vs-physics, AIS duplicate-MMSI-conflicting-position (exactly the
  impersonation signature confirmed this session), C2 unexpected-command
  detection. Underwater: acoustic-spoof detection, GPS detection during
  surfaced windows, same C2 detection. All consuming only the live feeds
  the dashboard already has -- never the private `attack_logs/*.csv` ground
  truth (see `docs/ARCHITECTURE.md`'s isolation rule).
- **WO-24: Alert layer on the dashboard.** Closes the attack -> alert loop,
  both domains.
- **WO-25: Offline scoring harness.** Anticipated already --
  `gps_spoof.py`'s ground-truth logging comment calls this "the offline
  evaluation harness (Phase 6)." Replay detector alerts against
  `attack_logs/*.csv`, produce precision/recall per attack type per domain.

**CHECKPOINT 5** -- full regression, plus confirm detectors fire correctly
on every attack in both domains and the scoring harness produces a sane
report for each.

## Phase F -- Designer-facing packaging

- **WO-26: `docs/DESIGNER_GUIDE.md`.** How to bring a vehicle (either
  domain), run the harness, read results.
- **WO-27 (optional): one-command setup.** Container or equivalent so
  designers don't hand-run `sim_config/install_*.sh` individually for
  either domain's toolchain.

**CHECKPOINT 6 (final acceptance gate)** -- full regression, both domains,
before calling this milestone done.

---

## Checkpoint log

| Checkpoint | Date | Result |
|---|---|---|
| (pre-checkpoint baseline, surface only) | 2026-07-28 | Manual full-stack boot + all 3 attacks visually verified working on the WAM-V, post-consolidation. See commits `5a5679d`, `9d80d66`, `31c896b`. Underwater track did not exist yet at this point. |
| WO-08 (not a full checkpoint -- pure config-loader refactor, no protocol/port changes) | 2026-07-28 | `constants.py` rewritten as a profile loader; attribute-equivalence check confirmed every value identical to pre-refactor; all six consumer files import cleanly; validation path confirmed to fail loudly (missing key, missing profile) rather than silently. Full live-boot regression deferred to Checkpoint 1 once WO-09 through WO-13 land, per plan. |
| WO-09 (not a full checkpoint -- Checkpoint 1 still waits on WO-10 through WO-13) | 2026-07-28 | Live boot: `RAW_IMU.zacc` corrected from ~+970..+990 mG to -1003 mG; vehicle armed successfully; `attacks/auto_mission.py` completed a full AUTO-mode waypoint mission for the first time in this project's history (mission accepted, autonomous nav through both waypoints, converged on target). GPS/AIS/C2 attacks not re-verified in this pass -- covered already at the pre-checkpoint baseline and unaffected by an IMU-only SDF change; full three-attack re-check still happens at Checkpoint 1. |
| WO-10 (not a full checkpoint) | 2026-07-29 | `inject_forged_rc_override` moved the WAM-V's TRUE Gazebo position 1.628 m. Evidence `evidence/wo10_c2_rc_override_run.log`. |
| WO-11 + WO-12 + WO-13 (Track U standup) | 2026-07-29 | BlueROV2 vendored + ArduSub-wired (`sim_config/models/bluerov2/`), self-contained underwater world (`sim_config/underwater_world.sdf`), and first live underwater run: ArduSub boots/arms/dives 10 m/holds depth <0.5 m/full +/-0.82 m/s thruster authority. Evidence `evidence/wo13_ardusub_dive_run.log`. |
| **CHECKPOINT 1 (full dual-domain regression)** | 2026-07-29 | **PASS.** Surface: AUTO arming succeeds (WO-09 holds); GPS spoof jumps MAVLink +50 m East with true pose unchanged; AIS emulator broadcasts real vessel (WAMV-CYBER/123456789); AIS ghost (999999001) + impersonation (real-MMSI conflict) inject; C2 true-pos per WO-10. Underwater: BlueROV2 boots/dives/holds-depth/arms per WO-13. First checkpoint to gate a live underwater stack. Evidence `evidence/checkpoint1_regression.log`. |
| WO-14 + WO-15 (Phase B harness) | 2026-07-29 | `tools/run_sim.sh` (one-command profile-parameterized boot, real health checks, up/down/status) + `tools/mav_bridge.py` + `tools/run_attack_suite.py` (domain-aware attack runner). Root-caused the SITL-death (stdin EOF -> FIFO stdin). Evidence `evidence/wo14_run_sim_harness.log`, `evidence/wo15_attack_suite.log`. |
| **CHECKPOINT 2 (automated harness reproduces CP1)** | 2026-07-29 | **PASS, both domains, 0 failures.** Surface: gps/ais/c2 all PASS via `run_sim.sh wamv up` + `run_attack_suite.py --profile wamv`. Underwater: c2 PASS, gps/acoustic SKIP (WO-17/WO-16), ais N/A. A checkpoint is now one command per domain. Evidence `evidence/checkpoint2_automated.log`. |
| WO-10 (not a full checkpoint -- Checkpoint 1 still waits on WO-11 through WO-13) | 2026-07-29 | Live boot (direct-binary SITL + standalone MAVLink bridge, no MAVProxy tty needed). `inject_forged_rc_override` confirmed to move the vessel's TRUE Gazebo position (gz-topic ground truth, independent of MAVLink): dist=1.628m over a 10s override, MAVLink `GLOBAL_POSITION_INT` moved in matching direction/magnitude on the dominant axis. GPS/AIS not re-verified in this pass (unaffected by this change); full three-attack re-check still happens at Checkpoint 1. |
