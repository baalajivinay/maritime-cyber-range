# AUV twin — vulnerable — BlueROV2

**Real hardware digital twin**: Blue Robotics BlueROV2, 6-thruster vectored
frame, full Gazebo buoyancy/hydrodynamics. **Out-of-the-box ArduSub
config** -- no GCS-link hardening.

## Expected result against all 3 attacks

| Attack | Vulnerability | Why |
|---|---|---|
| GPS spoof | **N/A** | Real physics, not a config choice: RF/GPS doesn't penetrate water. This vehicle's EK3_SRC1_POSXY is ExternalNav-driven, not GPS, while submerged. |
| AIS spoof | **N/A** | Platform fact -- ArduPilot never consumes AIS (transmit-only), and AIS is RF/surface-only regardless. |
| C2 replay (mode-change + RC-override) | **VULNERABLE** | No `MAV_OPTIONS`/`MAV_GCS_SYSID` enforcement configured -- accepts GCS-privileged commands from any sender. |

C2 is the only attack surface that applies to a submerged AUV at all in
this project's threat model -- that's a real architectural fact about
underwater vehicles, not something scoped down for this demo.

## Boot it

```bash
tools/run_vehicle.sh vehicle_twins/auv_vulnerable_bluerov2 up
python3 tools/test_target.py --target vehicle_twins/auv_vulnerable_bluerov2/target.json
tools/run_vehicle.sh vehicle_twins/auv_vulnerable_bluerov2 down
```

See `docs/TWIN_DEMO_GUIDE.md` for the full walkthrough and dashboard usage.
