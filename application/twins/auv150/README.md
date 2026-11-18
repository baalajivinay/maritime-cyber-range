# auv150 — CSIR-CMERI / IIT-KGP "AUV-150" digital twin

A digital twin of **AUV-150**, India's indigenous 150 m-class Autonomous
Underwater Vehicle, developed by **CSIR-CMERI (Durgapur)** with **IIT Kharagpur**
(sea trials off Chennai, 2011). One of **two real Indian AUVs** in this range.

## Real vehicle — published specifications
| Property | Value | Notes |
|---|---|---|
| Length | 4.8 m | |
| Diameter | 0.5 m | |
| Weight | ~490 kg | |
| Depth rating | 150 m | the "150" in the name |
| Max speed | ~3 kn (2–4 kn) | |
| Mission time | 4–6 h | payload 20–30 kg |
| Propulsion | **5 thrusters, 5 DOF** | mechanical roll stabilisation |
| Nav suite | GPS, INS, DVL, altimeter | payload: camera, CTD, side-scan sonar |

Sources: "Underwater terrain mapping with a 5-DOF AUV" (NISCPR IJMS 43(1)
106-110); "AUV-150 Development and Sea Trials"; "Autonomous Underwater Vehicle
for 150 m Depth — Development Phases"; navaldrones.com AUV-150; Jane's CMERI
coverage. Speed/mission figures vary slightly between sources — representative.

## Fidelity (honest)
- **Autopilot:** real AUV-150 ran a custom indigenous controller; this twin uses
  **ArduSub** to test the MAVLink/autopilot attack surface. Command-
  authentication findings are **firmware-accurate**.
- **Hull/physics:** represented by the **BlueROV2** Gazebo body (multi-thruster,
  vectored — closer to AUV-150's 5-thruster/5-DOF layout than a torpedo). The
  real 5-thruster geometry and hydrodynamics are documented, **not** reproduced
  → **Tier-A body**.
- **Environment:** site dataset (Kochi / Mumbai / Visakhapatnam) supplies real
  water density, sound-speed, current via `scaleup/physics/environment.py`.

## Attack applicability & expected result
| Vector | Applies? | Expected | Why |
|---|---|---|---|
| `gps_spoof` | **N/A** | — | no GPS underwater |
| `ais_spoof` | **N/A** | — | no AIS submerged |
| `c2_replay` (mode) | yes | **VULNERABLE** | ArduSub does not authenticate `SET_MODE` by default |
| `c2_replay` (RC override) | yes | **VULNERABLE** | stock `SYSID_MYGCS` honours the default GCS |
| `acoustic_spoof` | yes | **VULNERABLE** | unauthenticated ExternalNav/USBL feed walks the believed position |

## Run
```bash
MCR_SITE=visakhapatnam tools/run_vehicle.sh vehicle_twins/auv150 up
python3 tools/test_target.py --target vehicle_twins/auv150/target.json
python3 tools/report.py target_runs/auv150/<run>/verdicts.json
tools/run_vehicle.sh vehicle_twins/auv150 down
```
