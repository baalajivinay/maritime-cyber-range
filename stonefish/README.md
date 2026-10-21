# Stonefish integration — high-fidelity underwater AUV sim + ArduSub bridge

Stonefish simulates the AUV (realistic hydrodynamics + caustics + sonar/DVL) and
is bridged to ArduSub SITL via ArduPilot's JSON FDM protocol, so the cyber-range
attacks run against it exactly like the Gazebo stack.

## Files
- `auv150.scn` — the AUV-150 scenario (torpedo hull + 5 thrusters + DVL/IMU/
  pressure/GPS) in the Kochi environment.
- `auv150_ardusub.parm` — ArduSub ExternalNav config (position from USBL, not GPS).
- `mcr_src/` — the C++ runner (`MCR`): parses a `.scn`, renders it, and runs the
  JSON FDM loop (servo PWM -> thrusters; pose/IMU -> sensors; true pose broadcast
  on :9005 for the USBL feed).

## Build (one-time)
```bash
git clone https://github.com/patrykcieslak/stonefish.git ~/stonefish_src
# header-only GLM (no sudo): git clone -b 1.0.1 https://github.com/g-truc/glm ~/glm_src
cp maritime-cyber-range/stonefish/mcr_src ~/stonefish_src/Tests/MCR -r
# add to ~/stonefish_src/Tests/CMakeLists.txt:
#   add_executable(MCR MCR/main.cpp MCR/MCRApp.cpp MCR/MCRManager.cpp)
#   target_link_libraries(MCR Stonefish_test)
cd ~/stonefish_src && mkdir -p build && cd build
cmake .. -DBUILD_TESTS=ON -DCMAKE_CXX_FLAGS="-I$HOME/glm_src" && make -j MCR
```

## Run (from the repo)
```bash
tools/stonefish_bridge.sh up     # Stonefish + ArduSub(ExternalNav) + mav_bridge + USBL feed
echo step | nc -u -w1 127.0.0.1 10120     # acoustic spoof ON   (off: echo off | ...)
tools/stonefish_bridge.sh down
```
Verified: the acoustic spoof walks the AUV's believed position ~50 m off its true
Stonefish track (VULNERABLE), via the ExternalNav/USBL feed.
