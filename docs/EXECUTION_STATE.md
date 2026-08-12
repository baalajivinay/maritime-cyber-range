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

## LIVE DASHBOARD TEST (2026-08-07) — one fix landed, one real gap found deeper than expected

Booted `wamv` for real (`tools/run_demo.sh wamv up`) and drove the dashboard
through a browser instead of just reading code, to verify the previous
session's live-KPI/report work actually functions end-to-end. It does: GPS
spoof/AIS spoof both fired detectors, live latency badges showed correct
values (0.00-0.08s), live CPU/RSS/events-per-sec updated in real time, and
the rich `/cmd/report` overlay matched what was observed live.

**Fixed and verified live (commit 1ca5379)**: `status_update` (vehicle label
+ which attack buttons apply) was only ever broadcast once, right after
`detector_thread`'s first heartbeat during boot — before any browser
normally connects. Every dashboard load after that showed generic "Live
Monitor" and all four attack buttons regardless of domain (confirmed:
Acoustic spoof visible on the surface WAM-V). Fixed via a `socketio.on
('connect')` handler that sends the (static, constants-derived) label/attack
list directly to each new client. Reproduced clean on two separate boots
after the fix.

**RESOLVED (2026-08-07, later same day)**: the C2 RC-override half of this
was root-caused and fixed while building `targets/`/`tools/test_target.py`
(the vehicle-agnostic resilience tester, see below). Actual cause:
`dashboard_server.py`'s `cmd_conn()` used `source_system=250`. ArduPilot
only honors `RC_CHANNELS_OVERRIDE` from the sender matching `SYSID_MYGCS`
(default `255`) — with 250 it silently drops the override, zero error,
which looks exactly like a dead actuator/Gazebo bridge but isn't one. Fixed
(`source_system=255`) and verified live with precise timing: speed rises
0 -> 2.24 m/s starting at t=6.6s (matching the 6.5s arm/mode-switch
sequence), holds through the full 8s override window, decays after
release. `attacks/c2_replay.py`'s own standalone `connect()` was never
affected (it doesn't override pymavlink's default, which is already 255) —
this bug was isolated to the dashboard's `cmd_conn()`.

**`goto()`/click-to-navigate is a SEPARATE, still-open question** — its
MAVLink connection already used the (correct) default 255, so this same
fix does not explain why AUTO-mode navigation didn't move the vehicle.
Untouched since the original finding; still needs the ArduPilot
failsafe/param investigation described below if picked back up.

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

