# Execution State — live cursor for the dual-domain completion effort

> **This file is the resume point.** If you are a fresh session (context was
> summarized, or a session limit was hit), read this file top-to-bottom
> FIRST, then `docs/ROADMAP.md` for the full plan. This file tells you
> exactly what is done, what is in flight, and the next concrete action.
> Update it after every meaningful step — it is cheap insurance against
> losing the thread.

## Mission (do not deviate)

Complete the maritime cyber range as a **dual-domain (surface MASS + underwater
AUV)** simulator per `docs/ROADMAP.md`: both domains share one
attack/dashboard/scoring infrastructure; every remaining work order (WO-11
through WO-27) and its six regression checkpoints get executed in order. The
reference AUV is a **BlueROV2-style** model on **ArduSub**. Attack semantics
differ by domain by design (GPS/AIS are surface-RF; submerged AUV uses an
acoustic-positioning analog) — this is intended, not a gap.

Guardrail: reuse the proven surface architecture (ArduPilotPlugin FDM JSON ->
`attacks/gps_spoof.py` relay on :9002/:9100 -> Gazebo; `gz topic` true-pose
ground truth; per-attack private CSVs in `attack_logs/`). Do not reinvent it
for underwater.

## CURRENT POSITION

- **Active work order: WO-11** (BlueROV2-style vehicle model on ArduSub).
- **Active sub-step:** building the ArduSub-wired BlueROV2 SDF (see WO-11
  sub-steps below).
- **Last completed:** WO-10 (C2 true-position effect confirmed; committed? see
  git log — evidence at `evidence/wo10_c2_rc_override_run.log`).

## Resume protocol (fresh session, start here)

1. Read this file, then `docs/ROADMAP.md`.
2. `git log --oneline -8` and `git status` to see what landed vs. is dirty.
3. Find the "Active work order" above; open its sub-step checklist below.
4. Confirm no sim processes are stranded: `ps aux | grep -E "ardusub|ardurover|gz sim|mav_bridge|gps_spoof"`. Kill leftovers before booting fresh.
5. Continue from the first unchecked sub-step.

## Environment facts (surveyed 2026-07-29 — trust these, don't re-derive)

- `~/ardupilot/build/sitl/bin/ardusub` **is built** and runnable (same JSON FDM
  backend pattern as `ardurover`, sends FDM to 127.0.0.1:9002 by default).
- Native gz-sim8 physics systems present:
  `/usr/lib/x86_64-linux-gnu/libgz-sim8-buoyancy-system.so` and
  `...-hydrodynamics-system.so`. (Distinct from VRX's own
  `libSimpleHydrodynamics.so` / `libPolyhedraBuoyancyDrag.so` used by the WAM-V.)
- **`libArduPilotPlugin.so`** (ardupilot_gazebo) is what wires ArduPilot<->Gazebo;
  see the ArduPilotPlugin block in `sim_config/wamv_ardupilot.sdf` for the exact
  control-channel pattern to copy (cmd_topic per thruster, servo_min/max,
  multiplier/offset, `<modelXYZToAirplaneXForwardZDown>` and `<gazeboXYZToNED>`
  frame rotations, `<imuName>`).
