#!/bin/bash
set -e

# ArduPilotPlugin for Gazebo -- the bridge between ArduPilot SITL and Gazebo
# (every vehicle's model.sdf loads this). Pinned to the same commit the
# Docker image builds (deploy/Dockerfile's ARDUPILOT_GAZEBO_COMMIT), so the
# native and containerized setups stay identical.
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
git clone https://github.com/ArduPilot/ardupilot_gazebo.git ~/ardupilot_gazebo
cd ~/ardupilot_gazebo
git checkout 082a0fe
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
make -j"$(nproc)"

# SITL_Models -- ArduPilot's own reference Gazebo worlds/models (ground
# station, misc shared assets referenced by sim_config/*_world.sdf).
git clone --depth 1 https://github.com/ArduPilot/SITL_Models.git ~/SITL_Models

# dave -- the BlueROV2 Gazebo model + its ardusub.parm defaults, used by
# auv_vulnerable_bluerov2/auv_resilient_bluerov2_hardened and as the base
# BlueROV2 profile docs/NEW_AUV_QUICKSTART.md clones from.
mkdir -p ~/auv_ws/src
git clone --depth 1 --branch ros2 https://github.com/ioes-lab/dave.git ~/auv_ws/src/dave
