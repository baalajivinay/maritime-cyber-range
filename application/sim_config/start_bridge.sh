#!/bin/bash
set -e
source /opt/ros/jazzy/setup.bash
ros2 run ros_gz_bridge parameter_bridge /model/wildthumper/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry
