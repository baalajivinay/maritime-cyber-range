# Maritime Cyber Range — Project Overview

**The single, current-state reference for the whole project.** Read this
top-to-bottom to understand what exists, why, and what is actually verified.
For *how to run everything*, see the companion doc
[`RUNNING.md`](RUNNING.md). For the dated, blow-by-blow engineering history,
see [`EXECUTION_STATE.md`](EXECUTION_STATE.md). For how much to trust a result
(twin-vs-real fidelity + attack-class validation), see
[`VALIDATION.md`](VALIDATION.md).

*Last verified live: 2026-10-22 (Indian twins + Stonefish/Godot engines).*

---

## 1. What this is, and why

A **simulation-based cyber range** that builds a digital twin of the autopilot
software driving an uncrewed maritime vehicle — surface (USV) or underwater
(AUV) — then runs realistic attacks against it (GPS spoofing, AIS spoofing,
command-and-control hijack, acoustic-positioning spoofing) and reports two
things per attack: **was the vehicle fooled**, and **would a blind monitor have
caught it**.

**Origin.** A Phase-I prototype for an Indian Navy / iDEX-adjacent brief (the
founding proposal is `docs/reference/CYBER RANGE.docx`). Autonomous maritime
systems are being adopted faster than their cyber-security is being tested;
GPS, AIS, and C2 links were designed with essentially no authentication. The
brief asked for a safe, reproducible, **software-only** environment to
demonstrate and measure that gap — a foundation for a later, funded
hardware-in-the-loop range.

**What was built goes beyond the brief in three ways:**
1. A **vehicle-agnostic resilience tester** (`tools/test_target.py`) that
   points the same attacks at *any* ArduPilot/ArduSub vehicle, not just the
   twins this repo ships — producing a four-outcome verdict per attack. This
   tool, not any renderer, is the primary deliverable.
2. **Four digital twins of real, named Indian platforms** (§5) rather than
   generic reference hulls — two Indian AUVs and two Indian USVs.
3. A **geographically-grounded, physics-accurate multi-site framework** (§3):
   the range relocates to real Indian naval waters (Kochi, Mumbai,
   Visakhapatnam), each reproducing that water body's cited oceanography
   (density, ocean current, sound-speed profile) so a twin behaves the way
   real hardware would behave *there*.

## 2. One-paragraph architecture

Real autopilot firmware (**ArduPilot/ArduSub**, in **SITL** — the same
flight-control code that runs on real hardware, with sensors/motors replaced by
a live network link) is coupled to a physics engine so the simulated hull moves
under genuine hydrodynamics, not a scripted animation. The range now runs on
**three interchangeable engines** (§2a): **Gazebo** (the default backing the
twins and `test_target`), **Stonefish** (higher-fidelity underwater physics,
tuned for the AUV-150), and **Godot** (a game-quality 3D operator console).
Attack scripts sit in the sensor/command path and forge GPS position (a
Flight-Dynamics-Model relay), AIS radio broadcasts (AIVDM NMEA), MAVLink
commands, or acoustic-positioning fixes. A rule-based detection layer watches
only the same live telemetry a real operator sees — never the attacks' private
ground-truth logs — so its alert counts mean something. A headless CLI
(`tools/test_target.py`) produces written verdicts. Full component/port detail:
§4–§6.

### 2a. The three engines

The physics/rendering layer is now pluggable. A twin's *security verdict* is
identical on any engine (it depends on the firmware/protocol/EKF, not the
hull); the engines differ in physical fidelity and visuals.

| Engine | Role | Where |
|---|---|---|
| **Gazebo Harmonic** | The default. Backs all four twins and every `test_target` verdict run; driven via the ArduPilotPlugin FDM JSON relay. Site density/current/sound-speed are patched into its world. | `sim_config/`, `tools/run_sim.sh` |
| **Stonefish** | High-fidelity underwater engine (realistic 6-DOF hydrodynamics + caustics + sonar/DVL), bridged to ArduSub over the same JSON FDM protocol. Tuned scenario for the **AUV-150** (`stonefish/auv150.scn`): flies straight at ~1.8 m/s cruise with stable depth/heading hold. | `stonefish/`, `tools/stonefish_bridge.sh` |
| **Godot 4** | Game-quality 3D first-person operator console — one window, pick site + vehicle, watch it move, set a destination, launch attacks. **This is the default front-end** (`tools/app.sh`); it auto-routes each vehicle to its best engine (AUV-150 → headless Stonefish, the rest → Gazebo + real-data models). | `godot_app/`, `tools/godot_app.sh`, `tools/godot_relay.py` |

