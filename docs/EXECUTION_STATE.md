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

- **Active work order: WO-17** (GPS spoofing during the AUV's surfaced windows).
  KEY FACT from WO-16: ArduSub uses `EK3_SRC1_POSXY=6` (ExternalNav), NOT GPS,
  for XY — so GPS spoofing has no effect even at the surface *unless* a GPS EKF
  source is active for the surfaced regime. WO-17 must either configure a GPS
  source set for surfaced windows (EK3_SRC2=GPS + source switching) or document
  that with such a source the already-proven surface gps_spoof relay applies
  unchanged. Then WO-18 (AIS surfaced-only — largely already enforced by the
  suite's N/A handling) and WO-19 (C2 vs ArduSub — largely already shown by the
  suite's c2 check moving true pose 6.61 m). Then CHECKPOINT 3.
- **Last completed: WO-16** (`attacks/acoustic_spoof.py`) — the submerged analog
  of GPS spoofing. Investigated + found ArduSub's submerged positioning is
  ExternalNav (VISION_POSITION_ESTIMATE), not GPS. Built a spoof of that channel;
  live result: AUV's believed position walked 11 m off true while true pose
  stayed put; suite acoustic check PASS. Evidence `evidence/wo16_acoustic_spoof.log`.

### Two operational facts proven in WO-14/15 (don't relearn)
- ArduPilot SITL reads stdin as a console and EXITS on stdin EOF — launch with a
  never-closing stdin (FIFO + keepalive), never `< /dev/null`. run_sim.sh does
  this. (With it fixed, the whole stack now survives ACROSS tool calls.)
- In THIS agent harness only: a Bash call that boots the stack loses its own
  stdout/exit code (detached children transiently hold the harness pipe) — so
  REDIRECT run_sim.sh / --boot output to a file and `cat` it. The work still
  succeeds; only the tool's direct capture is cosmetically broken. Real
  terminals are fine.
- Surface re-boot needs a clean slate: always `run_sim.sh <p> down` (now kills
  VRX grandchildren) before re-`up`, or a stale relay on :9002 / stale gz server
  breaks the boot.

### Bring-up primitives proven this session (WO-14 should formalize these)
- Surface boot: `sim_config/start_vrx.sh` (headless) + `gps_spoof.py` relay
  (stdin via FIFO+keepalive) + `ardurover` direct binary + `mav_bridge.py`.
- Underwater boot: `gz sim -s -r sim_config/underwater_world.sdf` +
  `MCR_VEHICLE_PROFILE=bluerov2 gps_spoof.py` relay + `ardusub` direct binary
  (`--defaults <dave>/config/bluerov2/ardusub.parm`) + `mav_bridge.py`.
- `scratchpad/wo10/mav_bridge.py` = standalone MAVLink fan-out (tcp:5760 ->
  UDP 14551/14552/14553), replaces MAVProxy's `output add` (no tty). COPY this
  into the repo as part of WO-14 (e.g. `tools/mav_bridge.py`).
- Launch long-running SITL/bridge/relay via a mechanism that OUTLIVES a single
  shell call (harness background task, or `setsid`/systemd-run in run_sim.sh) —
  `nohup ... &` inside a one-shot Bash call gets its process group torn down.

### Key operational gotcha (cost real time — do not relearn)
- The BlueROV2 uses `<lock_step>1</lock_step>`: if ArduSub dies, Gazebo FREEZES
  (odometry stops; MAVLink heartbeat goes stale as sys 0). Launch long-running
  SITL + bridge so they persist the whole session (harness background-task
  mechanism), NOT `nohup ... &` inside a one-shot Bash call — that call's
  process group is torn down on return and silently kills the child.
- Always VERIFY arming (heartbeat SAFETY_ARMED flag, retry) before trusting any
  RC-override motion test. An unverified arm that failed makes the vehicle look
  like it has "no thrust" (it just drifts passively). This produced several
  false negatives.
- TRUE depth ground truth: `/model/bluerov2/odometry` (always publishes), NOT
  `dynamic_pose/info` (only emits moving models → None when settled).

### How to boot the underwater stack (verified working through model-load)
```
cd ~/maritime-cyber-range
export GZ_SIM_SYSTEM_PLUGIN_PATH=$HOME/ardupilot_gazebo/build:$GZ_SIM_SYSTEM_PLUGIN_PATH
export GZ_SIM_RESOURCE_PATH=$PWD/sim_config/models:$HOME/ardupilot_gazebo/models:$HOME/SITL_Models/Gazebo/models
gz sim -v4 -s -r sim_config/underwater_world.sdf        # headless; spawns bluerov2
# relay (passthrough), reused as-is under the underwater profile:
MCR_VEHICLE_PROFILE=bluerov2 python3 attacks/gps_spoof.py   # stdin via FIFO (see WO-10 method)
# ArduSub SITL, direct binary (bypasses MAVProxy tty):
~/ardupilot/build/sitl/bin/ardusub --model JSON --speedup 1 --slave 0 \
    --sim-address=127.0.0.1 -I0 --home -33.724223,150.679736,0.0,0.0 \
    --defaults ~/auv_ws/src/dave/models/dave_robot_models/config/bluerov2/ardusub.parm
# MAVLink fan-out bridge: scratchpad/wo10/mav_bridge.py (mirrors tcp:5760 -> 14551/2/3)
```

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
- [x] **WO-11 — BlueROV2-style model on ArduSub.** Vendored from DAVE (which
      already ships an ArduSub-wired ArduPilotPlugin — big de-risk) into
      `sim_config/models/bluerov2/`, self-contained (mesh URIs model-relative),
      `fdm_port_in` 9002->9100 for relay parity, IMU present with π frame
      transform, 6 control channels -> 6 thrusters. Depth via FDM position[D] ->
      ArduSub SIM baro (documented in the model header; drives WO-16). Profile
      `profiles/bluerov2.json` (domain underwater, type Sub, ais null) loads +
      validates; wamv profile unaffected. `gz sdf -k` valid; headless load-check
      clean.
- [x] **WO-12 — Underwater world** (`sim_config/underwater_world.sdf`).
      Self-contained (no Fuel), graded buoyancy (water<z=0, air>z=0 so the AUV
      can submerge AND surface for WO-17), seabed at -100 m, spherical coords =
      profile home, includes bluerov2 at z=-2. Boots headless: buoyancy + all 6
      thrusters + ArduPilotPlugin + IMU all load with zero errors.
- [x] **WO-13 — Confirm ArduSub boots & dives.** PASS: boots, arms (verified),
      dives 10 m at 0.82 m/s, ALT_HOLD holds depth <0.5 m/15s, symmetric ±0.82
      m/s vertical authority (surfacing works). Buoyancy trimmed to near-neutral
      (collision box 0.065->0.0632). Evidence `evidence/wo13_ardusub_dive_run.log`.
- [x] **CHECKPOINT 1 — PASS (both domains).** Surface: AUTO arming (WO-09),
      GPS spoof +50 m (true pose unchanged), AIS emulator+ghost+impersonate, C2
      (WO-10). Underwater: WO-13. Evidence `evidence/checkpoint1_regression.log`.

### Phase B (shared) — repeatable, domain-aware harness
- [x] **WO-14 — `tools/run_sim.sh`** (+ `tools/mav_bridge.py`). Profile-
      parameterized; per-stage health checks (gz model / :9002 / tcp:5760 /
      heartbeat); up|down|status. Validated both domains. Evidence
      `evidence/wo14_run_sim_harness.log`.
- [x] **WO-15 — `tools/run_attack_suite.py`.** Domain-aware; drives off the
      profile's ATTACKS set; verifies via MAVLink-vs-true-Gazebo-pose; PASS/FAIL/
      SKIP/N-A per attack + evidence log; `--boot` self-contained mode. Surface:
      gps/ais/c2 PASS. Underwater: c2 PASS; gps SKIP (surface-window only, WO-17);
      acoustic SKIP (WO-16); ais N/A. Evidence `evidence/wo15_attack_suite.log`.
- [x] **CHECKPOINT 2 — PASS (both domains, 0 failures).** Automated harness
      reproduces Checkpoint 1. Evidence `evidence/checkpoint2_automated.log`.

### Phase C Track U — underwater attack adaptation
- [x] **WO-16 — Acoustic-positioning spoofing.** `attacks/acoustic_spoof.py`.
      Submerged positioning = ExternalNav/VISION_POSITION_ESTIMATE (investigated,
      not GPS). Feed-true-when-off / feed-false-when-on; believed walked 11 m off
      true. Suite check PASS. Evidence `evidence/wo16_acoustic_spoof.log`.
- [~] **WO-17 — GPS spoofing during surfaced windows.** ACTIVE. See CURRENT
      POSITION note: needs a GPS EKF source active in the surfaced regime.
- [ ] **WO-18 — AIS spoofing, surfaced-only** (mostly done: suite marks ais N/A
      submerged; profile omits ais from the AUV attack set — just document).
- [ ] **WO-19 — C2 replay/inject vs ArduSub** (mostly shown: suite c2 check moves
      true pose 6.61 m; WO-13 dove via RC override — capture depth-effect evidence).
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

- 2026-07-29: CHECKPOINT 2 PASS (both domains, 0 failures) via the automated
  harness. WO-15 (run_attack_suite.py) done + committed. Next: WO-16 acoustic
  spoofing.
- 2026-07-29: WO-14 done — tools/run_sim.sh (+ tools/mav_bridge.py) boots either
  domain in one command with real health checks; validated both. Root-caused the
  recurring SITL-death: stdin EOF from `< /dev/null` (fixed via FIFO stdin).
- 2026-07-29: CHECKPOINT 1 PASS (both domains). Surface stack re-booted, all 3
  attacks + AUTO arming re-verified live; underwater per WO-13. Evidence
  `evidence/checkpoint1_regression.log`. Next: WO-14 run_sim.sh.
- 2026-07-29: WO-13 PASS — first end-to-end underwater run in the project.
  ArduSub + BlueROV2 + underwater world: arm/dive/hold-depth/full thruster
  authority all verified vs Gazebo ground truth. Trimmed model to near-neutral
  buoyancy for depth hold. Committed. Next: surface half of Checkpoint 1.
- 2026-07-29: WO-11 + WO-12 done. DAVE BlueROV2 vendored & repointed to the
  relay port; self-contained underwater world authored; both load clean
  headless (buoyancy + 6 thrusters + ArduPilotPlugin + IMU, zero errors).
  Committed. Next: WO-13 live dive test with ArduSub SITL.
- 2026-07-29: WO-10 done and evidenced. Surface stack torn down to free RAM.
  Surveyed underwater assets; found DAVE BlueROV2 + ocean worlds + ardusub.parm
  already on disk — big de-risk for WO-11/12. Wrote this state file. Starting
  WO-11.
