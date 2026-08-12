# Project Context — read this first

This is the single, current-state reference for the whole project. If you
are a new session (human or AI) picking this up cold, read this file
top-to-bottom before touching anything — it is written to make you
"pitch-perfect" on what exists, why, and what's actually verified vs. still
open, without having to reconstruct it from git history or a dozen docs.

Other docs go deeper on specific topics (see the map at the bottom); this
one is the map itself plus enough substance to act on immediately.

**Last verified accurate: 2026-08-12.** If anything here conflicts with the
live code or with `docs/EXECUTION_STATE.md`'s dated running log, trust the
code and the log — this file can drift, they can't (EXECUTION_STATE.md is
updated after every meaningful change; if you make a change, update it and
consider whether this file needs a matching touch-up).

---

## 1. What this project is, and why

**One sentence**: a simulation-based cyber range that builds an exact
digital twin of the autopilot software driving an uncrewed maritime
vehicle (surface or underwater), then runs realistic attacks against it —
GPS spoofing, AIS spoofing, command-and-control (C2) hijack — and reports
whether the vehicle was fooled and whether a blind monitor would have
caught it.

**Origin**: this is a Phase I prototype for an Indian Navy / iDEX-adjacent
internship brief (the founding proposal is `docs/CYBER RANGE.docx`).
Autonomous maritime systems (Unmanned Surface Vehicles / Maritime
Autonomous Surface Ships, and underwater equivalents) are being adopted
faster than their cybersecurity is being tested. GPS, AIS, and C2 links
were designed with essentially no authentication. The brief asked for a
safe, reproducible, software-only environment to demonstrate and measure
that gap — explicitly scoped to simulation only (no physical hardware, no
classified data), as a foundation for a later, funded hardware-in-the-loop
range.

**What actually got built goes further than the original brief in one
important way**: the brief described a fixed demo (one simulated vessel,
three attacks, a dashboard). What exists now is that *plus* a
vehicle-agnostic **testing tool** (`tools/test_target.py`) that can point
the same three attacks at *any* ArduPilot-based vehicle — not just the
ones this repo boots itself — and produce a vulnerability/detectability
report with a synthesized deployment-readiness verdict. That tool, not the
dashboard, is this project's primary deliverable today. See §3 for how
that shift happened.

## 2. The one-paragraph architecture

Real autopilot firmware (**ArduPilot**, in **SITL** — Software In The Loop
— mode: the exact same flight-control code that runs on real hardware,
with its sensors/motors replaced by a live network link instead of real
hardware) is connected to a real physics engine (**Gazebo**), so the
vehicle's simulated hull moves under genuine hydrodynamics, not a scripted
animation. Attack scripts sit in the sensor/command path and forge GPS
position, AIS radio broadcasts, or MAVLink (the drone/boat-industry command
protocol) commands. A rule-based detection layer watches only the same
live telemetry a real operator would see — never the attacks' own private
ground-truth logs — so its precision/recall numbers mean something. A
Flask+Socket.IO web dashboard visualizes all of this live; a separate CLI
tool (`tools/test_target.py`) runs the same attacks headlessly against any
target and produces a written verdict. Full component/port detail:
`docs/ARCHITECTURE.md`.

## 3. How the project got here — the three-phase history, condensed

*(Full blow-by-blow, dated, with evidence file paths: `docs/EXECUTION_STATE.md`.
Full original work-order plan: `docs/ROADMAP.md`, now historical.)*

**Phase 1 — Dual-domain demo (through 2026-07-30).** Built the original
scope: one surface vehicle (WAM-V, via the VRX simulator), then generalized
to a second surface vehicle (BlueBoat) and one underwater vehicle
(BlueROV2, via ArduSub), all three running the same GPS/AIS/C2 attacks
(AIS and surface-GPS are N/A while an AUV is submerged, correctly, by
physics), a rule-based detection layer, and a live dashboard. Reached
"PROJECT COMPLETE against stated scope" — 6 regression checkpoints, all
passing, both domains.

