# AUV twin — vulnerable — REMUS-100

**Real hardware digital twin**: US Navy REMUS-100 shallow-water
mine-countermeasures AUV — the most-cited AUV in academic hydrodynamics
literature. Hull mass (31.9 kg), dimensions (1.6 m long, 0.19 m diameter),
inertia, and drag are sourced directly from Thor I. Fossen's MIT-licensed,
still-maintained `PythonVehicleSimulator` reference implementation
(`vehicles/remus100.py`, github.com/cybergalactic/PythonVehicleSimulator).
Fossen's file separately notes a 1.9 m variant appears elsewhere in the
literature; this twin uses the 1.6 m figure from the maintained reference
implementation itself, stated here rather than picked silently.

**Disclosed actuation mismatch**: the real REMUS-100 is fin-steered (one
propeller plus rudder/stern-plane control fins). No ArduPilot firmware
supports that control scheme for an underwater vehicle — ArduSub's entire
motor-mixing library (`AP_Motors6DOF`, every frame type including CUSTOM)
is architecturally "N thrusters into a 6DOF force/torque matrix," with zero
concept of a control surface; confirmed further against ArduPilot's own
open GitHub issue #21568 (requests exactly this capability, unimplemented)
and a Blue Robotics community thread stating plainly no autopilot firmware
currently supports it. A genuine attempt was made to get real fin-steered
control via ArduPlane firmware instead: EKF/arming survived underwater (a
real, novel result), but ArduPlane's throttle path either silently ignores
RC override (MANUAL mode's RC-validity gate) or crashes with a
floating-point exception (GUIDED mode's TECS, built around real-airspeed
math that doesn't exist underwater) — a firmware-level dead end, not a
config problem. This twin therefore uses a 6-thruster vectored frame, the
same proven architecture BlueROV2 already uses on ArduSub, repositioned
and rescaled for REMUS's slim 1.6x0.19 m hull. Real hull physics, disclosed
simplified actuation — see `sim_config/models/remus100/model.sdf`'s header
for the full citation trail.

**Out-of-the-box ArduSub config** — no GCS-link hardening.

## Expected result against all 3 attacks

| Attack | Vulnerability | Why |
|---|---|---|
| GPS spoof | **N/A** | Real physics, not a config choice: RF/GPS doesn't penetrate water. This vehicle's EK3_SRC1_POSXY is ExternalNav-driven, not GPS, while submerged. |
| AIS spoof | **N/A** | Platform fact -- ArduPilot never consumes AIS (transmit-only), and AIS is RF/surface-only regardless. |
| C2 replay (mode-change + RC-override) | **VULNERABLE** | No `MAV_OPTIONS`/`MAV_GCS_SYSID` enforcement configured -- accepts GCS-privileged commands from any sender. |

C2 is the only attack surface that applies to a submerged AUV at all in
this project's threat model -- that's a real architectural fact about
underwater vehicles, not something scoped down for this demo.

## Verified live result (2026-08-08, `tools/test_target.py`)

```
mode_change: VULNERABLE  (forged ALT_HOLD accepted -- post_mode == forged_mode)
rc_override: VULNERABLE  (armed_confirmed=true, armed_during_injection=true,
                           pre_servo5=1500 -> peak_servo5_during_injection=1300)
detectability: c2_replay=1.0 (precision=1.0, recall=1.0)
```

Full evidence: `target_runs/auv_vulnerable_remus100/20260808T232733/verdicts.json`.

## Boot it

```bash
tools/run_vehicle.sh vehicle_twins/auv_vulnerable_remus100 up
python3 tools/test_target.py --target vehicle_twins/auv_vulnerable_remus100/target.json
tools/run_vehicle.sh vehicle_twins/auv_vulnerable_remus100 down
```

See `docs/TWIN_DEMO_GUIDE.md` for the full walkthrough and dashboard usage.
