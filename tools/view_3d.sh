#!/bin/bash
# Open the Gazebo 3D GUI attached to the ALREADY-RUNNING simulator, so you get
# the immersive 3D view (boat on water / AUV diving / thrusters) ALONGSIDE the
# dashboard. The sim runs headless (gz sim -s); this is just the GUI client.
#
#   tools/run_demo.sh <profile> up      # first: sim + dashboard
#   tools/view_3d.sh                    # then: attach the 3D view
#
# REQUIRES A GPU DISPLAY. The GUI renders with OpenGL, so it must run on a
# session with working GPU acceleration (e.g. your laptop's real desktop with
# the NVIDIA/Intel driver active). On a headless/remote/virtual display with no
# usable GL (libEGL "driver (null)"), it falls back to slow software rendering
# and meshes may not draw -- that's a driver/display limitation, not the sim.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source /opt/ros/jazzy/setup.bash 2>/dev/null
source "$REPO/ros2_ws/install/setup.bash" 2>/dev/null   # puts VRX/WAM-V models on the resource path
export GZ_SIM_SYSTEM_PLUGIN_PATH="$HOME/ardupilot_gazebo/build:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"
export GZ_SIM_RESOURCE_PATH="$REPO/sim_config/models:${GZ_SIM_RESOURCE_PATH:-}"

if [ -z "${DISPLAY:-}" ]; then
  echo "No DISPLAY set -- run this on a machine with a graphical desktop + GPU."
  exit 1
fi

echo "Attaching Gazebo 3D GUI to the running sim (needs a GPU display)..."
echo "If the window is black/slow, your session has no GPU acceleration -- use the dashboard for the live demo and run this on a GPU desktop."
exec gz sim -g