Also shipped: the **Flask + Socket.IO + Leaflet browser dashboard**
(`nodes/monitor/`, the original operator console at `:8080`) and a **legacy
pygame console** (`nodes/app/mcr_app.py`, `tools/app.sh pygame` — a GPU-shader-
free fallback).

## 3. The multi-site framework (scale-up)

The range runs at a selected real water body. **Kochi is the default.** Each
site is a cited JSON dataset under `scaleup/sites/data/` turned into live
physics by `scaleup/sites/`:

| Site | Position | Water body | Density ρ | Surface sound speed | Mean current |
|---|---|---|---|---|---|
| **Kochi (NPOL)** | 9.90 N, 76.20 E | Arabian Sea shelf | 1022.4 kg/m³ | 1542.4 m/s | 0.35 m/s @ 160° |
| **Mumbai** | 18.92 N, 72.80 E | Arabian Sea harbour approaches | 1022.9 kg/m³ | 1540.6 m/s | 0.60 m/s @ 020° |
| **Visakhapatnam** | 17.68 N, 83.33 E | Bay of Bengal shelf (fresher → lighter) | 1020.5 kg/m³ | 1538.5 m/s | 0.45 m/s @ 040° |

**The physics is applied to the live stack, not just annotated:**
- **Density → buoyancy.** The site's EOS-80 (UNESCO Millero–Poisson) density
  is patched into the Gazebo world's `<graded_buoyancy><default_density>`, so
  buoyant force is that water's.
- **Position → GPS origin + map.** The world's `<spherical_coordinates>` and
  `constants.HOME_LAT/LON` move to the site, so ArduPilot SITL `--home`, the
  map, and the GPS/vision feeders all spawn there from one override.
- **Current → real hull drift.** `tools/inject_current.py` publishes the
  site's current vector to Gazebo's `/ocean_current`, so the hydrodynamics
  plugin physically drifts the hull.
- **Sound speed → acoustics.** Mackenzie (1981) sound speed, Thorp
  absorption, and spreading loss drive the acoustic model and cap the
  acoustic-spoof forged offset to the site's realistic USBL detection range.

Oceanographic formulas are implemented in `scaleup/sites/oceanography.py` and
validated against their published references. Fidelity is **Tier A**
(representative regional climatology); Tier B (INCOIS/GEBCO/CTD ingest, via the
built adapters in `scaleup/physics/`) and ray-traced (Bellhop) acoustics are
the documented next steps.

**Every applicable attack works at every site** — the site is the *environment*,
not the attack menu. Verdicts are **invariant** across the three sites (the
vulnerability is a property of the autopilot config, not the water).

## 4. Component map

