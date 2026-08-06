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

## SECURITY/INTEGRITY AUDIT (2026-08-02)

Swept the codebase for leakage + loopholes, goal-focused (a credible cyber-range
= blind detectors scored against ground truth they never saw). Results:
- **Ground-truth isolation: INTACT.** Only `tools/score_detectors.py` (offline)
  reads `attack_logs/*.csv`; attacks WRITE their own CSVs; detectors + the live
  dashboard path consume only live feeds. The AIS detector's `known_mmsi` is the
  vessel's openly-broadcast MMSI (operational, not attack ground truth) — verified.
- **Credential leak: NONE in this repo.** README warns a sudo password was once
  hardcoded; confirmed absent from the current tree AND all git history here (it
  lived in the pre-consolidation repos). Nothing to scrub.
- **Injection: guarded.** All subprocess calls are list-form (no shell); the one
  `bash -c` path (`/cmd/vehicle`) interpolates only a whitelisted profile.
- **Flask debug OFF** (no Werkzeug-debugger RCE).
- **FIXED — open control surface.** The `/cmd/*` endpoints (launch attacks / move
  vehicle / reboot sim) had no auth — a real loophole once exposed on LAN/tunnel.
  Added an OPTIONAL shared-token gate: `MCR_DASHBOARD_TOKEN` env (off by default).
  When set, every `/cmd/*` needs the token (`X-MCR-Token` header or `?token=`);
  read-only views stay open. UI forwards it from the page URL. `launch.sh` passes
  the env through; docs/DEPLOY.md documents safe exposure. Verified with the Flask
  test client (off→open; on→401 without / 200 with). Constant-time compare.
- Noted (not fixed, acceptable for a demo): wildcard SocketIO CORS on read-only
  telemetry; the built-in werkzeug dev server has no HTTPS.

## PACKAGING (2026-07-31) — Docker image + one-command launcher (WO-27)

Goal: "download → extract → run the launcher → see the sim, set up the vehicle,
check the dashboard." Chosen delivery: a **single Docker image** carrying the
whole stack, with BOTH the web dashboard and the Gazebo 3D GUI (X11 forwarding).

Key design: the repo's launchers are already `$HOME`-relative, so the image just
reproduces the reference `$HOME` layout and `run_demo.sh`/`run_sim.sh` run
UNCHANGED (no code rewrite). New files:
- `deploy/Dockerfile` — Ubuntu 24.04 + ROS2 Jazzy + Gazebo Harmonic + ArduPilot
  (rover+sub @ pinned 1f6e646d2a) + ardupilot_gazebo (@082a0fe) + SITL_Models +
  dave (BlueROV2) + this repo with VRX (vendored @7609d1bd) colcon-built inside.
  Mirrors sim_config/install_*.sh + build_*.sh. Layered so a repo edit only
  rebuilds the cheap tail.
- `deploy/entrypoint.sh` — re-entrant in-container verbs (up/gui/switch/status/
  down/attack/shell); PID1 = `up` boots run_demo + stays alive.
- `deploy/requirements.txt` — pinned Python runtime deps.
- `.dockerignore` — keeps host-built ros2_ws/build|install OUT, vendored
  ros2_ws/src/vrx IN.
- `launch.sh` (host) — friendly one-command launcher: build/up/gui/switch/status/
  attack/shell/logs/down. Handles X11 (DISPLAY, /tmp/.X11-unix, xhost, /dev/dri,
  NVIDIA) + port 8080; opens the browser. macOS/Windows -> dashboard-only.
- `docs/DEPLOY.md` — build/run/share (docker save|load), GUI X11 setup, layout.

STATUS (update): IMAGE BUILDS (mcr:latest, 6.5 GB, all binaries+VRX baked in).
**bluerov2 (underwater) FULLY VALIDATED in-container**: sim boots, dashboard
serves (HTTP 200), acoustic attack -> 13 live detector alerts, AIS-None fix
confirmed. Runtime fixes landed: entrypoint dropped `set -u` (ROS setup.bash has
unbound vars -> instant exit-1); added iproute2(`ss`)+psmisc(`fuser`) the
launchers need; Dockerfile COPY-split so app edits don't recompile VRX.
**OPEN ISSUE — wamv (surface/VRX) does NOT boot in-container**: the VRX
sydney_regatta world hangs in the containerized gz server (`ros_gz create` loops
"Requesting list of world names" forever; `gz service /gazebo/worlds` times out).
Ruled OUT: --net=host gz-transport interference (fails on bridge net too), missing
X/GPU (fails with DISPLAY+/dev/dri forwarded too), Fuel download (VRX models are
local on GZ_SIM_RESOURCE_PATH). The gz server loads sydney_regatta.sdf then stalls
before serving worlds -- a world-load hang (VRX-in-Docker, known-hard). NEXT
OPTIONS: (a) ship bluerov2 as the reliable containerized demo + document wamv runs
natively on a GPU host; (b) keep debugging VRX headless (try xvfb-run wrapper /
GZ_PARTITION / run world standalone `gz sim -s -r sydney_regatta.sdf` to see the
hang). AWAITING USER DIRECTION.

