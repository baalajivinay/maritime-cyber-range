# Autonomous Maritime Cyber Range

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![ROS 2](https://img.shields.io/badge/ROS_2-Jazzy-22314E?style=flat-square&logo=ros&logoColor=white)](https://docs.ros.org/en/jazzy/)
[![Gazebo](https://img.shields.io/badge/Gazebo-Harmonic-F58113?style=flat-square)](https://gazebosim.org/)
[![ArduPilot](https://img.shields.io/badge/ArduPilot-SITL%2FMAVLink-CC2936?style=flat-square)](https://ardupilot.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)

A simulation-based cyber range for autonomous maritime vehicles. Real
ArduPilot/ArduSub autopilot firmware (SITL) is coupled to a real physics engine
(Gazebo, or the higher-fidelity Stonefish underwater engine) to form **digital
twins** of real, named Indian platforms — two USVs (an autonomous fast
interceptor and a coastal-survey catamaran) and two AUVs (CSIR's **AUV-150**
and **Maya**) — then attacked with GPS spoofing, AIS spoofing, C2 hijack, and
acoustic-positioning spoofing. A Godot 3D console, a live browser dashboard, and
a vehicle-agnostic CLI tester report, per attack, whether the vehicle was fooled
and whether a blind monitor would have caught it.

The range runs at real **Indian naval waters** — **Kochi** (default), Mumbai,
and Visakhapatnam — each reproducing that water body's cited oceanography
(density, ocean current, sound-speed profile). Pick the twin and the site from
the console/dashboard header; everything relocates and re-physics around the choice.

## Documentation — just two files

| Read | For |
|---|---|
| **[`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md)** | The complete picture: what it is, the architecture, the multi-site framework, the 4 twins, verified results, verdict methodology, known limits. **Start here.** |
| **[`docs/RUNNING.md`](docs/RUNNING.md)** | Every command: run the operator app, run from source, build a shareable package, pick a twin/site, fire attacks, run the resilience tester, reproduce the attack matrix, scripted scenarios, native setup. |

(`docs/EXECUTION_STATE.md` is the dated engineering log; `docs/reference/`
holds the founding brief, research PDFs, and the slide deck.)

## Quick start

**Operator application (Godot 3D console)** — needs a graphical display:

```bash
tools/app.sh                             # pick a site + twin, watch, attack
```

**From source (Docker build, browser dashboard):**

```bash
./launch.sh build && ./launch.sh up      # then open http://localhost:8080
```

**Headless resilience test of one twin:**

```bash
tools/run_vehicle.sh vehicle_twins/interceptor_usv up
python3 tools/test_target.py --target vehicle_twins/interceptor_usv/target.json
tools/run_vehicle.sh vehicle_twins/interceptor_usv down
```

A shareable, toolchain-free package (`.run` / `.zip`) is **built on demand** via
`app/build-*.sh` — the repo no longer ships a prebuilt copy.

## Layout

- `vehicle_twins/` — the 4 ready-to-run twins (2 USV + 2 AUV: `interceptor_usv`, `survey_usv`, `auv150`, `maya_auv`), self-contained folders.
- `stonefish/` — the Stonefish underwater engine integration (AUV-150 scenario + C++ runner).
- `godot_app/` — the Godot 4 operator console.
- `scaleup/` — the multi-site framework (`sites/` cited ocean physics) + the scripted scenario engine (`scenario/`) + the additive generic/real-physics layer.
- `attacks/` — GPS / AIS / C2 / acoustic attack modules.
- `detection/` — blind rule-based detectors.
- `nodes/monitor/` — the Flask + Socket.IO + Leaflet browser dashboard; `nodes/app/` — the legacy pygame console.
- `tools/` — orchestration (`app`/`run_sim`/`run_demo`/`run_vehicle`/`stonefish_bridge`), `test_target.py`, `test_all_4.py`, `run_scenario.py`, site utilities.
- `profiles/` / `targets/` — vehicle and target configs.
- `sim_config/` — Gazebo SDF models/worlds + install/build scripts.
- `hardware/` — ESP32 hardware-in-the-loop firmware (C2 node + NMEA spoofer).
- `deploy/` — Docker packaging (`Dockerfile`, `Dockerfile.dev`).
- `app/` — single-file Ubuntu `.run` + Windows `.zip` builders.
- `external/` — consolidated upstream build trees (ArduPilot, Gazebo plugin, SITL_Models, DAVE, build venv); gitignored, with compat symlinks at `$HOME`.
- `constants.py` — the profile + site loader every script imports.
