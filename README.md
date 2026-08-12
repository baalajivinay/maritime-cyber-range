# Autonomous Maritime Cyber Range

Real-physics vehicle simulation (ArduPilot SITL + Gazebo) with GPS/AIS/C2
attack modules, a live monitoring dashboard, and a CLI resilience-testing
tool, for **both surface (MASS) and underwater (AUV) vehicles** --
dual-domain by design, not surface-only, both tracks verified end-to-end.

Four self-contained digital twins under `vehicle_twins/` are ready to run
today -- copies of real, individually-named Navy/research hardware (the
Textron Fleet-class CUSV and the REMUS-100 AUV), one vulnerable and one
GCS-link-hardened per pair -- see
[`docs/TWIN_DEMO_GUIDE.md`](docs/TWIN_DEMO_GUIDE.md) for the full
step-by-step (boot, attack, read the verdict, tear down) and
[`docs/TARGET_TESTING.md`](docs/TARGET_TESTING.md) for `tools/test_target.py`,
the vehicle-agnostic resilience tester this project's real deliverable is
built around (point it at any ArduPilot SITL, not just these 4 twins). See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the component map, port
topology, and running order, and
[`docs/EXECUTION_STATE.md`](docs/EXECUTION_STATE.md) for the dated,
blow-by-blow build history (start there for full project context).

## Documentation map

| Start here | For |
|---|---|
| [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) | **Read this first if you're new** (including a fresh AI session) -- the complete, current-state picture of the whole project in one file: why it exists, how it's built, every component, all 4 twins' verified results, known issues, how to run everything. |
| [`docs/TWIN_DEMO_GUIDE.md`](docs/TWIN_DEMO_GUIDE.md) | Boot a twin, run attacks, read the verdict, tear down -- the fastest path to seeing the whole product work. |
| [`docs/TARGET_TESTING.md`](docs/TARGET_TESTING.md) | `tools/test_target.py`, the vehicle-agnostic resilience tester -- point it at any ArduPilot SITL, not just this repo's own twins. |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Docker packaging (`./launch.sh`) -- no native ROS/Gazebo/ArduPilot install needed. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Component map, port topology, vehicle-profile schema. |
| [`docs/VEHICLE_TWIN_CONTRACT.md`](docs/VEHICLE_TWIN_CONTRACT.md) | **Bring your own vehicle**: the `vehicle_twins/<name>/` folder contract (`profile.json`/`target.json` schemas, model.sdf requirements) and how to validate, boot, attack, and score it in this environment. |
| [`docs/DESIGNER_GUIDE.md`](docs/DESIGNER_GUIDE.md) | Deeper reference: attacks, detection/scoring internals, adding a new vehicle. |
| [`docs/NEW_AUV_QUICKSTART.md`](docs/NEW_AUV_QUICKSTART.md) | Full worked example: clone an existing AUV model into a genuinely new one. |
| [`docs/EXECUTION_STATE.md`](docs/EXECUTION_STATE.md) | Dated, blow-by-blow build history -- read this to resume in-flight work. |

## Layout

- `vehicle_twins/` -- the 4 ready-to-run digital twins (2 MASS + 2 AUV,
  one vulnerable/one hardened each); each is a self-contained folder
  (`profile.json`, `target.json`, `README.md`, `hardened.parm` where
  applicable) -- see `docs/TWIN_DEMO_GUIDE.md`
- `sim_config/` -- SDF vehicle models/worlds, install/build/start shell
  scripts
- `profiles/` -- one JSON file per vehicle (home coords, AIS identity,
  ports, applicable attack set); select which one is active with the
  `MCR_VEHICLE_PROFILE` env var (defaults to `wamv`) -- see
  `docs/ARCHITECTURE.md`'s "Vehicle profiles" section for the schema
- `attacks/` -- GPS spoofing, AIS spoofing, C2 replay/injection, autonomous
  mission demo
- `detection/` -- blind rule-based detectors + offline scoring
- `nodes/` -- AIS emulator, monitoring dashboard (Flask-SocketIO + Leaflet)
- `tools/` -- orchestration: `run_sim.sh`/`run_demo.sh`/`run_vehicle.sh`
  (boot), `test_target.py` (resilience tester), `generate_target_report.py`
  (cross-target report), `score_detectors.py`, `validate_vehicle.py`
- `targets/` -- connection-only target configs for `test_target.py` against
  *any* ArduPilot SITL (not tied to this repo's own vehicle models)
- `ros2_ws/` -- colcon workspace (`src/vrx`, the vendored WAM-V/VRX
  simulator, is a git submodule; `build/`/`install/`/`log/` are gitignored
  and must be regenerated locally, see below)
- `deploy/` -- Docker packaging (`Dockerfile`, `entrypoint.sh`) -- see
  `docs/DEPLOY.md`
- `attack_logs/` -- ground-truth CSVs written by each attack module
- `target_runs/` -- per-run verdicts/evidence from `test_target.py`
- `evidence/` -- screenshots/video/logs from demo runs
- `constants.py` -- loads the active vehicle profile and exposes it as the
  single source of truth every script imports (home coordinates, AIS MMSI,
  every port)

## First-time setup

```bash
git clone --recurse-submodules <this repo>
# or, if already cloned:
git submodule update --init --recursive

sim_config/install_ros2.sh          # ROS 2 Jazzy
sim_config/install_gazebo.sh        # Gazebo Harmonic
sim_config/install_ardupilot.sh     # ArduPilot SITL build prerequisites
sim_config/build_ardupilot.sh       # builds ardurover + ardusub
sim_config/install_sim_assets.sh    # ArduPilotPlugin, SITL_Models, BlueROV2 (dave)
cd ros2_ws && colcon build && cd .. # builds the vendored VRX (WAM-V) workspace
```

No GPU required for the CLI resilience tester or the web dashboard; a GPU
desktop is only needed to view the Gazebo 3D window itself
(`tools/view_3d.sh`).

Don't want to install any of this natively? See
[`docs/DEPLOY.md`](docs/DEPLOY.md) for the one-command Docker path
(`./launch.sh build && ./launch.sh up`) instead.

## Quick start

Boot the vulnerable CUSV twin, run the full attack suite against it, read
the verdict, tear down:

```bash
tools/run_vehicle.sh vehicle_twins/mass_vulnerable_cusv up
python3 tools/test_target.py --target vehicle_twins/mass_vulnerable_cusv/target.json
tools/run_vehicle.sh vehicle_twins/mass_vulnerable_cusv down
```

Prints a verdict per attack, then writes
`target_runs/mass_vulnerable_cusv/<timestamp>/verdicts.json`. Want to watch
it happen live in a browser instead of the terminal? Swap `run_vehicle.sh`
for `run_demo.sh` and open `http://localhost:8080` -- see
[`docs/TWIN_DEMO_GUIDE.md`](docs/TWIN_DEMO_GUIDE.md) for the full walkthrough,
all 4 twins, and how to read the results.

## Action items from the pre-consolidation audit

- **Rotate the machine's sudo password.** It was previously hardcoded in
  plaintext in `build_vrx.sh`/`install_ardupilot.sh` (now removed from both
  -- they prompt interactively instead). If this password is still in use
  anywhere, change it.
- After this reorg, `ros2_ws/build`, `ros2_ws/install`, and `ros2_ws/log`
  were intentionally not carried over (they contain absolute paths baked
  in by CMake that would silently break if moved) -- run `colcon build`
  fresh inside `ros2_ws/` before launching the sim.
