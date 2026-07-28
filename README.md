# Autonomous Maritime Cyber Range

Real-physics vehicle simulation (ArduPilot SITL + Gazebo) with GPS/AIS/C2
attack modules and a live monitoring dashboard, for **both surface (MASS)
and underwater (AUV) vehicles** -- dual-domain by design, not surface-only.
The surface track (WAM-V/ArduRover) is verified end-to-end today; the
underwater track (ArduSub) is in progress, see
[`docs/ROADMAP.md`](docs/ROADMAP.md) for current status. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the component map, port
topology, and running order, and
[`docs/Maritime_Cyber_Range_Progress_Report.docx`](docs/Maritime_Cyber_Range_Progress_Report.docx)
for project history/milestones.

## Layout

- `ros2_ws/` -- colcon workspace (`src/vrx`, the vendored VRX simulator, is
  a git submodule; `build/`/`install/`/`log/` are gitignored and must be
  regenerated locally, see below)
- `attacks/` -- GPS spoofing, AIS spoofing, C2 replay/injection, autonomous
  mission demo
- `nodes/` -- AIS emulator, monitoring dashboard (Flask-SocketIO + Leaflet)
- `sim_config/` -- SDF vehicle config, install/build/start shell scripts
- `profiles/` -- one JSON file per vehicle (home coords, AIS identity,
  ports, applicable attack set); select which one is active with the
  `MCR_VEHICLE_PROFILE` env var (defaults to `wamv`) -- see
  `docs/ARCHITECTURE.md`'s "Vehicle profiles" section for the schema
- `attack_logs/` -- ground-truth CSVs written by each attack module
- `evidence/` -- screenshots/video from demo runs
- `tools/` -- `capture_demo.py`, a Playwright-based screenshot/video capture helper
- `constants.py` -- loads the active vehicle profile and exposes it as the
  single source of truth every script imports (home coordinates, AIS MMSI,
  every port)

## First-time setup

```bash
git clone --recurse-submodules <this repo>
# or, if already cloned:
git submodule update --init --recursive

sim_config/install_ros2.sh
sim_config/install_gazebo.sh
sim_config/install_ardupilot.sh
sim_config/build_ardupilot.sh
cd ros2_ws && colcon build && cd ..
```

## Action items from the pre-consolidation audit

- **Rotate the machine's sudo password.** It was previously hardcoded in
  plaintext in `build_vrx.sh`/`install_ardupilot.sh` (now removed from both
  -- they prompt interactively instead). If this password is still in use
  anywhere, change it.
- After this reorg, `ros2_ws/build`, `ros2_ws/install`, and `ros2_ws/log`
  were intentionally not carried over (they contain absolute paths baked
  in by CMake that would silently break if moved) -- run `colcon build`
  fresh inside `ros2_ws/` before launching the sim.