**Phase 2 — Pivot to a vehicle-agnostic resilience-testing tool
(2026-08-07).** Realized the fixed 3-vehicle demo, while complete, wasn't
the most valuable deliverable — a *tool* that could test *any* ArduPilot
vehicle (someone else's SITL, not just this repo's own models) was. Built
`targets/*.json` (a connection-only config schema, no SDF/world file
needed), `tools/test_target.py` (the orchestrator: baseline, attack,
detect, verdict), `attacks/gps_input_inject.py` (a protocol-standard,
vehicle-agnostic GPS attack alongside the existing physics-layer one), and
`tools/generate_target_report.py` (cross-target HTML report with
per-finding recommendations and a synthesized deployment-readiness
verdict). Verdicts are one of **four** outcomes, not a binary pass/fail —
see §7. Proved genericity against independently-launched SITL instances
this repo never built.

**Phase 3 — Real, named hardware; twins replace generic reference vehicles
(2026-08-08).** The three original vehicles (WAM-V, BlueBoat, BlueROV2)
were generic hobbyist/research hulls, not vehicles a Navy reviewer would
recognize. Rebuilt the vehicle set as two real, individually-named,
distinct pieces of Navy/research hardware — the Textron **Fleet-class
CUSV** (surface) and the **REMUS-100** (underwater) — each as a
**self-contained `vehicle_twins/<name>/` folder** with a
vulnerable/resilient pair. The original three reference vehicles were
retired from the primary demo set but not deleted (still boot directly via
`profiles/{wamv,blueboat,bluerov2}.json`; still used as the teaching/clone
base in `docs/DESIGNER_GUIDE.md` and `docs/NEW_AUV_QUICKSTART.md`). This is
the vehicle set in active use today.

**Since then**: continuous live-verification passes, dashboard bug fixes
(most of them found by actually clicking through the live UI, not assumed
from a prior CLI-only pass — see §8 for the pattern of bugs this caught),
and the doc/repo cleanup this file is part of (2026-08-12).

## 4. What exists today, component by component