| Directory | What's in it |
|---|---|
| `vehicle_twins/` | **The 4 ready-to-run digital twins** (§5), each a self-contained folder (`profile.json`, `target.json`, `README.md`). |
| `stonefish/` | The Stonefish underwater engine integration — AUV-150 scenario + ArduSub params + the C++ `MCR` runner (`mcr_src/`). |
| `godot_app/` | The Godot 4 operator console (scene, ocean shader, `world.gd`). |
| `scaleup/sites/` | The multi-site framework: cited site data (`data/*.json`), oceanography formulas, the `Site` model. |
| `scaleup/` (rest) | The additive "scale-up" layer (§8a): autopilot `backends/` (ArduPilot + PX4), `protocols/` (MAVLink + NMEA-0183), real-physics models (`physics/`), `twins/` registry, `compliance/` mapping, a REST `platform/api.py`, and the scripted `scenario/` engine. All default-off. |
| `profiles/` | Each twin's vehicle profile. Legacy generic reference vehicles (`wamv`, `blueboat`, `bluerov2`) are retained as the teaching/clone base (still functional). |
| `sim_config/` | Gazebo SDF models + worlds + install/build/start scripts. |
| `attacks/` | `gps_spoof.py` (FDM-relay, surface), `gps_input_inject.py` (protocol `GPS_INPUT`, any vehicle), `ais_spoof.py` (ghost + impersonation), `c2_replay.py` (forged mode-change + RC-override), `acoustic_spoof.py` (underwater position + legitimate nav feed, site-range-capped). |
| `detection/` | `detectors.py` (blind rule-based `DetectorSuite`), `run_detectors.py` (standalone live tap + CPU/RSS self-sampling). |
| `nodes/` | `ais_emulator/`; `monitor/src/dashboard_server.py` (Flask+SocketIO browser console) + its template; `app/mcr_app.py` (legacy pygame console). |
| `hardware/` | ESP32 firmware for hardware-in-the-loop: a rogue MAVLink C2 node (WiFi) and an NMEA-0183 sensor spoofer (UART), plus the C2 HIL harness. |
| `tools/` | Orchestration — see §6. |
| `targets/` | Connection-only configs for `test_target.py` against any ArduPilot SITL. |
| `target_runs/` | Per-run verdicts/evidence from `test_target.py` (current twins only). |
| `deploy/` | Docker packaging: `Dockerfile` (frozen base `mcr:latest`), `Dockerfile.dev` (scale-up overlay `mcr:dev`). |
| `app/` | Single-file application builders: Linux `.run` + Windows `.zip`. **Built on demand** — the repo no longer ships prebuilt packages in `dist/` (they predated the Indian-twin + Stonefish/Godot work and were removed). |
| `external/` | **Consolidated upstream build trees** — ArduPilot, ardupilot_gazebo, SITL_Models, the DAVE AUV workspace, the ArduPilot build venv (and, when built, the Stonefish source). Gitignored (multi-GB, rebuilt by `sim_config/install_*.sh`); compat symlinks remain at `$HOME`. |
| `constants.py` | The profile + site loader every script imports — single source of truth for home coords, AIS identity, ports, and the active site. |

## 5. The 4 digital twins

The twins are copies of **real, individually-named Indian platforms** — two
AUVs and two USVs. Each is a **single real platform in its stock, as-fielded
configuration** — there is no longer an artificial "vulnerable vs hardened"
pairing; you test the twin and read the posture it actually shows. (The verdict
vocabulary still includes RESILIENT — see §7 — it simply isn't pre-baked into a
separate hardened twin.) Full per-twin specs, sources, and honest fidelity
notes are in each twin's own `README.md` and in [`VALIDATION.md`](VALIDATION.md).

| Twin | Real platform | Domain / firmware | Body (Tier-A) |
|---|---|---|---|
| `auv150` | CSIR-CMERI / IIT-KGP **AUV-150** (150 m-class research AUV) | underwater / ArduSub | BlueROV2 (multi-thruster) |
| `maya_auv` | CSIR-NIO **Maya** (small torpedo AUV, Goa) | underwater / ArduSub | REMUS-100 (torpedo) |
| `interceptor_usv` | Indian Navy autonomous **fast interceptor** (BEL/WESEE **A2NCS**) | surface / ArduRover | CUSV |
| `survey_usv` | Small Indian **coastal-survey USV** (representative catamaran class) | surface / ArduRover | BlueBoat (catamaran) |

The hull bodies are representative stand-ins (Tier-A) — a security verdict
depends on the *firmware / protocol / sensor-source* layer (exact/encoded), not
on the representative hull, which only affects *how far* a spoof walks the
vehicle. The AUV-150 additionally has a tuned high-fidelity **Stonefish**
scenario (`stonefish/auv150.scn`). See `VALIDATION.md §1e` for measured dynamic
fidelity and the per-twin calibration status.

### Verified results (2026-10-22)

The 4-twin × attack matrix, each booted and attacked by `tools/test_target.py`:

