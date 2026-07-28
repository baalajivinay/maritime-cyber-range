#!/bin/bash
set -e
export GZ_SIM_SYSTEM_PLUGIN_PATH=$HOME/ardupilot_gazebo/build:$GZ_SIM_SYSTEM_PLUGIN_PATH
export GZ_SIM_RESOURCE_PATH=$HOME/ardupilot_gazebo/models:$HOME/ardupilot_gazebo/worlds:$HOME/SITL_Models/Gazebo/models:$HOME/SITL_Models/Gazebo/worlds:$GZ_SIM_RESOURCE_PATH
source /opt/ros/jazzy/setup.bash
source ~/maritime-cyber-range/ros2_ws/install/setup.bash
ros2 launch vrx_gz competition.launch.py world:=sydney_regatta headless:=True urdf:=$HOME/maritime-cyber-range/sim_config/wamv_ardupilot.sdf extra_gz_args:="-v 4"
