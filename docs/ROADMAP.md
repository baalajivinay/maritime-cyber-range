# Roadmap: from attack demo to a general vehicle attack-testing simulator

## Where this picks up

The project (per `docs/Maritime_Cyber_Range_Progress_Report.docx` and this
session's own boot/visual verification) currently proves the *concept*
end-to-end for exactly one vehicle (the stock WAM-V): real ArduPilot SITL
+ real Gazebo/VRX physics, a live dashboard, and three working, visually
confirmed attacks (GPS spoof, AIS spoof/ghost/impersonate, C2 replay/inject).

The stated goal now is different in kind: turn this into a simulator other
vehicle *designers* can point their own vessel model at and run all three
attacks against, repeatably, without hand-holding. That requires closing
known gaps, replacing today's manual/hacky verification steps with real
tooling, generalizing away from the one hardcoded WAM-V, and adding the
detection/scoring layer the progress report already flags as next.

Work orders continue this project's existing `WO-##` numbering (WO-01
through WO-07 are already in the codebase's docstrings/history: physics
bridge, sensors, dashboard, GPS/AIS/C2 attacks). New work starts at **WO-08**.

## How checkpoints work

A checkpoint is not a milestone marker -- it's a **mandatory full regression
gate**. On hitting one:

1. Tear down anything running.
2. Boot the full stack from a clean slate (Gazebo/VRX -> relay -> SITL ->
   bridge -> AIS emulator -> dashboard), exactly as validated in this
   session, or via the automated runner once WO-10 exists.
3. Exercise all three attacks (GPS spoof, AIS ghost + impersonate, C2
   replay/inject) and confirm each still produces its expected, visible
   effect.
4. Diff against the last checkpoint's known-good behavior. Anything that
   changed track -- a new error, a silent behavior change, a broken
   connection -- gets root-caused and fixed **before** any work order past
   the checkpoint starts.
5. Record the result (pass/fail + what broke, if anything) at the bottom
   of this file before continuing.

Until WO-10 lands, run the checkpoint manually (as done for this session's
verification). After WO-10, `tools/run_sim.sh` + `tools/run_attack_suite.py`
should make this a single command.

---

## Phase A -- Close out known gaps (small, low-risk, unblocks everything else)

- **WO-08: Apply the accel-sign fix.** `PreArm: Accels inconsistent` has
  been observed on every boot (root-caused: `accel_body` Z-axis sign vs.
  ArduPilot's convention, per `accel_sign_test.py`'s now-deleted diagnostic
  -- see git history). Apply the fix to `sim_config/wamv.sdf`'s IMU
  `<pose>`, rebuild, confirm arming succeeds and `attacks/auto_mission.py`
  actually completes an AUTO-mode waypoint mission (this has never been
  demonstrated -- the progress report explicitly flags it as not yet shown).
- **WO-09: Finish C2 replay/inject verification.** Confirm
  `inject_forged_rc_override` moves the vessel's *true* Gazebo position
  (not just what MAVLink reports) -- the docstring claims this is what
  distinguishes C2 injection from GPS/AIS spoofing, but it's never been
  visually confirmed the way GPS/AIS were this session. Capture the same
  kind of before/after evidence.

**CHECKPOINT 1** -- full regression, including confirming AUTO-mode arming
now succeeds and C2's true-position effect is visible.

## Phase B -- Make the harness repeatable (stop relying on manual FIFO tricks)

- **WO-10: `tools/run_sim.sh`.** One command that launches Gazebo/VRX, the
  GPS relay, ArduPilot SITL, the MAVLink->dashboard bridge, the AIS
  emulator, and the dashboard, with real health checks at each step
  (port-bound confirmation, heartbeat confirmation, topic-publishing
  confirmation) instead of today's sleep-and-hope. This session's manual
  bring-up (relay via FIFO, direct `ardurover` invocation bypassing
  MAVProxy's tty requirement, a standalone MAVLink bridge) should become
  first-class, documented, supported code here -- not throwaway `/tmp`
  scripts.
- **WO-11: `tools/run_attack_suite.py`.** Programmatically drives all three
  attacks against a running sim (the same step/ramp/ghost/impersonate/
  replay/inject sequence used for this session's visual verification),
  captures evidence, and reports pass/fail per attack -- formalizing this
  session's demo-capture script into supported tooling designers can run
  unattended.

**CHECKPOINT 2** -- run the new automated harness; it must reproduce the
same verified results as this session's manual run, with no regressions.

## Phase C -- Generalize beyond the one hardcoded WAM-V

This is the actual "help designers test their vehicles" work -- everything
before this point only proves the concept on one vessel.

- **WO-12: Vehicle model contract.** Document (and enforce via a
  validation script) exactly what a designer's SDF/URDF must expose for
  the harness to work against it: IMU + navsat sensors, an ArduPilotPlugin
  with correctly-mapped control channels, expected joint/link naming.
  Parameterize `sim_config/modify_sdf.py` to inject this scaffolding into
  *any* base vehicle model, not just `wamv.sdf`.
- **WO-13: Per-vehicle config profiles.** Evolve `constants.py` (currently
  one global set of home coords/MMSI/ports) into a loadable per-vehicle
  profile, so multiple vehicles/worlds can coexist without hand-editing
  shared constants.
- **WO-14: Prove it with a second vehicle.** Bring in a genuinely
  different vessel model (different hull/thruster layout) and run it
  through Phase A-C's full pipeline. If this doesn't work first try,
  WO-12's contract is incomplete -- fix the contract, not just this one
  vehicle.

**CHECKPOINT 3** -- full regression on *both* the original WAM-V and the
new second vehicle; both must pass all three attacks.

## Phase D -- Detection + evaluation (the progress report's stated "next plan")

- **WO-15: Rule-based detectors.** GPS (implausible jump/velocity vs.
  physics), AIS (duplicate MMSI with conflicting position, i.e. exactly
  the impersonation signature confirmed this session), and C2 (unexpected
  RC-override/mode-change without corresponding operator action) -- each
  consuming only the same live feeds the dashboard already has, never the
  private `attack_logs/*.csv` ground truth (see `docs/ARCHITECTURE.md`'s
  isolation rule).
- **WO-16: Alert layer on the dashboard.** Closes the attack -> alert loop
  the progress report calls out as the next milestone.
- **WO-17: Offline scoring harness.** This is literally anticipated
  already -- `gps_spoof.py`'s ground-truth logging comment says it "exists
  only for the offline evaluation harness (Phase 6) to score detector
  performance." Build it: replay detector alerts against `attack_logs/*.csv`
  and produce precision/recall per attack type.

**CHECKPOINT 4** -- full regression, plus confirm the detector fires
correctly on each attack and the scoring harness produces a sane report.

## Phase E -- Designer-facing packaging

- **WO-18: `docs/DESIGNER_GUIDE.md`.** How to bring a vehicle, run the
  harness, read results -- the actual onboarding doc for someone who isn't
  this project's author.
- **WO-19 (optional): one-command setup.** Container or equivalent so
  designers don't hand-run `sim_config/install_*.sh` individually.

**CHECKPOINT 5 (final acceptance gate)** -- full regression before calling
this milestone done.

---

## Checkpoint log

| Checkpoint | Date | Result |
|---|---|---|
| (pre-checkpoint baseline) | 2026-07-28 | Manual full-stack boot + all 3 attacks visually verified working, post-consolidation. See commits `5a5679d`, `9d80d66`, `31c896b`. |