| Twin | GPS spoof | AIS spoof | C2 mode-change | C2 RC-override | Acoustic spoof |
|---|---|---|---|---|---|
| `interceptor_usv` (USV) | **VULNERABLE** | N/A-to-autopilot (detect-only) | **VULNERABLE** | **VULNERABLE** | — |
| `survey_usv` (USV) | **VULNERABLE** | N/A-to-autopilot (detect-only) | **VULNERABLE** | **VULNERABLE** | — |
| `auv150` (AUV) | N/A (submerged) | N/A (submerged) | **VULNERABLE** | **VULNERABLE** | **VULNERABLE** (Δ≈50 m) |
| `maya_auv` (AUV) | N/A (submerged) | N/A (submerged) | **VULNERABLE** | **VULNERABLE** | **VULNERABLE** |

- **GPS** is **N/A** for a submerged AUV (RF does not penetrate water);
  **AIS** is **N/A to the autopilot** on every vehicle (ArduPilot never consumes
  AIS — it is an operator/ECDIS-layer risk, recorded as detectability-only on
  the surface and N/A submerged).
- **Acoustic-positioning spoofing** is the submerged analog of GPS spoofing —
  forging the ExternalNav/USBL position delivered as `VISION_POSITION_ESTIMATE`.
  The forged offset is capped per-site to the modelled USBL detection range.
  On the Stonefish AUV-150 stack the realistic **ramp** walk-off (0.5 m/s) walks
  the believed position ~11 m off the true track in 40 s while depth holds →
  VULNERABLE; a sudden 50 m **step** is correctly rejected by the EKF innovation
  gate in that compass-nav config (the Gazebo twins' step still reads VULNERABLE
  — the outcome is EKF-config dependent, which is itself a documented finding).
- Verdicts are **invariant across the three sites**, as expected.
- Every `verdicts.json` records the `site` and the code `git_sha`, and
  detectability is reported both as a raw count and broken out `by_attack_type`.

## 6. The tools layer

| Tool | What it does |
|---|---|
| `tools/app.sh` | **The operator application.** Launches the Godot 3D console with all physics integrated (AUV-150 → Stonefish, rest → Gazebo). `tools/app.sh stonefish\|gazebo\|pygame` forces one engine / the legacy renderer. |
| `tools/run_sim.sh <profile> up\|down\|status` | Boots one domain's full headless Gazebo stack (Gazebo → FDM relay → ArduPilot SITL → MAVLink bridge) with real health checks. Defaults to the Kochi site. |
| `tools/run_demo.sh <profile-or-twin-path> up\|down` | Same boot **plus** the browser dashboard and (by default) ocean-current injection. |
| `tools/run_vehicle.sh vehicle_twins/<name> up\|down` | Symlinks a twin's `profile.json` into `profiles/`, then calls `run_sim.sh`. |
| `tools/stonefish_bridge.sh up\|down` | Boots the Stonefish + ArduSub(ExternalNav) + mav_bridge + USBL-feed stack (`MCR_HEADLESS=1` for the integrated app). |
| `tools/test_target.py --target <path>` | Connects, baselines, runs the target's enabled attacks, taps `DetectorSuite` live, writes `target_runs/<name>/<ts>/verdicts.json`. **The core deliverable.** |
| `tools/test_all_4.py` | Boots → attacks → tears down all 4 twins in turn, aggregates verdicts. |
| `tools/test_all_sites.py` | Twin × site matrix + the cross-site invariance check. |
| `tools/run_scenario.py --site <id>` | Runs a scripted scenario (`scenarios/*.json`) with site physics, emitting a markdown/HTML report. |
| `tools/inject_current.py --site <id>` | Publishes the site's ocean current to Gazebo's `/ocean_current` (started automatically by `run_demo.sh`). |
| `tools/report.py <verdicts.json>` | Turns a run's verdicts into a plain-language markdown/HTML report. |
| `tools/site_info.py <id>` | Prints a site's computed physics (density, sound speed, current, detection range). |
| `tools/validate_target.py` / `validate_vehicle.py` | Pre-flight contract checks (no live connection). |
| `tools/teardown_all.sh` | Reliable orphan-process reaper (kills stranded gz/SITL/relay/bridge). |

## 7. The four verdict outcomes

Binary pass/fail is wrong for a testing tool — "nothing moved" is ambiguous
between "it resisted" and "it never ingested the attack." Every sub-check
returns one of:

- **VULNERABLE** — the target accepted the forged input and its reported state
  changed accordingly.
