# Autonomous Maritime Cyber Range

Real-physics USV simulation (ArduPilot SITL + Gazebo/VRX) with GPS/AIS/C2
attack modules and a live monitoring dashboard. See
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
- `attack_logs/` -- ground-truth CSVs written by each attack module
- `evidence/` -- screenshots/video from demo runs
- `tools/` -- `capture_demo.py`, a Playwright-based screenshot/video capture helper
- `constants.py` -- single source of truth for home coordinates, AIS
  MMSI, and every port used across the scripts above

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