--- earlier build-failure fixes (all in-repo) ---
Build iterated through THREE env failures, each fixed in-repo (so they won't recur):
1. Build DNS couldn't resolve archive.ubuntu.com -> `launch.sh` builds with
   `--network=host` (uses host DNS; host resolves the mirrors over IPv6).
2. pip clashed with ROS's dpkg-managed numpy/blinker ("Cannot uninstall ...,
   RECORD file not found") -> app deps now install into a `--system-site-packages`
   venv at /opt/mcr-venv (shadows, never uninstalls); entrypoint prepends it to
   PATH; requirements.txt trimmed to just pymavlink/pyais/Flask/Flask-SocketIO.
3. ArduPilot install-prereqs + rosdep pip on Ubuntu 24.04 PEP-668 ->
   `ENV PIP_BREAK_SYSTEM_PACKAGES=1` in the image.
The build has since been interrupted twice by SESSION BOUNDARIES (not failures) --
buildkit cache resumes it. **To resume: `./launch.sh build`** (cached layers make
it fast up to wherever it got). Remaining UNVALIDATED layers = ArduPilot waf
build (rover+sub) and VRX colcon build; watch those. After it builds:
`./launch.sh up` -> http://localhost:8080, `./launch.sh gui` -> 3D.
NOTE: all packaging + the detection-audit fixes are UNCOMMITTED.

## DETECTION/ALERTS AUDIT (2026-07-31) — all 4 detectors verified, 3 fixes landed

Triggered by "the acoustic alert isn't firing." Root-caused and audited the whole
alert path live in both domains. **All four rule-based detectors work** — surface
precision 1.00 / recall 1.00 (gps+ais+c2), underwater 1.00 / 1.00 (acoustic),
**zero false positives** in either domain (C2 does NOT false-fire during AUTO nav).
There is no ML in this project by design (roadmap WO-23 = rule-based detectors).

Root cause of "acoustic alert never fires": a **profile/sim mismatch** — the
dashboard was running profile `bluerov2` (underwater) while the booted sim was
actually the WAM-V rover. The rover silently ignores the underwater
VISION_POSITION_ESTIMATE, so the belief never drifts and no alert fires, with no
error anywhere. Booting the real ArduSub stack: acoustic fires (12 live alerts, 1.00/1.00).

Fixes landed this pass:
1. **Mismatch guard** (`dashboard_server.py` `_domain_matches_vehicle` + red UI
   `#warnbar`): the dashboard now checks the autopilot HEARTBEAT MAV_TYPE against
   the profile domain and warns loudly if they disagree — so this silent-no-alert
   trap can't recur.
2. **Scorer auto-scoping** (`score_detectors.py`): the git-tracked
   `attack_logs/*.csv` accumulate windows across ALL past runs, so the plain
   documented command scored one run against months of history → bogus ~0.03
   recall. Now auto-scopes to the alert file's own time span (explicit
   `--min-ts`/`--max-ts` still override). Plain command now reports the true 1.00/1.00.
3. **AIS suite verifier self-explains** (`run_attack_suite.py`): the suite's
   `ais_spoof` check binds the AIS port with SO_REUSEPORT; when a blind detector
   is concurrently bound, kernel REUSEPORT hashing routes ALL spoof datagrams to
   ONE listener, so the verifier can see 0 and false-FAIL. It now says so and
   points to the scorer as authoritative. Standalone (no concurrent detector) the
   suite is a clean PASS (gps+ais+c2).

Known design limitation (documented, not a bug): `AcousticDivergenceDetector`
fires on belief drift only while **disarmed** — an armed, station-keeping AUV
whose belief is spoofed would be missed. Fine for the demo (AUV idle when spoofed).

## OBJECTIVE-DOC AUDIT + PERFORMANCE METRICS + EVALUATION REPORT (2026-08-07)

Read `CYBER RANGE.docx` (the funding-facing Phase I proposal, root of repo) end
to end and audited the codebase against it. Findings: every in-scope item
(GPS/AIS/C2 attacks, rule-based detection, live dashboard) is done and
exceeded for the surface vehicle. The dual-domain (underwater AUV) work and
the third vehicle (BlueBoat) are OUTSIDE that doc's stated Phase I scope
(explicitly surface-only; "multi-vessel fleet simulation" is listed as
out-of-scope) — kept per user direction, just noted here as a scope
deviation, not fixed. Two docx-required items were genuinely missing and are
now built:

1. **Detection latency** — `tools/score_detectors.py` now computes, per
   attack family, the time from an attack's action start to its first
   matching alert (mean/median/p95/max), alongside the existing
   precision/recall. Handles the one asymmetric ground-truth case: C2's
   `inject_rc_override` logs a single row *after* its multi-second loop, so
   its logged duration is used to recover the true action start (see the
   module docstring). Refactored the scorer's core into an importable
   `score()` function (single source of truth for the CLI table AND the
   report). Verified unchanged precision/recall on existing evidence
   (wamv 1.00/1.00, bluerov2 1.00/0.82) — the latency addition is purely
   additive.
2. **System performance overhead** — `detection/run_detectors.py` now
   self-samples via the stdlib `resource` module (CPU time, peak RSS) and
   `time.perf_counter()` around each detector `.update()` call (per-event
   processing time), writing `evidence/detector_overhead_<profile>.json` at
   exit. Framing: the detectors are a passive tap, never inline with vessel
   control, so this IS the whole overhead the monitoring layer adds to the
   system. Smoke-tested standalone (no live SITL) — survives a dead MAVLink
   thread and null-safe reports 0 events; the synthetic 0-event artifact was
   deleted, not committed.
3. **Scenario evaluation report** — new `tools/generate_report.py` compiles
   every profile with a `detector_alerts_*.jsonl` into one self-contained
   `evidence/evaluation_report.html` (cross-vehicle summary table + per-attack
   detail + overhead panel per vehicle + methodology section). Verified
   rendering in-browser (dark mode via `prefers-color-scheme`, both profiles'
   tables correct).

**Also fixed while auditing**: `attack_logs/gps_spoof_ground_truth.csv` had
grown to 330K rows / 57MB (git-tracked, appended every run since inception —
was almost the entire 177MB `.git`). Trimmed to the two most recent sessions
(commit 656c0b0, corrected in 6d22aa3 after the first trim accidentally kept
a stray session that didn't overlap `evidence/detector_alerts_wamv.jsonl`'s
window — caught because the scorer's gps_spoof recall dropped to 0/0 after
the first trim; re-verify precision/recall after ANY ground-truth trim, don't
just check the file shrank). `__pycache__` dirs + `eeprom.bin` (untracked,
gitignored) also deleted.

**Not done, flagged not built**: the docx's "five isolated nodes, each a
separate container or VM" architecture — current deploy (WO-27) is one
monolithic Docker image. Not addressed this pass.

Next, if resumed: run `detection/run_detectors.py` live against a booted
stack (wamv and bluerov2) to collect real `detector_overhead_*.json` samples
(none exist yet — the report currently shows "n/a" for CPU/RSS on both
profiles, honestly, since no live-sampled overhead data has been generated
since the instrumentation landed), then regenerate the report.

## CURRENT POSITION

- **PROJECT COMPLETE (against stated scope).** CHECKPOINT 6 (final acceptance
  gate) PASS. Every mandatory work order and all six checkpoints are done. Only
  the two explicitly-OPTIONAL items remain if ever wanted: WO-22 (a second AUV,
  e.g. dave's bluerov2_heavy — mirror WO-21 underwater) and WO-27 (a one-command
  container). Neither is required.
- **Last completed: CHECKPOINT 6 — final acceptance.** Consolidates fresh CP4
  (all 3 vehicles, all attacks) + CP5 (detection/scoring both domains) + a
  contract sweep. Evidence `evidence/checkpoint6_final_acceptance.log`.

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
- [x] **WO-17 — GPS spoofing during surfaced windows.** Investigation +
      finding: this BlueROV2/ArduSub is ExternalNav in all regimes; SIM GPS
      doesn't track the FDM relay, so GPS spoofing has no effect on it (acoustic
      spoof covers position). Surfacing mechanism demonstrated (ascent 0.88 m/s,
      GPS fix available at surface); config path for a GPS-source vehicle
      documented. Evidence `evidence/wo17_gps_surfaced_windows.log`.
- [x] **WO-18 — AIS spoofing, surfaced-only.** Enforced: profile ais:null +
      omitted from AUV attacks; suite reports N/A submerged; ais_spoof.py reused
      as-is on the surface. Evidence `evidence/wo18_wo19_underwater_attacks.log`.