- **RESILIENT** — the attack was confirmed delivered, but fused state didn't
  materially move.
- **N/A** — structurally inapplicable (AIS on a bare ArduPilot vehicle; GPS on
  a submerged AUV).
- **INCONCLUSIVE** — preconditions unmet (e.g. never confirmed armed) or the
  target stopped heartbeating (possible crash/DoS — a separate, more
  interesting finding than "resilient").

## 8. Known limitations (honest state)

- **Gazebo AUV AUTO-mode waypoint tracking is unreliable** — the Gazebo
  vectored-thruster AUV line never cleanly tracked a clicked destination (a
  motor-mixing/frame-rotation issue in the position controller). The **Stonefish**
  AUV-150 scenario was rebuilt to fix exactly this and now flies straight at
  ~1.8 m/s with stable depth/heading hold; prefer it for AUV navigation visuals.
  None of this affects any C2/acoustic/`test_target` verdict (those don't depend
  on AUTO tracking).
- **Hull fidelity is Tier-A.** Bodies are representative stand-ins, not the real
  geometry/hydrodynamics. `maya_auv` is drag-calibrated to ~real speed;
  `interceptor_usv` cannot reach its real 45 kn (the CUSV displacement body
  can't plane — a body-class limit, not a tuning gap). This changes divergence
  *magnitudes*, never a security *verdict*. See `VALIDATION.md §1`.
- **The acoustic vector is not field-proven.** No real AUV has been publicly
  acoustic-spoofed; that verdict rests on protocol logic + analogues, not a
  field test. The other three vectors (GPS/C2/AIS) are field-confirmed on
  comparable real platforms (`VALIDATION.md §2`).
- **Site fidelity is Tier A** (representative climatology), not live
  observational data. Tier B (INCOIS/GEBCO/CTD) and Bellhop ray-traced
  acoustics are the next upgrades — the adapters already exist in `scaleup/physics/`.
- **`wamv` (legacy VRX) does not boot headless in Docker** — the VRX world
  stalls in the containerised Gazebo server. Native boot is fine; the 4 primary
  twins (non-VRX path) are the Docker-supported set.
- The `external/` build trees are host-specific (absolute paths); they are
  gitignored and rebuilt by `sim_config/install_*.sh` on a new machine. The
  portable artifact is the Docker image (or an on-demand `app/` package build).

### 8a. The scale-up layer (additive, default-off)

`scaleup/` grows the range from "an ArduPilot attack harness with good
oceanography" toward a generic maritime cyber range with real-world physics,
all additive and off the frozen release path. Built & tested: autopilot-agnostic
backends (ArduPilot + PX4 adapter), protocol adapters (MAVLink + a real NMEA-0183
codec/spoofer), real-physics models (sensor error, JONSWAP sea state, harmonic
tides, image-method acoustics + Bellhop adapter, CTD/WOA/GEBCO ingest, real AIS
feed), a twin registry/scaffolder, multi-framework compliance mapping
(IACS/IMO/IEC 62443/NIST 800-82r3/MITRE ATT&CK ICS/DNV), a range-as-a-service
REST API, and ESP32 hardware-in-the-loop firmware. Items that need external
data/hardware (PX4 SITL install, GEBCO, the Bellhop binary, an SDR) ship as an
adapter + working fallback, tier-marked, never faked. Full per-item status:
[`ROADMAP.md`](ROADMAP.md).

## 9. Repository & release layout

- **Branches.** Active work is on `feat/upscale`. `master` is the stable line;
  `scaleup` is the multi-site branch.
- **Engines.** Gazebo is the committed default; Stonefish needs its upstream
  source + a one-time `MCR` build (`stonefish/README.md`); Godot needs the
  Godot 4 binary.
- **Regression gate.** `tools/test_all_4.py` must still produce the expected
  verdicts, and the `scaleup/tests/` offline suite (40 tests) must stay green,
  before a release is cut.
- **Standards mapping.** Verdicts map to IACS UR E26/E27 and IMO MSC.428(98),
  with the broader framework map in `scaleup/compliance/`.

For the exact commands to run any of this — Docker or native — see
[`RUNNING.md`](RUNNING.md).
