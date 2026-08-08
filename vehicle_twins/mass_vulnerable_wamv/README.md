# MASS twin — vulnerable — WAM-V

**Real hardware digital twin**: the WAM-V catamaran USV (VRX simulation
stack), full Gazebo hydrodynamics. **Out-of-the-box ArduPilot/ArduRover
config** -- nothing in this folder hardens it. This is the baseline: what a
vehicle looks like before anyone has hardened its GCS link or its GPS
trust model.

## Expected result against all 3 attacks

| Attack | Vulnerability | Why |
|---|---|---|
| GPS spoof | **VULNERABLE** | Position spoofed at the physics/FDM level, which feeds every onboard sensor identically -- no independent signal for the EKF to cross-check against, so the forged position is accepted into the fused belief. |
| AIS spoof | **N/A** | Platform fact, not a per-vehicle config choice -- ArduPilot never consumes AIS (transmit-only architecture). Same on every twin in this set. |
| C2 replay (mode-change + RC-override) | **VULNERABLE** | No `MAV_OPTIONS`/`MAV_GCS_SYSID` enforcement configured -- ArduPilot accepts GCS-privileged commands from any sender by default (confirmed: `accept_packet()` fails open unless `GCS_SYSID_ENFORCE` is explicitly turned on). |

## Boot it

```bash
tools/run_vehicle.sh vehicle_twins/mass_vulnerable_wamv up
python3 tools/test_target.py --target vehicle_twins/mass_vulnerable_wamv/target.json
tools/run_vehicle.sh vehicle_twins/mass_vulnerable_wamv down
```

See `docs/TWIN_DEMO_GUIDE.md` for the full walkthrough and dashboard usage.
