# Stonefish integration — high-fidelity underwater AUV sim + ArduSub bridge

Stonefish simulates the AUV (realistic hydrodynamics + caustics + sonar/DVL) and
is bridged to ArduSub SITL via ArduPilot's JSON FDM protocol, so the cyber-range
attacks run against it exactly like the Gazebo stack.

## Files
- `auv150.scn` — the AUV-150 scenario: torpedo hull (near-neutral buoyancy,
  ~541 kg vs ~543 kg displaced) + tail fins (hydrodynamic damping) + 5 thrusters
  laid out to ArduSub's **SIMPLEROV_5** frame + DVL/IMU/pressure/GPS, in the
  Kochi environment.
- `auv150_ardusub.parm` — ArduSub config: `FRAME_CONFIG=6` (SIMPLEROV_5), the
  realistic AUV nav split (**horizontal position from ExternalNav/USBL**, which
  the acoustic spoof forges; **heading from the compass/INS**; depth from the
  pressure sensor), and conservative, stable depth/heading PID gains.
- `mcr_src/` — the C++ runner (`MCR`): parses a `.scn`, renders it, and runs the
  JSON FDM loop (servo PWM -> thrusters; pose/IMU -> sensors; true pose broadcast
  on :9005 for the USBL feed). Thrusters are looked up by their `"<robot>/<name>"`
  namespace (e.g. `AUV150/ThrPortFwd`), which is how Stonefish registers them.

## Active control (ArduSub drives the Stonefish body)
`tools/stonefish_control_test.py` arms ArduSub and commands dive / depth-hold /
heading / forward via `MANUAL_CONTROL`, measuring the response. Validated,
repeatable across runs:
- **depth-hold**: drift < 0.2 m, wobble < 0.3 m *while cruising at 1.8 m/s*
  (ALT_HOLD); holds through the forward leg with no creep
- **heading-hold**: turns ~30 deg on command and settles to ~11–13 deg wobble;
  flies level (roll/pitch within a few deg)
- **forward cruise**: ~1.8 m/s (meets/exceeds the AUV-150's ~1.5 m/s spec)
- all consistent run-to-run; robust arm

**Static stability + correct sign conventions are what make it fly straight.**
The scenario's port/starboard sides are mirrored from ArduSub's SIMPLEROV_5
convention, so BOTH differential thruster pairs must be swapped in the MCR map
(`stonefish/mcr_src/MCRManager.cpp`) or the feedback is positive and the hull
diverges — roll (vertical pair) and yaw (horizontal pair). The hull also carries
a dense **keel ballast** low in the body (CG below CB) for passive roll/pitch
self-righting, and the tail **fins are neutrally buoyant** (so the tail does not
float up and pitch the nose down). The horizontal thrusters are dual-purpose
(common-mode = surge, differential = yaw), so cruise thrust is sized for ~1.8 m/s
with the fins sized for damping and the yaw gains kept moderate.

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
python3 tools/stonefish_control_test.py   # verify active depth/heading/forward control
echo ramp | nc -u -w1 127.0.0.1 10120     # acoustic spoof ON (ramp = realistic walk-off)
echo off  | nc -u -w1 127.0.0.1 10120     # spoof OFF (transparent USBL)
tools/stonefish_bridge.sh down

# MCR_HEADLESS=1 runs Stonefish as pure physics (no window) -- this is how the
# integrated app uses it, so Godot is the only window:
MCR_HEADLESS=1 tools/stonefish_bridge.sh up
```

## One app, all the physics
`tools/app.sh` launches the Godot console with every engine integrated: it
auto-routes each vehicle to its best physics via `tools/unified_backend.py` --
the AUV-150 onto this Stonefish stack (started headless on demand) and the other
twins onto the Gazebo + real-data models -- all feeding the one Godot window.
Force a single engine with `tools/app.sh stonefish` or `tools/app.sh gazebo`.
Verified end-to-end: ArduSub holds depth/heading on Stonefish's 6-DOF
hydrodynamics (the combined-physics closed loop), and the acoustic **ramp**
spoof walks the AUV's believed position steadily off its true Stonefish track
(~11 m in 40 s at 0.5 m/s injection) while the vehicle keeps holding depth —
**VULNERABLE**. A sudden 50 m *step* is correctly rejected by the EKF
innovation gate, so the realistic attack is the gradual ramp.