- [x] **WO-19 — C2 replay/inject vs ArduSub.** Forged RC override moved the AUV's
      TRUE depth +8.25 m (attacker seized vertical control) + suite c2 PASS.
      Evidence `evidence/wo18_wo19_underwater_attacks.log`.
- [x] **CHECKPOINT 3 — PASS (both domains, 0 failures).** Every applicable attack:
      surface gps/ais/c2; underwater acoustic/c2. Evidence
      `evidence/checkpoint3_full_attack_set.log`.

### Phase D — generalize beyond one vehicle per domain
- [x] **WO-20 — Vehicle model contract + validation script**
      (`tools/validate_vehicle.py`; profiles self-describe via `model_sdf`).
      wamv+bluerov2 ALL PASS; broken profile → 4 faults caught.
- [x] **WO-21 — Second surface vehicle (BlueBoat).** Different hull/thrusters,
      gz-direct `surface_harbor` world, distinct AIS identity. Vendored + swapped
      hydro to gz-sim standard + box buoyancy (floats at waterline) + navsat.
      Generalized the harness: run_sim.sh reads each profile's `world` config,
      run_attack_suite.py derives pose topic per profile. validate_vehicle.py:
      ALL PASS. Suite: gps/ais/c2 all PASS. Evidence
      `evidence/wo21_second_surface_vehicle.log`.
- [ ] **WO-22 (optional) — Second underwater vehicle.** Optional; not done.
- [x] **CHECKPOINT 4 — PASS.** All three vehicles (wamv VRX, blueboat gz,
      bluerov2 gz) regression-clean through the generalized harness; original two
      not broken. Evidence `evidence/checkpoint4_vehicle_set.log`.

### Phase E (shared) — detection + evaluation  [DONE]
- [x] **WO-23 — Rule-based detectors per domain.** `detection/detectors.py` +
      `detection/run_detectors.py` (blind live tap). Surface GpsJump/AisConflict/
      C2Override; underwater AcousticDivergence/C2Override. Live-validated.
- [x] **WO-24 — Alert layer on the dashboard.** `dashboard_server.py`
      detector_thread emits `attack_alert`; template shows a live alerts panel.
- [x] **WO-25 — Offline scoring harness** (`tools/score_detectors.py`). Only
      reader of ground truth; precision/recall per attack per domain.
- [x] **CHECKPOINT 5 — PASS.** Both domains, recall 1.00; surface precision 1.00,
      underwater 0.82. Evidence `evidence/wo24_checkpoint5_detection.log`.

### Phase F — designer-facing packaging
- [x] **WO-26 — `docs/DESIGNER_GUIDE.md`.** Front-door guide: quick start,
      reading results, detection+scoring, adding a vehicle (via the WO-20
      contract), ports.
- [ ] **WO-27 (optional) — one-command setup** (container). REMAINING.
- [ ] **CHECKPOINT 6 (final acceptance gate)** — after WO-21 (+ optional WO-27).

---

## Running notes (append newest at top; keep terse)

- 2026-08-07: Added the two docx-required metrics that were missing (detection
  latency in score_detectors.py, system overhead self-sampling in
  run_detectors.py) + tools/generate_report.py compiling both into
  evidence/evaluation_report.html. Also fixed the runaway gps_spoof ground
  truth CSV (330K rows -> ~3K, was most of .git). See the dated section above
  for details/caveats.
- 2026-07-30: CHECKPOINT 6 (final acceptance) PASS -> PROJECT COMPLETE against
  stated scope. All mandatory WOs + all 6 checkpoints done. Only optional
  WO-22/WO-27 remain if ever wanted.
- 2026-07-30: WO-21 + CHECKPOINT 4 PASS. Second surface vehicle (BlueBoat) boots
  + passes all surface attacks; harness generalized to a per-profile world
  config; all three vehicles regression-clean. Phases A–F now all complete;
  only optional WO-22/WO-27 + final CHECKPOINT 6 remain.
- 2026-07-29: PHASE E COMPLETE + CHECKPOINT 5 PASS. Detection subsystem
  (detectors blind on live feeds + offline scorer + dashboard alert layer). Live
  both domains: surface 1.00/1.00, underwater recall 1.00 / precision 0.82. Did
  Phase E before Phase D by design. Remaining: Phase D (WO-20/21/22, CP4) +
  Phase F (WO-26/27, CP6).
- 2026-07-29: PHASE C COMPLETE + CHECKPOINT 3 PASS. WO-16 acoustic_spoof (the
  submerged position spoof, belief walk-off), WO-17 GPS-surfaced finding
  (vehicle is ExternalNav), WO-18 AIS N/A-submerged enforced, WO-19 C2 true-depth
  seizure (+8.25 m). Both-domain full attack set green. Next: Phase D or E.
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