- **BlueROV2 assets already on disk** at `~/auv_ws/src/dave` (the DAVE project):
  - `.../dave_robot_models/description/bluerov2/model.sdf` (496 lines): full
    physical model — meshes, inertia, 6 thrusters with correct BlueROV2 vectored
    geometry, native `gz-sim-hydrodynamics-system` + `gz-sim-thruster-system` +
    BuoyancyPlugin. **BUT it has NO ArduPilotPlugin** — it's driven by ROS
    thruster topics, not ArduSub FDM. So: reuse its physics/geometry, graft on an
    ArduPilotPlugin wired to ardusub (6 control channels -> its 6 thruster topics).
  - `.../config/bluerov2/ardusub.parm` — a ready ArduSub parameter set (copied
    from ardupilot's `default_params/sub.parm`).
  - DAVE ocean worlds at `.../dave_worlds/worlds/*.world` (e.g.
    `dave_ocean_waves.world`) — candidate bases for WO-12's underwater world.
  - BlueROV2 mesh: `.../meshes/bluerov2/bluerov2.dae`.
- WO-10 manual bring-up primitives (reuse for any surface reboot / adapt for sub):
  FDM relay stdin via a FIFO held open by a keepalive writer; SITL launched by
  direct binary (`build/sitl/bin/ardusub ... --model JSON ...`) to bypass
  MAVProxy's tty requirement; a standalone MAVLink fan-out bridge
  (`scratchpad/wo10/mav_bridge.py`) mirroring tcp:5760 to UDP 14551/14552/14553.
  These become first-class in WO-14's `tools/run_sim.sh`.

## Underwater profile plan (WO-08 contract, for WO-11)

Create `profiles/bluerov2.json`: `domain: underwater`, `ardupilot_vehicle_type:
Sub`, `ais: null` (submerged AIS N/A), a home coord, attacks list
`["gps_spoof","acoustic_spoof","c2_replay"]` (AIS omitted while submerged),
same FDM port pair (9002/9100) so the relay is reusable, distinct MAVLink ports
if the surface stack ever runs concurrently (else reuse 14551-3). Selected via
`MCR_VEHICLE_PROFILE=bluerov2`.

---

## Work-order ledger

Legend: [x] done · [~] in progress · [ ] not started

### Phase A Track U — stand up AUV from zero
- [~] **WO-11 — BlueROV2-style model on ArduSub.** Sub-steps:
  - [ ] 11.1 Copy DAVE `bluerov2/model.sdf` + `bluerov2.dae` mesh into the repo
        (`sim_config/models/bluerov2/` or similar); make paths self-contained.
  - [ ] 11.2 Add an IMU sensor to `base_link` (ArduSub needs it; mirror the
        WAM-V's imu_sensor incl. the `pose 0 0 0 180 0 0` fix from WO-09).
  - [ ] 11.3 Add `libArduPilotPlugin.so` block: 6 control channels mapped to the
        model's 6 thruster cmd_topics, `fdm_port_in` 9100, sub-appropriate frame
        rotations, `<imuName>` pointing at 11.2's sensor. Confirm against ArduSub
        SERVO output -> BlueROV2 vectored-thruster mapping.
  - [ ] 11.4 Add a depth/pressure sensor path (ArduSub uses baro for depth; no
        navsat while submerged) — confirm what ArduSub actually consumes for
        depth in SITL/JSON (relevant to WO-16 later).
  - [ ] 11.5 Write `profiles/bluerov2.json` per the plan above.
  - [ ] 11.6 Load-check: model spawns in Gazebo without SDF errors (headless).
- [ ] **WO-12 — Underwater world** (adapt a DAVE ocean world or author one with
      real water volume/depth; wire buoyancy system + water plane).
- [ ] **WO-13 — Confirm ArduSub boots & dives** (arm, dive, hold depth, thruster
      control; visually/telemetry confirmed, not just log-inferred).
- [ ] **CHECKPOINT 1** — full regression: surface (all 3 attacks pass, AUTO
      arming succeeds, C2 true-pos visible) + underwater (boots/dives/holds/arms).

### Phase B (shared) — repeatable, domain-aware harness
- [ ] **WO-14 — `tools/run_sim.sh`** (param by profile; real health checks;
      formalize WO-10's manual bring-up primitives).
- [ ] **WO-15 — `tools/run_attack_suite.py`** (domain-aware; evidence + pass/fail).
- [ ] **CHECKPOINT 2** — harness reproduces Checkpoint 1 for both domains.

### Phase C Track U — underwater attack adaptation
- [ ] **WO-16 — Acoustic-positioning spoofing** (submerged analog of GPS spoof;
      determine ArduSub's submerged positioning input, inject in that path).
- [ ] **WO-17 — GPS spoofing during surfaced windows.**
- [ ] **WO-18 — AIS spoofing, surfaced-only** (enforce no-op while submerged).
- [ ] **WO-19 — C2 replay/inject vs ArduSub** (true depth/pos effect, like WO-10).
- [ ] **CHECKPOINT 3** — full regression both domains, every applicable attack.

### Phase D — generalize beyond one vehicle per domain
- [ ] **WO-20 — Vehicle model contract + validation script.**
- [ ] **WO-21 — Second surface vehicle** (prove the contract).
- [ ] **WO-22 (optional) — Second underwater vehicle.**
- [ ] **CHECKPOINT 4** — full regression across larger vehicle set.

### Phase E (shared) — detection + evaluation
- [ ] **WO-23 — Rule-based detectors per domain** (live feeds only, never the
      private `attack_logs/*.csv` ground truth).
- [ ] **WO-24 — Alert layer on the dashboard.**
- [ ] **WO-25 — Offline scoring harness** (replay detector alerts vs ground
      truth; precision/recall per attack per domain).
- [ ] **CHECKPOINT 5** — detectors fire on every attack; scoring sane.

### Phase F — designer-facing packaging
- [ ] **WO-26 — `docs/DESIGNER_GUIDE.md`.**
- [ ] **WO-27 (optional) — one-command setup.**
- [ ] **CHECKPOINT 6 (final acceptance gate).**

---

## Running notes (append newest at top; keep terse)

- 2026-07-29: WO-10 done and evidenced. Surface stack torn down to free RAM.
  Surveyed underwater assets; found DAVE BlueROV2 + ocean worlds + ardusub.parm
  already on disk — big de-risk for WO-11/12. Wrote this state file. Starting
  WO-11.
