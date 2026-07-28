#!/bin/bash
set -e
source /opt/ros/jazzy/setup.bash
cd ~/maritime-cyber-range/ros2_ws
sudo rosdep install --from-paths src --ignore-src -r -y
colcon build