| Directory | What's in it |
|---|---|
| `vehicle_twins/` | **The 4 primary, ready-to-run digital twins** (§6). Each folder is self-contained: `profile.json` (+ `hardened.parm` for resilient ones), `target.json`, `README.md` with its own verified results. |
| `profiles/` | Legacy generic reference vehicles (`wamv`, `blueboat`, `bluerov2`) — retired as the primary demo set, still fully functional, still the teaching/clone base for new vehicles. |
| `sim_config/` | Gazebo SDF models (`models/{cusv,remus100,blueboat,bluerov2,ground_station,plane_spike}/`) + world files + install/build/start shell scripts. `models/plane_spike/` is a leftover research spike (see §9). |
| `attacks/` | `gps_spoof.py` (physics-layer FDM relay, surface), `gps_input_inject.py` (protocol-standard `GPS_INPUT` injection, any vehicle), `ais_spoof.py` (ghost + impersonation), `ais_listener.py`, `c2_replay.py` (mode-change forgery + RC-override), `acoustic_spoof.py` (underwater position **and** legitimate-position/yaw feed — see §8's yaw-fix entry), `auto_mission.py` (early AUTO-mode demo script). |
| `detection/` | `detectors.py` (blind rule-based `DetectorSuite` — GPS-jump, AIS-duplicate-MMSI, C2 RC-override), `run_detectors.py` (standalone live tap + CPU/RSS self-sampling). |
| `nodes/` | `ais_emulator/ais_emulator.py` (broadcasts the *real* vessel's AIS), `monitor/src/dashboard_server.py` (the Flask+SocketIO operator console — the biggest single file in the project; see §5), `monitor/src/templates/index.html`. |
| `tools/` | Orchestration layer — see §5's table. |
| `targets/` | Connection-only configs for `test_target.py` against anything (this repo's own vehicles or external). `loader.py` validates + refuses to run without `authorized: true`. |
| `target_runs/` | Per-run verdicts/evidence from `test_target.py`, one timestamped folder per run. |
| `attack_logs/` | Ground-truth CSVs each attack module writes about itself — **private**, never read by any detector, only by offline scoring. |
| `evidence/` | Screenshots/video/logs from Phase 1's checkpoint regressions — historical. |
| `deploy/` | Docker packaging (`Dockerfile`, `entrypoint.sh`) + `launch.sh` (host-side launcher). |
| `ros2_ws/src/vrx/` | Vendored VRX (WAM-V) simulator, a git submodule — only needed for the legacy `wamv` profile's VRX boot path. |
| `docs/` | Everything else written down — see the map at the bottom. |
| `constants.py` | The profile loader every script imports — see `docs/ARCHITECTURE.md`. |

## 5. The tools layer, precisely

| Tool | What it does | You'd run it... |
|---|---|---|
| `tools/run_sim.sh <profile> up\|down\|status` | Boots one domain's full stack (Gazebo → FDM relay → ArduPilot SITL → MAVLink bridge → AIS emulator if surface) with real health checks. The actual boot engine everything else calls into. | Directly for a legacy `profiles/*.json` vehicle. |
| `tools/run_vehicle.sh vehicle_twins/<name> up\|down\|status` | Symlinks a twin's `profile.json` into `profiles/`, then calls `run_sim.sh`. Headless. | Before running `test_target.py` against a twin. |
| `tools/run_demo.sh <profile-or-twin-path> up\|down\|status` | Same boot, plus starts `dashboard_server.py`. | For the live browser demo. |
| `tools/test_target.py --target <path>` | Connects, baselines, runs the target's enabled attacks, taps `DetectorSuite` live, writes `target_runs/<name>/<ts>/{verdicts.json,alerts.jsonl,*_ground_truth.csv}`. | The core resilience-test deliverable, headless. |
| `tools/generate_target_report.py` | Compiles every target's latest run into `target_runs/resilience_report.html` — vulnerability + detectability tables, per-finding recommendations, deployment-readiness verdict. | After one or more `test_target.py` runs. |
| `tools/validate_target.py <name>` | Pre-flight contract check on a `targets/*.json` (or a twin's `target.json`) — no live connection needed. | Before ever running `test_target.py` on a new target. |
| `tools/validate_vehicle.py <name>` | Pre-flight contract check on a `profiles/*.json` + its SDF (plugin present, ports match, sensors present). | Before booting a new/edited vehicle. |
| `tools/run_attack_suite.py --profile <name>` | The *legacy* attack runner (profile-based, not target-based) — PASS/FAIL/SKIP/N-A per attack, verified against true Gazebo pose. | Automated regression on a `profiles/*.json` vehicle without the dashboard. |
| `tools/score_detectors.py` | Offline: replays a detector alert log against `attack_logs/*.csv` ground truth → precision/recall/FP-rate/latency. | After `run_detectors.py` + some attacks. |
| `tools/generate_report.py` | Compiles scoring + overhead into `evidence/evaluation_report.html` (the *legacy* profile-based report — parallel to, not the same as, `generate_target_report.py`). | Legacy-path evaluation. |
| `tools/mav_bridge.py` | Standalone MAVLink fan-out (replaces MAVProxy's `output add` — MAVProxy needs a tty, this doesn't). Ports come from the active profile. | Started automatically by `run_sim.sh`. |
| `tools/view_3d.sh` | Attaches the Gazebo 3D GUI (needs a real GPU desktop). | Optional, for a visually immersive demo moment. |
| `tools/capture_demo.py` | Scripted screenshot capture for the `evidence/demo_captures/` set. | Historical, Phase 1. |

`nodes/monitor/src/dashboard_server.py` itself is the browser operator
console: click a destination to navigate, click an attack button, watch
true-vs-believed position diverge, watch live detector alerts, click
**Report** for an on-the-spot PDF. It has its own background threads —
`legit_gps_feeder`/`legit_vision_feeder` (keep resilient twins' position
source alive continuously, §8), `detector_thread` (the dashboard's own
live tap, separate from `detection/run_detectors.py`), `overhead_emitter`
(CPU/RSS/latency telemetry to the UI), `believed_thread`/`gz_pose_thread`
(true vs. believed position polling).

## 6. The 4 vehicle twins — what they are, and their verified results

All four are copies of **real, individually-named, currently-active
Navy/research hardware**, not generic placeholders — hull mass, dimensions,
and hydrodynamics are sourced and cited in each twin's own `README.md` and
`model.sdf` header.

| Twin | Real hardware | Config |
|---|---|---|
| `mass_vulnerable_cusv` | Textron Fleet-class CUSV (US Navy mine-countermeasures/ASW USV) | Out-of-the-box, no hardening |
| `mass_resilient_cusv` | Same CUSV hull | `GPS1_TYPE=14` + `MAV_GCS_SYSID`/`MAV_OPTIONS=1` hardened |
| `auv_vulnerable_remus100` | REMUS-100 (US Navy shallow-water mine-countermeasures AUV; the most-cited AUV in academic hydrodynamics literature) | Out-of-the-box, no hardening |
| `auv_resilient_remus100_hardened` | Same REMUS-100 hull | `MAV_GCS_SYSID`/`MAV_OPTIONS=1` hardened (GPS N/A underwater — real physics) |

**Disclosed simplification (REMUS-100 only)**: the real REMUS-100 is
fin-steered (one propeller + rudder/stern-plane control surfaces). No
ArduPilot firmware supports that scheme for an underwater vehicle
(confirmed against ArduPilot's own source and an open GitHub issue
requesting exactly this, unimplemented). A genuine attempt was made via
ArduPlane firmware (EKF/arming survived underwater — a real result — but
the throttle path hit a firmware-level dead end). This twin uses a
6-thruster vectored frame instead — the same proven architecture BlueROV2
already used — with real hull mass/buoyancy/drag, disclosed simplified
actuation. Full trail: `vehicle_twins/auv_vulnerable_remus100/README.md`.

**Verified live results** (most recent full pass; re-verify before quoting
in a live demo — re-running is cheap and this project's own convention):

| Twin | Mode-change | RC-override | GPS spoof | AIS spoof | Deployment verdict |
|---|---|---|---|---|---|
| `mass_vulnerable_cusv` | VULNERABLE | VULNERABLE | VULNERABLE | N/A | **NOT READY TO DEPLOY** |
| `mass_resilient_cusv` | RESILIENT | INCONCLUSIVE | N/A | N/A | **CONDITIONALLY READY** |
| `auv_vulnerable_remus100` | VULNERABLE | VULNERABLE | N/A (real physics) | N/A | **NOT READY TO DEPLOY** |
| `auv_resilient_remus100_hardened` | RESILIENT | INCONCLUSIVE | N/A (real physics) | N/A | **CONDITIONALLY READY** |

The resilient twins' RC-override reads INCONCLUSIVE, not a clean
RESILIENT, because the attacker can't even **arm** the hardened vehicle —
the tool's own conservative-verdict rule (never claim more than observed:
"can't arm" and "armed but ignored" are different findings, not the same
bucket). This is arguably *stronger* evidence than a clean RESILIENT, but
reported honestly rather than assumed. Full per-twin evidence and
methodology: each twin's own `README.md`, `docs/TARGET_TESTING.md`.

**Quick start** (any twin):
```bash
tools/run_vehicle.sh vehicle_twins/mass_vulnerable_cusv up
python3 tools/test_target.py --target vehicle_twins/mass_vulnerable_cusv/target.json
tools/run_vehicle.sh vehicle_twins/mass_vulnerable_cusv down
```
Or `tools/run_demo.sh vehicle_twins/mass_vulnerable_cusv up` +
`http://localhost:8080` for the live dashboard. Full walkthrough, all 4
twins, reading the results: `docs/TWIN_DEMO_GUIDE.md`.

## 7. How a verdict is reasoned about (the four outcomes)

Binary vulnerable/resilient is wrong for a testing tool — "nothing moved"
is ambiguous between "it resisted" and "it never even ingested the
attack," and conflating those in front of a reviewer is a credibility
problem. Every attack sub-check returns one of:

- **VULNERABLE** — the target accepted the forged input and its own
  reported state changed accordingly.
- **RESILIENT** — the attack was confirmed delivered/ingested, but the
  target's fused state didn't materially move.
- **N/A** — structurally inapplicable (AIS on any bare ArduPilot vehicle;
  GPS on a submerged AUV; RC-override when actuation testing wasn't
  opted into).
- **INCONCLUSIVE** — can't be determined safely — preconditions weren't
  met (e.g. never confirmed armed), or the target stopped heartbeating
  entirely after injection (could indicate a crash/DoS — a separate,
  more interesting finding than "resilient").

Full methodology per attack family: `docs/TARGET_TESTING.md`.

## 8. Known issues and limitations — current, honest state

**Open, not fixed:**
- **AUV waypoint-tracking bug (both REMUS-100 twins).** Clicking a
  destination arms the vehicle and enters AUTO correctly, but the vehicle
  does not reliably navigate there — oscillates at long range, actively
  diverges at short range. Root-caused in two layers:
  1. **Fixed 2026-08-10**: `legit_vision_feeder`/`acoustic_spoof.py`'s
     `read_true_ned()` was hardcoding the vehicle's YAW to 0 in the
     `VISION_POSITION_ESTIMATE` feed. Both REMUS-100 twins use that same
     feed as their yaw source (`EK3_SRC1_YAW=6`), so this was silently
     telling the EKF "always facing north," corrupting heading the moment
     the vehicle turned. Confirmed live (ArduPilot's believed heading ~0
     rad while Gazebo's true heading was ~1.78 rad at the same instant) and
     fixed — the feed now sends real yaw, computed from Gazebo's true
     orientation quaternion (ENU→NED conversion).
  2. **Not fixed, still open**: with a *correct* heading fed from the
     start, both twins now hold position and report "arrived" immediately
     on a fresh AUTO mission instead of driving there at all — worse for a
     demo than before (at least the old behavior moved part-way). Ruled
     out a mission-upload bug (`MISSION_ITEM_INT` readback confirms the
     correct destination was stored and targeted) and a race (reproduced
     deterministically 3/3 times). Best current hypothesis: an
     earth-frame-to-body-frame rotation issue in how ArduSub's position
     controller output reaches REMUS-100's 6-thruster vectored mixer once
     heading is genuinely non-zero — a motor-mixing/control-loop level fix,
     not a config or feeder change, and not something to blind-patch
     without the normal iterate-and-test cycle this project's other
     control-loop tuning has always used.
  - **What's unaffected**: arming, mode-change, RC-override, and the full
    `test_target.py` verdict suite — none of that depends on AUTO waypoint
    tracking. **Recommendation**: use the CUSV twins for any live
    click-to-navigate demo; use either AUV twin for the C2 attack buttons
    and the CLI report.
  - Full diagnosis with live numbers: `docs/EXECUTION_STATE.md`'s
    2026-08-09 and 2026-08-10 entries.
- **The original PSC_POSXY_P/PSC_VELXY_* "untuned gains" theory
  (documented 2026-08-09) was wrong** and is superseded by the above —
  those are pre-4.x ArduPilot parameter names that don't exist in the
  current firmware build and silently no-op; both twins have always run
  ArduSub's plain default position-controller gains, not "copied BlueROV2
  gains." Don't retune those parameter names; they don't do anything.
- **`fdm_relay`-method GPS spoofing pollutes the shared
  `attack_logs/gps_spoof_ground_truth.csv`** — it's a separate,
  already-running process with its own ground-truth logging outside
  `test_target.py`'s control. Only affects that one shared CSV; target-run
  evidence under `target_runs/` stays correctly isolated. Trim the CSV
  periodically if it grows large from repeated `fdm_relay` runs.
- **ArduSub can auto-disarm within ~1s of arming** (a GCS/RC-failsafe
  race, reproduced independently of any attack). The C2 RC-override check
  mitigates this (requires 2 consecutive armed heartbeats, keeps
  re-arming through its measurement window) but an unusually flaky target
  can still cost one run an INCONCLUSIVE — re-run, don't treat as a bug.
- **`wamv` (VRX) does not boot headless in the Docker deploy path** — the
  VRX world stalls during load in the containerized Gazebo server. Native
  boot works fine; this is a container-specific gap. The current primary
  twins (non-VRX Gazebo boot path) are believed compatible with Docker but
  **not yet explicitly verified there** — see `docs/DEPLOY.md`.
- **`sim_config/models/plane_spike/`** is a leftover research artifact
  from the ArduPlane-underwater investigation during the REMUS-100 build
  (see Phase 3 in §3) — a dummy capsule hull used to test whether
  ArduPlane could survive underwater at all before the 6-thruster fallback
  was chosen. Not part of any current twin; harmless to leave, safe to
  delete if you want it gone (`docs/EXECUTION_STATE.md`'s 2026-08-08
  "Phase B spike" entry has the full investigation if you want the
  reasoning before removing it).

**Fixed this session (2026-08-09/10), for context on what "known good" now
means:**
- Unthrottled true-position socket emits (was ~112/s, now ~13.6/s).
- `c2_replay`'s `rc_stop` PWM used the wrong assumption about this CUSV
  twin's symmetric-around-trim throttle curve.
- Both resilient twins had no ambient GPS/vision position source at all
  outside an active attack — `legit_gps_feeder`/`legit_vision_feeder`
  fixed this (§5).
- `goto()`'s arm-retry window was 6 attempts (~6s) — too short for a
  freshly-appeared external position fix to earn the EKF's trust; extended
  to 90 attempts (~90s), self-terminating once armed.

## 9. Repository housekeeping notes (2026-08-12 pass)

This file's creation was paired with a repo-wide doc audit. What changed,
for anyone wondering where something went:

- **Deleted** (superseded, all recoverable via git history):
  `docs/DEMO_GUIDE.md` (legacy profile-based presentation script,
  superseded by `docs/TWIN_DEMO_GUIDE.md`), `docs/
  Maritime_Cyber_Range_Progress_Report.docx` (a stale point-in-time
  snapshot from before even the accel-sign arming fix landed, fully
  superseded by `docs/EXECUTION_STATE.md`), three throwaway target
  configs (`targets/{gps_test_converged,gps_test_fresh,standalone_test}.json`
  and their `target_runs/` evidence — one-off verification artifacts from
  early Phase 2 whose job was already done and documented), and an
  untracked leftover `target_runs/mass_vulnerable_wamv/` run.
- **Updated**: `docs/ARCHITECTURE.md` (was surface-only/WAM-V-only and
  described a since-fixed bug as current; now covers both domains, the
  full current port map, and the profile/twin/target three-layer config
  system), `docs/ROADMAP.md` (marked historical — its scope is 100% done
  and it predates both later pivots), `docs/TWIN_DEMO_GUIDE.md` + both
  REMUS-100 twins' READMEs (added the §8 navigation-bug disclosure where a
  reader would actually hit it), `docs/Maritime_Cyber_Range_Plain_Language_Guide.docx`
  (referenced the retired wamv/blueboat/bluerov2 twin names — rewritten to
  the current CUSV/REMUS-100 set, plus the same navigation caveat added to
  its troubleshooting table).
- **Moved**: `CYBER RANGE.docx` (the founding brief) from the repo root
  into `docs/` for organization.
- **This file** (`docs/PROJECT_CONTEXT.md`) is new.

## 10. Full documentation map

| Doc | Read it for |
|---|---|
| **This file** | Everything, current state, start here. |
| `docs/TWIN_DEMO_GUIDE.md` | Step-by-step: boot a twin, attack it, read the verdict, tear down. |
| `docs/TARGET_TESTING.md` | `tools/test_target.py` deep-dive — schema, verdict methodology, onboarding an external target. |
| `docs/ARCHITECTURE.md` | Component map, full port table, the profile/twin/target config layers. |
| `docs/VEHICLE_TWIN_CONTRACT.md` | Package your own vehicle as a `vehicle_twins/<name>/` folder. |
| `docs/NEW_AUV_QUICKSTART.md` | Full worked example: clone-and-retune BlueROV2 into a genuinely new AUV. |
| `docs/DESIGNER_GUIDE.md` | The underlying generic `profiles/*.json` mechanism, detection/scoring internals. |
| `docs/DEPLOY.md` | Docker packaging (`./launch.sh`) — no native install needed. |
| `docs/EXECUTION_STATE.md` | Dated, blow-by-blow build log — every bug found, every fix, every live-verification run, in chronological order. The primary-source record this file is a synthesis of. |
| `docs/ROADMAP.md` | Historical — the original WO-08..WO-27 work-order plan, 100% complete, predates the two later pivots. |
| `docs/CYBER RANGE.docx` | The original founding project brief/proposal. |
| `docs/Maritime_Cyber_Range_Plain_Language_Guide.docx` | The same material as `TWIN_DEMO_GUIDE.md`, written for a reader with zero technical background. |
| `README.md` | Top-level entry point, first-time setup, quick start. |