- 2026-08-12 (full repo doc audit + cleanup + new master context doc): User
  asked to recheck every doc against current reality, update programs/docs,
  delete unnecessary "old idea" docs, and write a universal pin-to-pin
  context doc so a fresh session (human or AI) can get pitch-perfect on the
  whole project without reconstructing it from git history. Read every
  doc/program end to end before writing anything, rather than assuming
  prior docs were still accurate.
  - **Real accuracy gap found and fixed**: `docs/ARCHITECTURE.md` was
    still describing the Phase-1 surface-only/WAM-V-only architecture --
    no underwater domain, no `vehicle_twins/`/`targets/` config layers,
    missing 3 of the project's 8 MAVLink ports (the `test_target`/
    `gps_feeder`/`vision_feeder` ports added since), and it asserted the
    `accel_body` arming bug as a live "known pre-existing issue" -- that
    bug was fixed back at WO-09, over a hundred commits ago. Fully
    rewritten to the current dual-domain state, verified against
    `constants.py`'s actual port defaults and a `grep` for every relevant
    function name before writing, not copied from the stale version.
  - **Deleted** (superseded, recoverable via git history if ever needed):
    `docs/DEMO_GUIDE.md` (legacy profile-based presentation script, already
    self-flagged as superseded, fully covered by `docs/TWIN_DEMO_GUIDE.md`);
    `docs/Maritime_Cyber_Range_Progress_Report.docx` (a snapshot from
    2026-07-27 -- predates even the accel-sign arming fix -- fully
    superseded by this file); three throwaway `targets/*.json` dev/
    verification configs (`gps_test_converged`, `gps_test_fresh`,
    `standalone_test`) plus their `target_runs/` evidence -- one-off
    artifacts from early Phase 2 whose job (proving vehicle-agnosticism)
    was already done and is already documented here; an untracked leftover
    `target_runs/mass_vulnerable_wamv/` run; stray `__pycache__/` dirs
    (never tracked, `.gitignore`'d already, just filesystem clutter).
  - **Updated for accuracy**: `docs/ROADMAP.md` (added a header marking it
    historical -- its own scope is 100% complete and it predates both the
    resilience-tester pivot and the real-vehicle-twin rebuild, neither of
    which it mentions); `docs/TWIN_DEMO_GUIDE.md` and both REMUS-100 twins'
    `README.md` (added the AUV navigation-bug disclosure from the
    2026-08-10 entry below at the exact point a reader would hit it --
    previously only `EXECUTION_STATE.md` itself had this, so a reader
    landing directly on a twin's own README or the demo guide wouldn't
    have known); `README.md`, `docs/DEPLOY.md`, `docs/DESIGNER_GUIDE.md`
    (fixed now-dangling references to the deleted `DEMO_GUIDE.md`).
  - **`docs/Maritime_Cyber_Range_Plain_Language_Guide.docx` rewritten**
    (still referenced the retired `mass_vulnerable_wamv`/
    `mass_resilient_blueboat`/`auv_vulnerable_bluerov2`/
    `auv_resilient_bluerov2_hardened` twin names throughout section 4's
    table, section 8's commands, and section 10's results table -- edited
    directly via the docx XML, same workflow as the earlier PPT build this
    session, verified correct by re-rendering to PDF/JPG and reading every
    changed page, not just trusting the XML edit). Also added the same
    navigation-bug caveat as a new row in its plain-language troubleshooting
    table, and refreshed its "prepared"/"most recently verified" dates.
  - **`CYBER RANGE.docx`** (the original founding project brief -- Navy/
    iDEX framing, Phase I scope, the two-student division of labor) moved
    from the repo root into `docs/` for organization; content read and
    confirmed still relevant as origin-story context, left otherwise
    unchanged.
  - **New**: `docs/PROJECT_CONTEXT.md` -- the requested universal doc.
    Single file covering: why the project exists, the one-paragraph
    architecture, the full 3-phase pivot history condensed to one page,
    every component/directory, the full tools-layer table, all 4 twins'
    real hardware + verified results + verdict methodology, current known
    issues (including this session's earlier AUV yaw-fix finding, stated
    precisely -- fixed vs. still-open, not glossed over), this cleanup
    pass itself, and a full doc map. Positioned as the new #1 "start here"
    entry in `README.md`'s documentation table, ahead of
    `TWIN_DEMO_GUIDE.md`. Every specific claim in it (function names,
    class names, file existence, ports) was grep/read-verified against the
    live repo while writing, not transcribed from memory of older docs --
    e.g. confirmed `sim_config/models/plane_spike/` has zero references in
    any `profiles/*.json`/`targets/*.json` before calling it an orphaned
    research artifact, confirmed `believed_thread`/`gz_pose_thread`/
    `detector_thread`/`overhead_emitter`/`DetectorSuite` are real current
    names via `grep`.
  - Not touched, deliberately: `evidence/` (Phase 1's historical checkpoint
    logs -- still cited by `docs/ROADMAP.md`'s checkpoint table, left as
    the historical record it is), `ros2_ws/src/vrx` (the VRX submodule --
    still load-bearing for the legacy `wamv` profile), `profiles/
    {wamv,blueboat,bluerov2}.json` and their `sim_config/models/` (retired
    from the primary demo set but still fully functional and still the
    teaching/clone base for `docs/DESIGNER_GUIDE.md`/
    `docs/NEW_AUV_QUICKSTART.md` -- deleting them would be a functional
    regression, not a doc cleanup).
  - Nothing in this pass touched code behavior -- documentation and
    filesystem organization only. Uncommitted at the time of this entry;
    the day's earlier code changes (the yaw fix) are also still
    uncommitted -- both awaiting explicit "commit and push" per this
    project's standing rule of never committing without being asked.

- 2026-08-10 (presentation day -- AUV nav bug root-caused precisely, ONE real
  bug fixed, a SECOND deeper one found underneath and deliberately left
  alone): User asked for a full backend audit + to fix the AUV
  destination-tracking bug from the 2026-08-09 dry run if not yet fixed.
  Re-investigated live rather than trusting the old diagnosis.
  - **The old diagnosis (untuned PSC_POSXY_P/PSC_VELXY_* "copied from
    BlueROV2") was WRONG.** Confirmed live via PARAM_REQUEST_READ: those are
    pre-4.x parameter names that don't exist in this firmware build (current
    names are PSC_NE_POS_P / PSC_NE_VEL_P/I/D -- traced via
    AC_PosControl.cpp's own param-conversion table). The parm file's lines
    silently no-op at boot -- both REMUS-100 twins have always run ArduSub's
    plain default gains, not "BlueROV2's gains." Nothing to retune here.
  - **Real root cause, found instead**: `legit_vision_feeder()`
    (dashboard_server.py) and `acoustic_spoof.py`'s `run_feed()` both call
    `vision_position_estimate_send(..., 0.0, 0.0, 0.0)` -- hardcoding
    roll/pitch/**yaw** to zero. Both REMUS-100 twins set `EK3_SRC1_YAW=6`,
    making this feed the EKF's YAW source too, not just position. Sending a
    constant 0.0 tells the EKF "always facing north" regardless of the
    vehicle's real heading. Confirmed live: at rest, ArduPilot's own
    `ATTITUDE.yaw` read ~0 rad while Gazebo's true yaw for the same instant
    was ~1.78 rad (~102 deg). Reproduced the exact 2026-08-09 failure
    signature standalone (short-range goto: net progress then a full
    reversal back near the start point, `NAV_CONTROLLER_OUTPUT.wp_dist`
    reading 0 while true distance was still ~80m) with a scripted repro that
    replays goto()'s exact mission-upload sequence and watches true Gazebo
    position continuously.
  - **Fixed**: `acoustic_spoof.read_true_ned()` now also parses the
    orientation quaternion from the same Gazebo pose block (previously only
    position was extracted -- the old code's block-termination check fired
    at the position sub-block's own closing brace, before the orientation
    sub-block was ever reached) and yields a real NED compass yaw
    (`yaw_ned = pi/2 - yaw_enu`, ENU->NED conversion derived and sanity
    checked, not guessed). Both callers now send this real yaw instead of a
    hardcoded 0.0. `acoustic_spoof.py`'s own attack path (`run_feed`)
    deliberately still forges POSITION only, never yaw -- a false heading
    would be a second, uninteded corruption unrelated to the position-spoof
    attack this module models.
  - **This fix is real and verified correct in isolation** (ArduPilot's
    believed heading now tracks Gazebo truth continuously, confirmed live)
    but **exposed a SECOND, deeper bug it had been masking**: with a
    correct heading fed from the start, both REMUS-100 twins now hold
    position and report `wp_dist=0`/near-zero thruster output IMMEDIATELY
    on a fresh AUTO mission, i.e. they don't move toward the destination AT
    ALL (worse for a live demo than before, which at least drove partway
    there before diverging). Confirmed NOT a mission-upload bug (MISSION_ITEM_INT
    readback shows the correct destination coordinates, MISSION_CURRENT
    confirms it's targeting the right waypoint) and NOT a race (reproduced
    deterministically 3/3 times, including retrying on an already-converged,
    fully-settled EKF). Best current hypothesis, not yet confirmed: an
    earth-frame-to-body-frame rotation issue in how ArduSub's position
    controller output gets applied to REMUS-100's 6-thruster vectored mixer
    once heading is genuinely non-zero -- i.e. a motor-mixing/SITL-config
    level issue, not something fixable by touching the feeder or dashboard
    code again. This has never been proven working for ANY vehicle in this
    project's underwater vectored-thruster line, REMUS-100 or the earlier
    BlueROV2 -- AUTO-mission horizontal waypoint tracking specifically (not
    arm/dive/RC-override, all of which stay fully verified) was never
    actually confirmed accurate before the 2026-08-09 dry run first looked
    for it.
  - **Deliberately NOT chased further today** -- diagnosing a motor-mixing/
    frame-rotation issue inside ArduSub's position controller needs the
    same iterate-and-test cycle this project has always required for
    control-loop changes (see the CUSV buoyancy trim, 3 iterations), which
    does not exist minutes before a live presentation. The yaw fix stays
    (objectively correct, zero downside, and c2_replay's mode_change/
    rc_override verdicts re-verified byte-identical after landing it --
    VULNERABLE/VULNERABLE, detectability 1.0, `target_runs/
    auv_vulnerable_remus100/20260812T204332/verdicts.json`). The AUV
    waypoint-navigation bug itself is still open.
  - **Recommendation is UNCHANGED from 2026-08-09**: do not live
    click-to-navigate demo the AUV twins on the dashboard map -- use
    `mass_vulnerable_cusv`/`mass_resilient_cusv` for the navigation/movement
    visual (unaffected by any of today's changes -- surface twins don't use
    `acoustic_spoof.py` at all). Demonstrate the AUV twins via the C2
    command buttons (mode-change, RC-override) and/or the `test_target.py`
    CLI report.
  - Full teardown clean (`ps`/`ss`) after every test this session.

- 2026-08-09 (final pre-presentation dry run -- found a 6th real issue, NOT
  fixed, disclosed instead): User asked for one more full dry run plus a
  constraints/roadmap writeup the night before presenting. Validate +
  movement + CLI regression all repeated clean for all 4 twins (see below)
  -- but this pass watched AUV navigation CONTINUOUSLY over 60-90s instead
  of spot-sampling, and found a real, previously-invisible problem:
  **`auv_vulnerable_remus100`/`auv_resilient_remus100_hardened` do not
  track a clicked destination correctly.** At long range (~800m) the
  vehicle oscillates/circles, covering only ~34m of net progress in 90s
  despite repeatedly hitting 5.6 m/s at 100% throttle -- and at short range
  (~80m) it's worse: distance to destination increased monotonically
  (82.6m -> 375.4m over 56s), i.e. actively diverging, not just
  inefficient. Confirmed via `MISSION_ITEM_INT` readback that the uploaded
  waypoint coordinates are exactly correct (ruling out a goto()/frame-math
  bug) -- `NAV_CONTROLLER_OUTPUT`'s `wp_dist`/`target_bearing` were
  internally inconsistent with the vehicle's own verified true position,
  pointing at an ArduSub position-controller/EKF-origin behavior, not a
  dashboard bug. Both REMUS-100 twins share byte-identical `PSC_POSXY_P`/
  `PSC_VELXY_P/I/D` gains (confirmed by diffing the two parm files),
  apparently copied from BlueROV2 -- REMUS-100 can generate a much higher
  top speed than BlueROV2, and these gains are the classic shape of
  "tuned for a slower vehicle, unstable on a faster one."
  - **Why this was never caught before**: navigation was UNREACHABLE for
    either AUV twin until today's earlier `legit_vision_feeder` fix (no
    position source at all -> AUTO mode-entry silently refused). This
    isn't a regression from anything landed today -- it's a pre-existing
    tuning gap that simply had no way to become visible until arming and
    AUTO-entry started working.
  - **Deliberately NOT fixed this pass** -- blind-tuning an ArduSub
    position controller (PSC_*/WPNAV_*) the night before a presentation,
    without the normal iterate-and-re-test cycle this project's other
    tuning work (e.g. CUSV's buoyancy trim, 3 iterations) always used, is
    a real risk of making it worse in a way that's harder to notice than
    "doesn't track well." Disclosing honestly and recommending a
    workaround for tomorrow (below) instead.
  - **What's unaffected, confirmed via the same pass**: arming, mode
    changes, C2/RC-override attacks, and the full `test_target.py` CLI
    verdict suite all work identically on both AUV twins regardless of
    this bug -- none of that code path depends on AUTO waypoint tracking.
    Re-ran the full CLI suite on all 4 twins headless as part of this same
    dry run: byte-identical verdict shapes to every prior run this session
    for all 4 (`mass_vulnerable_cusv` VULNERABLE/VULNERABLE/VULNERABLE
    1.0/1.0/1.0; `mass_resilient_cusv` RESILIENT/INCONCLUSIVE/N-A/N-A,
    0.0 c2 recall; `auv_vulnerable_remus100` VULNERABLE/VULNERABLE, 1.0;
    `auv_resilient_remus100_hardened` RESILIENT/INCONCLUSIVE, 0.0).
  - **Recommendation for tomorrow's presentation**: don't live
    click-to-navigate demo the AUV twins on the dashboard map. Use
    `mass_vulnerable_cusv`/`mass_resilient_cusv` for the navigation/
    movement visual (both fully solid, re-confirmed this pass). For the
    AUV twins, demonstrate via the C2 command buttons (mode-change,
    RC-override -- both fully live and correct) and/or the
    `test_target.py` CLI report, neither of which touches the broken
    navigation path.
  - Filed as a next-stage item (see roadmap) rather than left silently
    undocumented.

- 2026-08-09 (5th real fix -- goto() arm retry was too short, presentation
  eve): User came back after the GPS+vision feeder fixes still seeing
  `mass_resilient_cusv` stuck AUTO/DISARMED ("i dont know what you fixed").
  Found an actively-running session on this machine (started 22:34, AFTER
  all the code fixes -- ruled out "stale process running old code" as the
  explanation) and inspected it live rather than re-asserting the fix was
  good: `GPS_RAW_INT` showed a clean `fix_type=3`/10 satellites (the feeder
  IS working), and a direct manual arm attempt succeeded INSTANTLY. So the
  vehicle COULD arm -- the bug was that `goto()`'s own arm-retry loop only
  tries 6 times over ~6 seconds. `goto()` is fire-and-forget per click and
  never self-retries, so any click landing before the EKF finished
  trusting the fresh GPS fix (confirmed varies from ~10s up to several
  minutes depending on exact boot timing) failed PERMANENTLY -- the
  vehicle just sat there until the user knew to click "Set Destination"
  again, which is not a reasonable thing to expect from someone at a demo.
  **Fix**: extended the retry loop from 6 attempts to 90 (still 1s apart,
  still bails out immediately once armed -- costs nothing on an
  already-converged vehicle). **Verified properly this time**: full clean
  teardown + fresh cold boot + a single goto() click fired at the
  worst-case moment (immediately after boot, not after any settle wait)
  for ALL FOUR twins back to back, watching continuously (not
  spot-checking) until each one either armed+moved or the run gave out:
  `mass_vulnerable_cusv` armed 7s/moving 13.5s (0.83 m/s), `mass_resilient_cusv`
  armed 27s/moving confirmed 1.05 m/s, `auv_vulnerable_remus100` armed
  7s/position genuinely changing by 12.5s, `auv_resilient_remus100_hardened`
  armed 7s/position genuinely changing by 72.5s. All four self-recovered
  from a single click with zero manual intervention. Full teardown clean
  after every boot, confirmed via `ps`/`ss`.
  - Lesson for next time this class of bug shows up: a `curl`
    "ok:true"/"200" response from an async endpoint proves the request was
    ACCEPTED, not that the underlying action SUCCEEDED -- `/cmd/goto`
    always returns immediately since it launches a background thread.
    Every verification in this session that only checked the HTTP response
    without then watching live telemetry to confirm the actual outcome was
    incomplete, and this was the second time that gap let a real bug
    through undetected until the user found it live.

- 2026-08-09 (full-fleet movement audit -- 4th real fix, underwater twins):
  User pushed back after the GPS-feeder fix ("why the vehicle is not
  moving... i want all the twins to work properly") and asked for a
  thorough audit, not another point fix. Given the GPS bug's shape (no
  ambient position source outside an explicit attack), the obvious next
  question was whether the underwater twins had the same class of gap --
  checked rather than assumed either way.
  - **Confirmed live: yes, both REMUS-100 twins had it too, worse than the
    surface case.** Both `auv_vulnerable_remus100/remus100.parm` and
    `auv_resilient_remus100_hardened/hardened.parm` set
    `EK3_SRC1_POSXY=6` (ExternalNav) -- position comes from
    `VISION_POSITION_ESTIMATE`, and (per `attacks/acoustic_spoof.py`'s own
    docstring, already known) "without an external-nav feed its
    GLOBAL_POSITION_INT is 0,0." That feed previously only started inside
    `launch_attack()`'s `acoustic_spoof` branch -- never as a baseline.
    Live-verified the actual failure mode (worse than the GPS case, not
    the same): `goto()` armed the vehicle fine, but ArduSub silently
    refused to enter AUTO at all (stayed in MANUAL, no error) and
    `GLOBAL_POSITION_INT` stayed frozen exactly at HOME the whole time --
    "it armed but the destination distance never counted down."
  - **Fix**: `legit_vision_feeder` in `dashboard_server.py`, the
    underwater twin of `legit_gps_feeder` -- reuses
    `attacks/acoustic_spoof.py`'s already-fixed `read_true_ned()` Gazebo
    pose parser (deliberately did NOT write a 4th copy of that regex
    parsing logic) rather than the attack module's `run_feed()` directly,
    specifically to avoid sharing that module's `state`/`_lock` (the
    forged-offset toggle) -- this feeder always sends the untouched true
    position, so when Acoustic Spoof is later launched its own separate
    `run_feed()` call has to compete with a still-running legitimate
    signal, not be the only signal the vehicle ever sees (same design
    intent as the GPS feeder). New `MAVLINK_VISION_FEEDER_PORT`
    (`constants.py`, same computed-default pattern, added to
    `tools/mav_bridge.py`'s fan-out). Gated on `DOMAIN == "underwater"`.
  - **Verified live, both AUV twins, full `goto()` sequence**: arm +
    AUTO entry + genuine position change (lat/lon actually moving, not
    frozen) on the very first attempt post-boot for BOTH twins -- unlike
    the surface GPS fix, this one needed no EKF settle-time wait at all.
  - **Zero regression**: re-ran the full `test_target.py` CLI suite
    (headless, `run_vehicle.sh`) against both AUV twins after the fix --
    byte-identical verdict shapes to every prior run this session
    (`auv_vulnerable_remus100`: VULNERABLE/VULNERABLE, detectability 1.0;
    `auv_resilient_remus100_hardened`: RESILIENT/INCONCLUSIVE,
    detectability 0.0) -- expected, since `legit_vision_feeder` only runs
    inside `dashboard_server.py`'s process, which isn't alive during a
    headless CLI run.
  - `docs/TWIN_DEMO_GUIDE.md` updated with this finding alongside the GPS
    one. **Net result: all 4 primary twins now genuinely navigate live on
    the dashboard from a fresh boot** -- this was NOT true before today's
    audit for 3 of the 4 (only `mass_vulnerable_cusv` worked out of the
    box; the other 3 each had a distinct real bug blocking movement, found
    only because each was actually clicked through live rather than
    assumed working from a prior CLI-only pass).

- 2026-08-09 (dashboard Q&A + 3 real fixes, incl. a resilient-twin arming
  bug found from a live screenshot): After the fixes below were already
  committed, user sent a screenshot of `mass_resilient_cusv` mid-use:
  Mode=AUTO, Armed=DISARMED, Speed=0.00, "178.9m remaining -- en route"
  frozen. Root-caused live (not assumed): `GPS_RAW_INT` showed
  `fix_type=1`/0 satellites -- **the resilient twins have literally no
  ambient GPS position source at all**, since `GPS1_TYPE=14` switches them
  to the external `AP_GPS_MAV` driver and nothing was feeding it
  `GPS_INPUT` outside of a `test_target.py` run. `goto()` could still set
  AUTO and upload a mission, but its own arm-retry loop silently failed
  every time -- exactly the frozen state in the screenshot. This was a
  real, presentation-blocking gap beyond what `docs/TWIN_DEMO_GUIDE.md`
  previously documented (it only warned the GPS *panel* would look empty,
  not that the vehicle literally could never arm or move).
  - **Fix**: new `legit_gps_feeder` thread in `dashboard_server.py`, always
    running for surface twins, feeding the vehicle's own true Gazebo
    position as legitimate `GPS_INPUT` at 5Hz for the whole time the
    dashboard is up (reuses `attacks/gps_input_inject.py`'s
    `send_gps_input`, the exact mechanism already proven for the attack
    side). New dedicated `MAVLINK_GPS_FEEDER_PORT` (`constants.py`, same
    `.get()`-with-computed-default pattern as `MAVLINK_TEST_TARGET_PORT`,
    zero edits needed to existing `profile.json` files) added to
    `tools/mav_bridge.py`'s fan-out list so the port actually carries
    traffic. Harmless no-op for vulnerable twins (no `AP_GPS_MAV` driver
    listening without `GPS1_TYPE=14`), so it's unconditional rather than
    needing to know which twins are hardened.
  - **A second, real bug found getting the fix working**: the first version
    sent `GPS_INPUT` immediately after opening the connection and produced
    zero effect with no errors anywhere. Root cause: a fresh `udpin:`
    listener doesn't know `mav_bridge`'s ephemeral reply address until it
    has received at least one message FROM it -- exactly the same
    reason `goto()` already calls `wait_heartbeat()` before doing anything
    else. Added the same `wait_heartbeat(timeout=15)` before the send loop
    -- confirmed live (isolated python probe) that this alone was the
    difference between `GPS_RAW_INT.fix_type` staying 1 forever vs.
    becoming 3 with 10 satellites within ~1s.
  - **A third, genuine (not a bug) finding while verifying the fix
    end-to-end**: a `goto()` click sent ~10s after boot still failed to
    arm even with a valid `fix_type=3` GPS_RAW_INT already present --
    EKF3 needs a few seconds of *consistent* readings after a fix first
    appears before it trusts it enough to satisfy arming's GPS-health
    prearm check (the same phenomenon this project already characterized
    and named via `targets/gps_test_fresh.json` vs
    `targets/gps_test_converged.json`). The identical click retried after
    more settle time armed cleanly on `goto()`'s very first retry and the
    vehicle started moving (0.32->0.77 m/s). Documented in
    `docs/TWIN_DEMO_GUIDE.md` as "wait ~30-60s after boot before clicking
    a destination on a resilient twin" rather than attempting to code
    around real EKF physics this close to a presentation.
  - Does NOT affect `tools/test_target.py`'s CLI verification pass earlier
    today -- `legit_gps_feeder` only exists inside `dashboard_server.py`'s
    process, which isn't running during a headless `run_vehicle.sh` boot
    (the documented/recommended way to run the CLI tester). Underwater
    twins are unaffected too (`legit_gps_feeder` returns immediately for
    `DOMAIN != "surface"` -- they already get position via the separate,
    already-working acoustic/ExternalNav feed).
  - `docs/TWIN_DEMO_GUIDE.md`'s old note ("resilient twins' GPS panel won't
    show a live position on the dashboard, that's expected") is now WRONG
    and was corrected in place -- the panel works live now, the only
    remaining caveat is the EKF settle-time wait.

- 2026-08-09 (dashboard Q&A + 2 real fixes): User asked 7 questions after the
  full verification pass above, several of which led to live investigation
  and found genuine, fixable issues (not just explanations):
  - **Fix: `gps_true_update` socket emit was unthrottled.** `gz_pose_thread`
    (`nodes/monitor/src/dashboard_server.py`) emitted on every single
    `/pose/info` message with zero rate limiting -- measured live at
    ~112 emits/sec (2239 in 20s) vs. the believed-position feed's sane
    ~9/sec. This is what produced the user-reported "many dots appear
    randomly while moving": at that rate the 80-point trail buffer covers
    under a second of travel, so consecutive points sit millimeters apart
    on a meters-scale map and render as a scattered cluster instead of a
    line. Fixed with a `_TRUE_POS_EMIT_INTERVAL_S = 0.1` throttle on the
    EMIT only (`_last_true_pos` itself still updates every message, since
    `goto()`'s frame alignment needs the freshest value) -- measured live
    after the fix: ~13.6/sec, an ~8x reduction. Matches the exact throttling
    pattern already used for `attacks/gps_spoof.py`'s ground-truth CSV
    logging earlier this session.
  - **Fix: dashboard's live "Cut throttle -- stop" C2 command used the wrong
    PWM value.** User reported a C2 "hold the throttle" test on a vulnerable
    vehicle appearing not to work. Live investigation (direct MAVLink
    telemetry, bypassing the browser) found TWO separate, real explanations,
    only one of which was a bug:
    1. Mode-CHANGE C2 attacks (Force HOLD/MANUAL) work correctly regardless
       of current mode (confirmed AUTO->HOLD in <1s) -- not the issue.
    2. RC-override-style C2 attacks (Seize/Cut throttle) only affect vehicle
       modes where ArduPilot reads RC input directly (MANUAL/ACRO/STEERING)
       -- in AUTO/GUIDED/HOLD the nav controller owns throttle. The
       dashboard's own `_c2()` handler already knows this and force-switches
       to MANUAL + re-arms before injecting (confirmed correct) -- but the
       actual bug was the PWM value it then sent: `rc_stop` used 1300,
       assumed to be "well below trim = low throttle." Live-measured against
       the CUSV skid-steer twin, that assumption was wrong for this hull:
       the throttle-vs-PWM curve is symmetric around RC3_TRIM (1500) --
       deviation in EITHER direction drives throttle UP, not down (1100 and
       1900 both measured 100% throttle; only exactly 1500 measured 0%).
       1300 sat in the "wrong half," producing ~45% throttle instead of a
       stop -- enough residual thrust to look like "the attack partially
       worked" or "the vehicle is resilient," neither of which was true.
       Fixed by using exact RC3_TRIM (1500) for `rc_stop`, which is safe
       across any hull by definition (trim always means neutral). Re-verified
       live: throttle pinned at 0% for the full 8s window, speed decaying
       cleanly to a stop.
  - **Report enhancement** (user explicitly asked for more detail, then
    picked via AskUserQuestion: executive summary, per-attack timeline with
    raw evidence, methodology depth -- NOT charts): `tools/generate_target_report.py`
    gained `render_executive_summary()` (plain-language synthesis per
    target, no jargon) and `render_timeline()` (merges each run's own
    `*_ground_truth.csv` injection log + `alerts.jsonl` detection log into
    one chronological, elapsed-time table -- zero new data collection, both
    files already existed per run). Methodology section expanded with an
    explicit "no ML anywhere, this is rule-based state machines + timestamp
    matching against ground truth" paragraph and the mode-dependent
    RC-override caveat above, generalized for any reader. Regenerated and
    visually verified in-browser -- all three additions render correctly.
  - All fixes are additive/isolated (dashboard UI-only code paths, a new
    report-rendering function) -- no change to `tools/test_target.py`'s core
    attack/verdict logic, so the full verification pass immediately above
    this entry stays valid.

- 2026-08-09 (pre-presentation full verification): **All 4 primary twins +
  the external-target path re-verified live, end to end, with zero product
  bugs found.** User asked for a thorough pre-presentation check ("i dont
  want a single mistake to happen"), covering both the 4 owned twins and the
  claim that the tool works against a vehicle it doesn't own.
  - **Static validation**: `tools/validate_vehicle.py` clean PASS on all 4
    twins (`mass_vulnerable_cusv`, `mass_resilient_cusv`,
    `auv_vulnerable_remus100`, `auv_resilient_remus100_hardened`).
  - **A real scare that turned out to be self-inflicted, not a regression**:
    the first live `test_target.py` pass against `mass_vulnerable_cusv`
    came back wrong (`gps_spoof: RESILIENT` with `peak_delta_m: 0.01`,
    `rc_override: INCONCLUSIVE`) -- alarming since this is the *vulnerable*
    twin and should read VULNERABLE/VULNERABLE/VULNERABLE. Root-caused
    before treating it as a bug: an earlier failed attempt to background-boot
    the stack (a `... & disown` inside one shell call, which this project's
    own documented gotcha says doesn't survive the tool's call boundary) had
    actually left orphaned children alive -- a `ps aux` check found TWO live
    `gz sim` processes, TWO GPS-relay processes, TWO AIS emulators, all bound
    to the same world/ports from a single boot attempt. The properly-booted
    second attempt's spoof commands were evidently landing on the wrong
    orphaned relay instance some of the time, producing a near-zero measured
    offset despite the attack genuinely firing. Force-killed everything,
    confirmed a clean 7-process single-instance boot, and reran: two
    consecutive clean passes, deterministic
    `VULNERABLE`/`VULNERABLE`/`VULNERABLE`, detectability 1.0/1.0/1.0 --
    exact match to the documented result. **Lesson reconfirmed**: always
    `ps aux` after a boot to confirm single-instance before trusting a test
    result, especially after any nonstandard/manual process launch.
  - **All 4 twins, clean live pass, exact match to each twin's documented
    README table**: `mass_vulnerable_cusv`
    (VULNERABLE/VULNERABLE/VULNERABLE, 1.0/1.0/1.0),
    `mass_resilient_cusv` (RESILIENT/INCONCLUSIVE/N/A, matching the known
    GCS_SYSID_ENFORCE-blocks-GPS_INPUT-too interaction),
    `auv_vulnerable_remus100` (VULNERABLE/VULNERABLE, 1.0),
    `auv_resilient_remus100_hardened` (RESILIENT/INCONCLUSIVE, parity with
    `auv_resilient_bluerov2_hardened`'s own historical result). Every boot
    confirmed single-instance and torn down clean before the next.
  - **External-twin path re-proven, not just recalled from memory**:
    hand-launched a genuinely independent `ardurover --model rover` SITL
    instance (its own internal physics, not this repo's Gazebo/JSON-FDM
    stack; a throwaway Mumbai-coast home location; ports this repo doesn't
    own) using the project's own FIFO-stdin-keepalive trick so it survives
    background launch. Wrote `targets/presentation_external_smoke.json`
    exercising all 3 attacks (`gps_spoof` via the protocol-generic
    `gps_input` method, not `fdm_relay`; `ais_spoof`; `c2_replay`).
    `tools/validate_target.py` clean (1 expected warning: impersonate mode
    has no `own_mmsi` to impersonate). Full `test_target.py` run:
    VULNERABLE/VULNERABLE/VULNERABLE, detectability 1.0/1.0/1.0 -- proves
    the tool's core claim ("point it at any ArduPilot SITL, ours or not")
    still holds after all the CUSV/REMUS-100 work. Instance killed, config
    kept in `targets/` for reuse.
  - **Live dashboard click-through** (the surface the user's original
    complaint came from): booted `mass_vulnerable_cusv` via `run_demo.sh`,
    drove the real UI in the browser (not a bypassed HTTP probe) --
    clicked "Set Destination" then the map: `/cmd/goto` fired, vehicle
    armed, entered AUTO, and correctly closed distance on the destination
    at 1.05 m/s (matching the physics-fix numbers from the prior CUSV
    navigation entry, now re-confirmed through the actual click path, not
    just telemetry). Clicked "GPS Spoof": position-integrity panel correctly
    showed 49.9 m deviation ("believed position diverged from true"), alert
    fired in 0.08s, vehicle's true motion continued unaffected (correct --
    this is the vulnerable twin's *belief*, not its real state, being
    fooled). Clicked "Stop Attacks": deviation returned to ~0.1 m, a brief
    (~5s) MANUAL/DISARMED blip appeared then self-corrected back to
    AUTO/ARMED while resuming course -- read as a transient MAVLink state
    flicker during the abrupt spoof-to-real position snap-back, not a
    persistent bug (confirmed by rechecking a few seconds later). "Report"
    button fired `/cmd/report` 200 OK. Auto-stop-on-disconnect was NOT
    independently re-exercised this pass (the sandboxed browser pane
    auto-restores a phantom tab on close, so `_connected_clients` never hit
    0 no matter how the test tab was closed) -- the code path is unchanged
    since it was directly proven live in the 2026-08-08 dry run, so this is
    a sandbox limitation, not a gap in what got checked.
  - **Cross-target report regenerated clean**: `tools/generate_target_report.py`
    -- 8 targets, no NaN/traceback, correctly picked up every fresh run
    from this pass (confirmed by grepping the report for today's run-ts
    directories). `evidence/`/`target_runs/` cleaned of the one contaminated
    run directory from the orphaned-process incident above.
  - **Net finding: zero real product bugs this pass.** The one alarming
    result was fully traced to this session's own process-management
    mistake, not the twins or the tool. All 4 twins + the external-target
    path are presentation-ready as of this entry.

- 2026-08-09 (CUSV navigation): **Two real, distinct physics/config bugs
  found and fixed** while investigating a user-reported "vehicle deviating
  from the goal / speed too slow" symptom -- neither was the dashboard's
  goto()-race bug fixed earlier the same day (that one was real too, but
  didn't fully explain the symptom on its own). Diagnosed by watching
  live NAV_CONTROLLER_OUTPUT/VFR_HUD/SERVO_OUTPUT_RAW telemetry during an
  actual AUTO-mode run, not by reading code alone:
  1. **`sim_config/models/cusv/model.sdf`'s thruster links had no
     rotation** (`0 0 0`) -- compared directly against BlueBoat's own
     proven `motor_stbd_link`/`motor_port_link` poses
     (`sim_config/models/blueboat/model.sdf`), which both apply
     `-90 0 90` degrees. Without it, `gz-sim-thruster-system` generates
     thrust along the joint's local -Z axis, which stayed literally
     vertical (world frame) instead of being rotated into the hull's
     forward/aft axis -- confirmed live: throttle correctly ramped to
     100% chasing WP_SPEED but groundspeed stayed under 0.15 m/s. Fixed
     by applying the same rotation CUSV's own build should have carried
     over from BlueBoat originally.
  2. **CUSV had no `ardu_defaults` file at all** (neither twin), so it
     booted with ArduRover's factory defaults for a conventionally-
     steered vehicle (SERVO1_FUNCTION=26 GroundSteering, SERVO3_FUNCTION=
     70 plain Throttle) instead of skid-steer's differential mixing
     functions (73/74, ThrottleLeft/ThrottleRight). Confirmed live:
     SERVO_OUTPUT_RAW's servo1/servo3 stayed pinned identically
     regardless of a growing cross-track error -- the boat drove dead
     straight and never turned toward its waypoint at all. New
     `vehicle_twins/mass_vulnerable_cusv/cusv.parm` (+ wired via
     profile.json's `ardu_defaults`) and the same two lines added to
     `vehicle_twins/mass_resilient_cusv/hardened.parm` (ardu_defaults
     files aren't merged -- SITL only accepts one, so the hardened twin
     needs its own copy, not a reference). **BlueBoat has this same gap**
     (`profiles/blueboat.json` also has no `ardu_defaults`) -- not fixed
     here since it's not one of the 4 primary twins, but flagged as a
     likely-real, unverified issue there too.
  Verified live, before/after, same due-East waypoint test: groundspeed
  0.14 m/s (barely moving, throttle maxed) -> 1.05 m/s stable cruise;
  heading frozen at a fixed value while target_bearing drifted away and
  xtrack_error grew unboundedly -> heading locks onto target_bearing
  exactly, xtrack_error stays ~0.00 the whole run. A second test with a
  deliberate 90-degree-off target confirmed real differential steering
  (servo1/servo3 diverging, heading actively turning toward the new
  bearing). Then re-ran the full attack suite on both twins headless --
  identical verdicts to before (VULNERABLE/VULNERABLE/VULNERABLE and
  RESILIENT/INCONCLUSIVE respectively), confirming the navigation fixes
  didn't regress anything else.

- 2026-08-09 (twin cleanup): **Removed the 4 original reference twins**
  (`vehicle_twins/mass_vulnerable_wamv/`, `mass_resilient_blueboat/`,
  `auv_vulnerable_bluerov2/`, `auv_resilient_bluerov2_hardened/`) plus
  their `profiles/*.json` symlinks and their `target_runs/` evidence
  (including the older `wamv_local`/`blueboat_local`/`bluerov2_local`
  ad hoc runs) at the user's explicit request, now that CUSV/REMUS-100
  are fully live-verified as the primary demo set — this project now
  ships exactly 4 twins, not 8. Scope, confirmed with the user first:
  twin *packages* only, not the underlying hull models -- `sim_config/
  models/blueboat/`, `sim_config/models/bluerov2/`, the VRX-based WAM-V,
  and their base `profiles/wamv.json`/`blueboat.json`/`bluerov2.json`
  stay on disk (`docs/NEW_AUV_QUICKSTART.md`'s own tutorial still clones
  BlueROV2 as a starting point for a brand-new AUV twin, independent of
  whether BlueROV2 has its own `vehicle_twins/` package). Fixed the
  handful of now-dead cross-references this left behind in the kept
  twins' own files (`vehicle_twins/mass_resilient_cusv/{README.md,
  hardened.parm}`, `vehicle_twins/auv_resilient_remus100_hardened/
  {README.md,hardened.parm}` all cited the removed BlueBoat/BlueROV2
  twins by path as provenance for their hardening mechanism -- reworded
  to describe the same substance without a dead relative link) and
  rewrote `docs/TWIN_DEMO_GUIDE.md`'s "8 folder paths (4 primary + 4
  retained reference)" framing down to a plain 4.

- 2026-08-08 (real-hull rebuild, Phase C-fallback + Phase D): **REMUS-100
  (real US Navy shallow-water mine-countermeasures AUV) fully built on the
  proven ArduSub 6-thruster architecture, live-verified end to end,
  hardening re-confirmed with exact parity to BlueROV2's own result.**
  Follows directly from the prior entry's decisive ArduPlane-underwater
  spike failure and the user's explicit "go ahead with the REMUS-100
  fallback" instruction.
  - **Hull/mass/inertia/drag**: sourced from Thor I. Fossen's MIT-licensed
    `PythonVehicleSimulator` (`vehicles/remus100.py`) — L=1.6m, diameter
    0.19m, mass 31.9kg, prolate-spheroid-derived inertia/drag. Actuation is
    a disclosed simplification (6-thruster vectored frame, same proven
    architecture as BlueROV2, repositioned/rescaled for REMUS's slimmer
    hull) since no ArduPilot firmware supports the real fin-steered scheme
    — see `sim_config/models/remus100/model.sdf`'s header for the full
    citation trail (GitHub issue #21568, Blue Robotics community thread,
    the ArduPlane dead-end from the prior entry).
  - **Buoyancy trim took three live-tested iterations, each a genuine,
    distinct finding, not one bug fixed three times**: (1) an `<ellipsoid>`
    collision shape sank steadily (~0.44 m/s) despite staying level —
    `gz-sim-buoyancy-system` doesn't compute displaced volume correctly for
    ellipsoids in this Gazebo version, consistent with the same class of
    issue already worked around for every other vehicle's box geometry.
    Switched to a box. (2) The box, volume-matched to the spheroid mass
    calc, STILL sank at nearly the same rate — root-caused to a rho=1026
    (spheroid calc) vs the world's actual 1025 kg/m³ mismatch, reconciled
    everywhere in the file. (3) Even after that fix, a slower but real
    ~0.2-0.35 m/s sink persisted — traced to the 6 thruster links (0.05kg
    each, 0.3kg total) having mass but no `<collision>` geometry of their
    own, so the buoyancy plugin (which sums displaced volume per-link)
    silently never accounted for their weight; true system mass is 32.2kg,
    not 31.9kg. Final box: `1.6 x 0.14013 x 0.14013` m, solved for the
    WHOLE assembly's mass against the world's real density, erring ~4g
    positive (float, not sink, on any residual rounding) — live-confirmed
    stable, level, gently rising at the hand-calculated terminal velocity
    (~0.02 m/s asymptotic, matching the quadratic-drag prediction almost
    exactly).
  - **Full SITL boot, arm, and 6-thruster response confirmed live**:
    `tools/run_vehicle.sh vehicle_twins/auv_vulnerable_remus100 up` passes
    every health gate; EKF3 healthy (small variances, valid position);
    armed in MANUAL; RC-override on the Throttle channel visibly moved the
    two vertical thrusters (SERVO5/6: 1500->1300) while horizontal
    thrusters stayed neutral — correct, channel-selective response.
  - **A real ArduSub arm-flake, already known and already solved by this
    project's own tooling, re-encountered and correctly NOT mistaken for a
    new REMUS-100 bug**: ad hoc hand-test scripts saw intermittent
    "Arming motors" immediately followed by "Disarming motors". Root cause:
    ArduSub's `FS_PILOT_INPUT` failsafe (default `FS_PILOT_INPUT_DISARM`,
    3s timeout) disarms if no RC-override/pilot-input activity is received
    quickly enough after arming — a script that pauses or reads
    STATUSTEXT for a few seconds between arming and its first override
    trips it. `tools/test_target.py` (`run_c2_rc_override_test`) already
    documents this exact behavior (found live against BlueROV2, same date)
    and already handles it correctly (re-send arm every ~1s, require 2
    consecutive ARMED heartbeats, keep re-arming through the whole
    injection window) — so the real verification path was simply to run
    the actual tool, not keep hand-debugging an ad hoc script.
  - **Fixed a real, generic (not REMUS-specific) bug found along the way**:
    `attacks/acoustic_spoof.py`'s `ODOM_TOPIC` was hardcoded to
    `/model/bluerov2/odometry`, meaning the underwater acoustic-positioning
    feed (what gives ANY submerged ArduSub vehicle a valid EKF position,
    per that file's own docstring) silently only worked for BlueROV2.
    Added `constants.MODEL_NAME` (mirrors `run_sim.sh`'s own
    `world.model_name` read, defaults to the profile name — backward
    compatible, confirmed `bluerov2`'s profile resolves to the same value
    as before) and derived `ODOM_TOPIC` from it. Live-confirmed against
    REMUS-100: `acoustic_spoof.py` connects, finds `/model/remus100/`
    odometry, and the vehicle's `LOCAL_POSITION_NED` tracks real Gazebo
    ground truth continuously.
  - **`tools/test_target.py` full run, both new AUV twins — clean pass,
    verdict shape and evidence matching BlueROV2's own proven pattern
    exactly**:
    - `auv_vulnerable_remus100`: `mode_change: VULNERABLE`,
      `rc_override: VULNERABLE` (`armed_confirmed=true`,
      `peak_servo5_during_injection=1300`), detectability 1.0
      (precision/recall 1.0). Evidence:
      `target_runs/auv_vulnerable_remus100/20260808T232733/verdicts.json`.
    - `auv_resilient_remus100_hardened` (own trimmed `hardened.parm` —
      NOT the BlueROV2 DAVE file verbatim, deliberately stripped of
      BlueROV2-hardware-specific junk: joystick BTN* mapping, that unit's
      COMPASS_OFS/INS_ACC calibration offsets, camera MNT_*/SERVO8,
      RNGFND1_* rangefinder REMUS's model doesn't have — kept only what's
      load-bearing for this SDF/EKF setup plus `MAV_GCS_SYSID 77`/
      `MAV_OPTIONS 1` carried over unchanged in value): `mode_change:
      RESILIENT` (forged mode from sysid 255 refused), `rc_override:
      INCONCLUSIVE` (attacker can't even arm under `MAV_OPTIONS=1` --
      correctly INCONCLUSIVE per the tool's own `preconditions_met` gate,
      not RESILIENT). Exact verdict-shape and evidence parity with
      `auv_resilient_bluerov2_hardened`'s own result. Evidence:
      `target_runs/auv_resilient_remus100_hardened/20260808T232839/verdicts.json`.
  - Both twins' `README.md`s updated with these live-verified result
    tables (previously placeholder "PENDING LIVE VERIFICATION" rows).
    Torn down clean both times (`ps`/`ss` empty after teardown).
  - **Next**: Phase E (documentation pass — top-level `README.md`,
    `docs/ARCHITECTURE.md`'s vehicle-schema note re: `MODEL_NAME`,
    `docs/TARGET_TESTING.md`, `docs/TWIN_DEMO_GUIDE.md`,
    `docs/NEW_AUV_QUICKSTART.md`, the plain-language docx).

- 2026-08-08 (real-hull rebuild, Phase B spike): **ArduPlane-underwater
  spike — genuine, positive core result, plus one real, distinct
  complication found beyond what the plan anticipated.** Built a
  throwaway `sim_config/models/plane_spike/` (crude 48kg torpedo-shaped
  cylinder, single aft propeller, no fins) + `sim_config/plane_spike_world.sdf`
  (clone of `underwater_world.sdf`'s buoyancy setup), boot-orchestrated
  manually (gz sim + FDM relay + `arduplane --model JSON`, same FIFO-stdin
  pattern `run_sim.sh` uses) rather than touching `run_sim.sh` itself yet.
  - **B0 (build + standalone boot): PASS.** `./waf plane` builds clean.
    Standalone `arduplane --model plane` (no Gazebo) is healthy. One real
    gotcha found along the way: launching it via plain `nohup ... &`
    (stdin inherited as effectively closed) causes it to die silently
    within seconds with zero error logged — `run_sim.sh`'s own comment
    already explains why (SITL treats stdin EOF as a kill signal) and its
    FIFO-keepalive-writer trick fixes it; several confusing "random
    crashes" during this spike traced back to skipping that trick in ad
    hoc test launches, not to ArduPlane itself.
  - **B1 core question (does the EKF/arming survive underwater via the
    same Gazebo JSON-FDM path every other vehicle here uses): PASS,
    cleanly, confirmed twice independently.** 55+ continuous seconds
    armed, zero disarm events, EKF flags stable at 895 (a fully healthy
    state: attitude/velocity/position all good, dead-reckoning-fallback
    bit correctly NOT set) the entire window. No GCS/RC-failsafe race like
    ArduSub has. This is a genuinely new result — not documented anywhere
    found in research (the Blue Robotics community's own assessment was
    "no autopilot firmware currently supports this" — that claim was about
    fin/actuation support specifically, and remains true, but the
    EKF-survives-underwater question itself has a clean answer now).
  - **Same class of bug as CUSV's, caught the same way**: the first
    version of this spike model (no CG offset, same as CUSV's first
    version) sank to the seabed and tumbled with no stable orientation.
    Fixed identically (CG well below the geometric centroid) — also
    genuinely realistic for a torpedo AUV, not just a simulator workaround
    (real ones put the battery pack low for exactly this reason).
  - **A separate, real, ArduPlane-specific complication, found only after
    fixing the above**: even armed and stable, commanded throttle via
    `RC_CHANNELS_OVERRIDE` never reached the propeller — `SERVO_OUTPUT_RAW`
    stayed pinned at 1100 regardless of the override value sent. Traced to
    source: `ArduPlane/reverse_thrust.cpp`'s `get_throttle_input()` returns
    0 outright if `!rc().has_valid_input()`, and ArduPlane's own override
    (`RC_Channels_Plane::has_valid_input()`,
    `ArduPlane/RC_Channel_Plane.cpp:25`) additionally gates on RC-failsafe/
    throttle-failsafe-counter state — `RC_CHANNELS_OVERRIDE` alone,
    without genuine periodic `RC_CHANNELS` frames, doesn't satisfy this in
    MANUAL mode. This is a real architectural difference from ArduRover
    (whose throttle path has no equivalent gate — confirmed working
    identically for WAM-V and CUSV via this exact same override mechanism
    this project's whole C2 attack methodology depends on). Not yet
    investigated: whether GUIDED mode (velocity/attitude setpoints via
    MAVLink, bypassing RC entirely) or an `RC_OPTIONS`-style parameter
    sidesteps this — stopped here to report back rather than open-endedly
    continue past the point of a quick check, per the project's own
    established pattern of checking in at real decision points rather than
    silently pushing on.
  - **Follow-up (same session, user asked to investigate GUIDED mode as a
    bypass for the RC-validity gate): decisive, negative result.** GUIDED
    mode does use `does_auto_throttle()=true`, so it doesn't hit the same
    `has_valid_input()` gate MANUAL mode does -- sent a
    `SET_POSITION_TARGET_LOCAL_NED` velocity setpoint (3 m/s forward,
    bypassing RC/override entirely, arguably a more realistic C2 hijack
    surface than raw RC override anyway). Result: **ArduPilot crashed
    outright with `ERROR: Floating point exception -- aborting` (SIGFPE,
    core dumped)**, moments after "Detected physics reset" repeated in the
    SITL log. This lines up exactly with the risk flagged before this
    spike even started: GUIDED mode's auto-throttle runs through TECS
    (Total Energy Control System), which is built around true-airspeed-
    and air-density-based energy calculations -- with no real airflow
    underwater and no airspeed field in the JSON FDM message at all, some
    TECS computation almost certainly divided by (or otherwise operated
    on) a zero/undefined airspeed-derived value. This is a firmware-level
    numerical bug surfaced by operating Plane outside its designed
    envelope, not a configuration mistake -- fixing it would mean patching
    ArduPilot's own TECS source, well outside this spike's scope.
  - **Verdict: ArduPlane-underwater spike stops here.** Two real,
    independent blockers found in one session (MANUAL mode's RC-validity
    gate silently drops throttle; GUIDED mode's TECS path crashes
    outright) -- not instability or bad luck, but Plane's control loops
    genuinely not built for zero-airspeed operation, exactly as the risk
    register anticipated. The EKF/arming result (B1's actual core
    question) stands as a real, positive, novel finding worth keeping
    documented on its own merits. Proceeding to Phase C-fallback per the
    plan's pre-agreed rule: real REMUS-100 physics on the proven,
    unmodified ArduSub 6-thruster architecture, with the actuator mismatch
    disclosed prominently, not silently.
  - Torn down clean (verified via `pgrep`/`ss`, no processes/ports held --
    took two passes, two `gz sim` instances and a relay pair survived the
    first `pkill` attempt and needed direct `kill -9` by PID).
    `sim_config/models/plane_spike/` and `sim_config/plane_spike_world.sdf`
    left in place (marked THROWAWAY in their own headers) as a record of
    what was tried.

- 2026-08-08 (real-hull rebuild, Phase A): **CUSV (Textron Fleet-class,
  real active-duty Navy mine-countermeasures USV) fully built, live-
  verified, replaces WAM-V/BlueBoat as the MASS reference pair.** User
  asked for all 4 twins to be copies of specific, named, real Navy/
  research vehicles, not generic hobbyist platforms — landed on REMUS-100
  (AUV, real Navy MCM AUV + the most-cited AUV in academic hydrodynamics
  literature) and Textron Fleet-class CUSV (MASS, real active Navy MCM/ASW
  USV). This entry covers the CUSV half (Phase A of the rebuild plan);
  REMUS-100 is Phase B/C, a much bigger ArduPlane-firmware R&D spike,
  logged separately once resolved.
  - **Two real bugs found and fixed via live iteration, not caught by
    review**: (1) a symmetric buoyancy/collision box with CG at its own
    geometric centroid floats stably CAPSIZED as often as upright — no
    keel/ballast asymmetry to break the tie. Confirmed via ArduPilot's own
    live ATTITUDE report (roll=180°, not a Gazebo frame-convention
    artifact — cross-checked against the raw world-frame quaternion too,
    both agreed). Fixed by moving CG well below the box's geometric
    center, mimicking a real hull's low keel/ballast. (2) A shallow-draft
    box (~24% submerged) turned out to be a numerically sensitive edge
    case for `gz-sim-buoyancy-system`'s box-submersion approximation —
    produced a stable-but-wrong 38.5° pitch tilt even after roll was
    fixed. Fixed by shrinking the footprint and increasing height so ~55%
    of the box is submerged at equilibrium (closer to the real 7.7 m³
    displacement volume), which brought pitch down to a modest, plausible
    ~7.2° static trim — not chased to exactly 0.0° since the residual
    didn't trace to an identifiable single cause and real vessels commonly
    carry a few degrees of trim anyway.
  - **A third apparent bug turned out to be a test-methodology gap, not a
    vehicle bug**: a hand-written RC-override probe (sending
    `RC_CHANNELS_OVERRIDE` at ~2Hz via a blocking-poll loop) showed flat
    servo output on CUSV — and, when used as a control, on the
    already-known-working WAM-V too. `tools/test_target.py`'s own
    `run_c2_rc_override_test` sends the same message at ~10Hz with full
    non-blocking queue drain per cycle; re-run through the real tool, both
    CUSV and WAM-V showed correct servo movement. Lesson: don't trust an
    ad-hoc reimplementation of an already-verified attack path over the
    real one, even for a quick sanity check.
  - **Live-verified result matches WAM-V/BlueBoat's exact shape**:
    `mass_vulnerable_cusv` — mode_change/rc_override/gps_spoof all
    VULNERABLE, ais_spoof N/A, detectability 1.0 across all three attack
    families. `mass_resilient_cusv` — mode_change RESILIENT, rc_override
    INCONCLUSIVE (can't arm), gps_spoof/ais_spoof N/A. The two hardening
    mechanisms (`GPS1_TYPE=14`, `MAV_GCS_SYSID`+`MAV_OPTIONS`) carried over
    from BlueBoat's `hardened.parm` unmodified in value and produced an
    identical result on a hull ~250x heavier — confirms they're genuinely
    ArduPilot-parameter-level, not hull-specific, as the theory predicted.
  - No public CUSV propulsion data exists (Textron hasn't published engine/
    thruster count) — disclosed explicitly in `sim_config/models/cusv/
    model.sdf`'s header comment as a stated assumption (twin differential
    thrust), not silently invented. Similarly disclosed: this simulation's
    simple drag model has no planing-lift term, so it does not attempt to
    reproduce the real vehicle's 35kn top speed — tuned instead for
    stable, controllable low-speed maneuvering sufficient for the attack
    tests.
  - Full teardown confirmed clean after every boot cycle in this phase.

- 2026-08-08 (dry run): **Full pre-presentation rehearsal of
  `docs/TWIN_DEMO_GUIDE.md`, two real bugs found and fixed, all 4 twins
  re-verified.** User asked to dry-run everything before presenting. Ran the
  guide exactly as written, twin by twin -- this caught two bugs the
  previous same-day verification missed because it never exercised the CLI
  tester and the dashboard *concurrently against the same boot*:
  - **Bug 1 (real, fixed): `tools/test_target.py` hung forever against any
    vehicle_twins target booted via `run_demo.sh`.** Root cause: ArduPilot
    SITL only exposes 3 raw MAVLink TCP ports (5760/5762/5763); the
    dashboard's `detector_thread` grabs 5763 unconditionally from boot, and
    a 2nd simultaneous TCP client on the same SITL serial port never gets a
    heartbeat (confirmed empirically, not assumed). All 4
    `vehicle_twins/*/target.json` hardcoded `tcp:127.0.0.1:5763`, inherited
    from the original (pre-dashboard) `targets/*.json` design where
    test_target.py always had the port to itself. Fixed by giving
    test_target.py its own fan-out port through the existing
    `tools/mav_bridge.py` mechanism instead of a raw port: added
    `constants.MAVLINK_TEST_TARGET_PORT` (`.get()` with a computed default,
    so no existing `profile.json` needed editing), added it to
    `mav_bridge.py`'s `OUT_PORTS`, changed all 4 twins' `target.json`
    `mavlink.connection` to `udpin:127.0.0.1:14554`. Verified live: CLI test
    now runs to completion with the dashboard up, same verdicts as headless.
  - **Bug 2 (real, mitigated): AIS detectability silently reported a false
    0.0 recall under the same concurrent-boot scenario.** Root cause:
    `test_target.py`'s own AIS tap and the dashboard's `ais_thread` both
    bind UDP :10110 exclusively; the loser's bind fails, its thread died
    silently, and the run finished looking normal but reported "the
    detector caught nothing" for an attack that was never actually fed to
    it -- a wrong, presentation-damaging finding, not a crash. Confirmed via
    a same-target rerun without the conflict (recall 1.0) vs. with it
    (recall 0.0). `SO_REUSEPORT` doesn't fix this -- for unicast UDP it
    load-balances to ONE socket, it doesn't duplicate delivery, so true
    fan-out would need a relay (out of scope for a same-day fix). Landed the
    safe half instead: `_ais_tap_loop` now reports a bind failure instead of
    dying silently, `run_target_test` prints a loud `WARNING` and stamps
    `results["warnings"]` in `verdicts.json` so a bad number is never
    silently trusted again. `docs/TWIN_DEMO_GUIDE.md` updated to recommend
    running the CLI tester against a **headless** boot (`run_vehicle.sh`)
    for a fully accurate report, and to explain the dashboard-concurrent
    case is now self-diagnosing rather than silently wrong.
  - **Re-verified end to end after both fixes**: all 4 twins' CLI verdicts
    (headless) match the previously-documented table exactly; live dashboard
    click-through re-confirmed for both `mass_vulnerable_wamv` (C2 inject
    actually armed + seized the vehicle, alert fired, detected in 6.58s) and
    `mass_resilient_blueboat` (same C2 inject: mode stayed MANUAL, stayed
    disarmed, speed 0.00 -- visibly failed on the dashboard UI itself, a
    good live moment); PDF export re-confirmed (44KB, 1 page); auto-stop-on-
    disconnect re-confirmed via dashboard.log (`last client disconnected --
    stopping any active attacks`); base (non-twin) `wamv` profile re-booted
    clean to confirm the shared-file changes (`constants.py`,
    `tools/mav_bridge.py`) didn't regress the original reference vehicles.
    Full teardown confirmed (`ps`/`ss` clean) before finishing.
  - **Everything else in the previous entry below stands unchanged** -- this
    was a verification + 2-bug-fix pass on top of that work, not a redesign.

- 2026-08-08 (late): **4 self-contained vehicle_twins/ built, real
  vulnerable/resilient split, live-verified end to end.** User asked for 2
  MASS + 2 AUV real digital twins (1 vulnerable, 1 resilient each), a
  folder-based boot workflow, a single-vehicle dashboard with manual-only
  attacks and auto-stop-on-close, and PDF report export. Explicitly
  rejected placeholder verdicts -- everything below is real ArduPilot
  behavior, verified live, not asserted.
  - **Two dead ends found and abandoned before landing on what works**
    (both root-caused via ArduPilot's own C++ source in `~/ardupilot`, not
    assumed from docs): `SYSID_MYGCS` alone does nothing -- confirmed
    unused/deprecated in this ArduPilot version's own source; `EK3_GLITCH_RAD`
    /`EK3_POS_I_GATE` had zero measurable effect against an `fdm_relay`
    spoof (makes sense in hindsight: fdm_relay corrupts the same ground
    truth every sensor including IMU derives from, so there's nothing for
    innovation gating to cross-check against). Both checked in with the
    user before spending more time (AskUserQuestion) rather than silently
    building on an unverified mechanism a second time.
  - **What actually works, verified live**: (1) GPS resilience --
    `GPS1_TYPE=14` (external GPS_INPUT driver) makes GPS just another fused
    sensor instead of embedded in the shared FDM truth, so the EKF's real
    IMU cross-check catches a spoof (`gps_input` method only, not
    `fdm_relay`) -- confirmed: fused delta 0.00m while raw ingestion
    confirmed the forged value reached the wire at the full 50m offset. (2)
    C2 resilience -- `MAV_GCS_SYSID` + `MAV_OPTIONS=1` (`GCS_SYSID_ENFORCE`
    bit 0), the modern non-deprecated replacement for SYSID_MYGCS -- traced
    to `GCS_Common.cpp`'s `accept_packet()`, confirmed it fails OPEN by
    default (any sysid accepted) unless the enforce bit is set. Verified:
    attacker sysid 255 can't even arm; legitimate sysid 77 arms and
    controls normally.
  - **Combining both mechanisms on one vehicle produced a real, honest
    interaction** worth knowing about: `GCS_SYSID_ENFORCE` also blocks the
    attacker's `GPS_INPUT` traffic and arm attempts outright, so
    `gps_spoof` reads N/A (never showed ingestion) and `rc_override` reads
    INCONCLUSIVE (never confirmed armed) rather than a clean RESILIENT --
    `mode_change` alone comes back a clean RESILIENT. This is the tool's
    existing conservative-verdict design working as intended (never claim
    more than observed), not a new bug -- documented in both resilient
    twins' READMEs and `docs/TWIN_DEMO_GUIDE.md`.
  - **Code changes**: `constants.GCS_SOURCE_SYSTEM` (new, profile-driven,
    default 255) -- `tools/mav_bridge.py` and `dashboard_server.py`'s
    `goto()`/`detector_thread()` now use it (legitimate-operator paths);
    `dashboard_server.py`'s `cmd_conn()` deliberately stays at plain 255
    (it simulates the attacker -- comment updated to explain why, so it
    doesn't get "fixed" by a future reader). `tools/run_sim.sh` gained a
    per-profile `ardu_defaults` override (was hardcoded per-domain).
    `tools/run_vehicle.sh` (new) and `tools/run_demo.sh` (extended) both
    accept a `vehicle_twins/<name>` folder path directly, symlinking its
    `profile.json` into `profiles/` for discovery -- no changes needed to
    `constants.py`'s loader.
  - **Dashboard**: removed the cross-vehicle switch dropdown and
    `/cmd/vehicle` route entirely (`index.html` + `dashboard_server.py`) --
    the dashboard now only ever reflects the profile it was booted with.
    Added a connected-client counter + `disconnect` handler that calls the
    existing `stop_attacks()` when the last browser tab disconnects.
  - **New**: `/cmd/report/pdf` route renders the same report data (factored
    out into `_report_table_html()`, shared with the existing
    `/cmd/report`) to a downloadable PDF via headless Chromium (Playwright,
    already a project dependency) -- verified live (44KB valid
    `application/pdf` response).
  - **Live-verified all 4 twins** via `tools/test_target.py`, each booted
    fresh through `tools/run_vehicle.sh`: `mass_vulnerable_wamv` and
    `auv_vulnerable_bluerov2` both VULNERABLE/VULNERABLE on C2 (matching
    every reference vehicle tested so far this project); `mass_resilient_blueboat`
    and `auv_resilient_bluerov2_hardened` both RESILIENT (mode-change) /
    INCONCLUSIVE (rc-override, correctly, per above) -- reproduced 3x
    manually before landing in the twins to rule out flakiness. Also
    live-verified the dashboard changes against a booted twin: single-vehicle
    header confirmed, 0 automatic alerts, closing the tab triggered
    `[dashboard] last client disconnected -- stopping any active attacks`
    in the server log, PDF download returned a valid 44KB PDF.
  - Docs: `docs/TWIN_DEMO_GUIDE.md` (new) -- the terminal step-by-step
    handoff doc, includes the verified result table and the one real
    dashboard limitation for the resilient twins (their GPS panel needs
    `test_target.py`'s own feed to show anything, since GPS1_TYPE=14 has no
    ambient position source otherwise).
- 2026-08-08: **`docs/NEW_AUV_QUICKSTART.md` added** -- self-serve guide for
  building a new AUV digital twin (clone+retune an existing model, world,
  profile, `targets/<name>_local.json`) and running the full resilience-test
  pipeline without needing an assistant present (for live presentation
  prep). Every step was actually executed end-to-end while writing it
  (clone -> retune mass/buoyancy/inertia -> validate_vehicle PASS -> boot
  -> arm/thrust smoke test -> test_target.py -> VULNERABLE verdict ->
  generate_target_report.py -> teardown) against a real clone
  (`myauv_test`, deleted after verification, not committed) -- this caught
  two real gaps in the first draft: the thruster `<cmd_topic>` SDF entries
  also need renaming (easy to miss, silently breaks thrust if skipped), and
  a single-attempt arm check in the smoke-test script gives a false
  negative against the known ArduSub auto-disarm race (see the entry
  below) -- both fixed in the guide before handoff.
- 2026-08-08: **Underwater C2 RC-override fixed (previously INCONCLUSIVE by
  design).** Root-caused live against a fresh BlueROV2 boot with an
  empirical RC-channel sweep (all 8 channels, one at a time, watching all 8
  SERVO_OUTPUT_RAW channels): chan3 (RCMAP_THROTTLE) already correctly
  drove ArduSub's vertical thrust -- this project's own WO-19 finding
  (+8.25m true depth) proves the SEND side was never broken -- but the
  check was reading back `servo3` for verification, and ArduSub's vectored
  frame actually outputs vertical thrust on servo5/servo6, not servo3.
  `run_c2_rc_override_test` (`tools/test_target.py`) now watches servo5 for
  underwater targets, keeping servo3 for surface/Rover. Along the way, also
  found and fixed a second, independent bug: ArduSub can arm then
  auto-disarm again within ~1s (a GCS/RC-failsafe race, reproduced with
  nothing but repeated arm commands and no override at all) -- the check
  now requires 2 consecutive armed heartbeats before spending its
  measurement window, keeps re-arming throughout that window, and fully
  drains the message queue each loop iteration (a single-message-per-tick
  drain was starving the rarer 1Hz HEARTBEAT out against the busier 10Hz
  SERVO_OUTPUT_RAW stream, producing a false INCONCLUSIVE despite the servo
  visibly moving). Verified live: 3 consecutive clean `VULNERABLE` verdicts
  against bluerov2_local, no regression against wamv_local (still
  VULNERABLE as before). `bluerov2_local`'s deployment verdict is now a
  fully-substantiated "NOT READY TO DEPLOY" (2 vulnerable findings, 0
  inconclusive) instead of the old 1-vulnerable-1-inconclusive hedge.
  `docs/TARGET_TESTING.md`'s "Known limitations" updated to match --
  now documents the ArduSub auto-disarm race (mitigated, not eliminated;
  an unusually flaky target can still cost one INCONCLUSIVE run) instead of
  the old "channel mapping unvalidated" gap.
- 2026-08-07 (night): **Resilience-tester pivot Phases 1-4 COMPLETE + docs
  landed (Phase 5).** The vehicle-agnostic testing tool described in the PIVOT
  entry below is now fully built and evidenced. Summary for a fresh session:
  read `docs/TARGET_TESTING.md` first (front door, mirrors DESIGNER_GUIDE.md).
  - Phase 1 (commit 564caf5): `targets/loader.py`, `tools/validate_target.py`,
    `tools/test_target.py` skeleton + C2 mode-change check. Proved
    vehicle-agnosticism against 3 independent ArduPilot instances. Root-caused
    + fixed the C2 RC-override bug along the way (source_system 250 vs 255,
    ArduPilot's SYSID_MYGCS default) -- commit adae412, fixed in both the
    dashboard and the new loader's default.
  - Phase 2 (commit cd10161): AIS spoof wiring (vulnerability structurally
    N/A on bare ArduPilot, detectability fully tested) + live `DetectorSuite`
    tap threaded through every attack window + `score_detectors.py` made
    target-scoped via an additive `gt_dir` param (zero behavior change for
    existing callers).
  - Phase 3 (commit 2e53253): `attacks/gps_input_inject.py` (standard MAVLink
    `GPS_INPUT`, autopilot-agnostic) + the raw-vs-fused GPS verdict logic
    (`GPS_RAW_INT` confirms ingestion, `GLOBAL_POSITION_INT` confirms whether
    fusion trusted it -- this split is what lets the tool distinguish "EKF
    rejected it" from "injection never landed"). Preceded by an analysis
    (recorded in the plan file) confirming Gazebo has no better free/open
    hydrodynamics option, but ArduPilot's proprietary FDM protocol didn't need
    to stay load-bearing -- `GPS_INPUT` is the protocol-standard equivalent,
    also valid for PX4 and real hardware later.
  - Phase 4 (commit 7120660): `tools/generate_target_report.py` (recommendation
    text per VULNERABLE finding, detectability-gap notes, synthesized
    deployment-readiness verdict per target) + `targets/blueboat_local.json` +
    `targets/bluerov2_local.json`, all 3 reference vehicles live-tested through
    the exact same code path as external targets. Caught and fixed a real gap
    while running BlueROV2: the RC-override check's channel/servo assumptions
    are Rover-specific and don't hold for ArduSub's thruster layout (override
    registered in `RC_CHANNELS` but the watched servo never moved) -- gated
    `domain == "underwater"` to always return INCONCLUSIVE for that sub-check
    rather than let a false RESILIENT stand. `target_runs/resilience_report.html`
    now covers 6 targets (3 reference vehicles + 3 external/throwaway SITL
    instances proving genericity), all 4 verdict outcomes represented.
  - Phase 5 (this entry + commit after it): `docs/TARGET_TESTING.md` written.
  - Known, documented limitations (not fixed, by design -- see
    `docs/TARGET_TESTING.md`'s "Known limitations" section): `fdm_relay`
    GPS-spoof pollutes the shared `attack_logs/gps_spoof_ground_truth.csv`
    (relay is a separate already-running process, trimmed back twice this
    session); C2 RC-override underwater gate is a documented scope limit, not
    a bug fix, pending a real ArduSub-aware channel mapping.
  - Remaining/optional, not required for the internship deliverable: the
    plan's 2-day buffer (unused), real-hardware support, a "legitimate
    GPS_INPUT bridge" for testing gps_input against a real-physics reference
    vehicle simultaneously, fixing the ArduSub channel-mapping gap itself.
  - Full rationale/design history: `~/.claude/plans/crystalline-frolicking-thompson.md`.
- 2026-08-07 (evening): **PIVOT** -- the project's primary deliverable is now
  a vehicle-agnostic resilience-testing TOOL (point it at any ArduPilot
  vehicle, ours or someone else's, and get a vulnerability/detectability
  report), not the fixed 3-vehicle demo. The old "PROJECT COMPLETE" status
  below is against the OLD scope; this is new, additive work, see
  `targets/`, `tools/test_target.py`, `tools/validate_target.py`. Phase 0+1
  done and verified live against 3 independent ArduPilot instances
  (commit 564caf5). Along the way, root-caused and fixed the C2 RC-override
  bug noted just below (commit adae412). Full plan at
  `~/.claude/plans/crystalline-frolicking-thompson.md`. Phases 2-5 (AIS +
  detectability, GPS_INPUT injection, unified report, docs) remain.
- 2026-08-07: Dashboard upgrade -- /cmd/report now renders the same rich
  precision/recall/FP-rate/latency + overhead tables as generate_report.py
  (reused its render_family_table/render_overhead_panel) instead of a raw CLI
  text dump. Added live instrumentation to the dashboard's OWN in-process
  detector loop (separate from detection/run_detectors.py): a "Live detection
  metrics" card streams CPU%/peak RSS/events-per-sec/avg-proc-time every 5s via
  a new `overhead_update` socket event, and a badge pops up with measured
  detect-latency (launch-click -> first matching alert) via `attack_latency`.
  Also made the layout responsive (stacks on screens <900px) and gave report
  tables their own horizontal scroll instead of overflowing the page. Verified
  the backend logic (tap()/latency/overhead snapshot) via a standalone import
  smoke test (no live sim needed) and the frontend visually via the browser
  preview (KPI card, latency badges, report overlay, mobile stacking).
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
