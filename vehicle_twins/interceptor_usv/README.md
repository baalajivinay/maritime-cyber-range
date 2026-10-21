# interceptor_usv — Indian autonomous fast interceptor boat twin

A digital twin of an **Indian Navy autonomous Unmanned Surface Vessel (USV)**,
modelled on the real programme shape: **autonomy retrofitted onto an in-service
fast interceptor boat**. The Indian Navy's **A2NCS** (Advanced Autonomous
Navigation & Control Software, by **BEL** and the Navy's **WESEE**) has been
integrated onto a fielded fast interceptor craft and exercised in mine-
countermeasure and combat roles. This is **one real Indian USV class replicated
from published data** — not a "vulnerable/resilient" variant.

## Real vehicle class — published data
| Property | Value | Notes |
|---|---|---|
| Hull | planing monohull interceptor | Solas Marine fast interceptor class |
| Length (LOA) | ~16.3 m | |
| Top speed | ~45 kn | |
| Autonomy | A2NCS (BEL / WESEE) | retrofit onto existing craft |
| Role (autonomous) | mine countermeasures, patrol, combat support | |
| Sensors | GPS, AIS, IMU/compass, radar | GPS + AIS present (surface) |

Sources: Indian Navy USV / A2NCS reporting; Wikipedia "Solas Marine fast
interceptor boat" (16.33 m LOA, 45 kn). Exact autonomous-variant specs are not
public — treat as representative of the class.

## Fidelity (honest)
- **Autopilot:** real craft runs A2NCS, not ArduRover. This twin runs **ArduRover**
  to test the MAVLink/autopilot attack surface; command-authentication findings
  are **firmware-accurate**.
- **Hull/physics:** represented by the **CUSV** Gazebo body (nearest unmanned
  surface combatant model). Real planing-hull hydrodynamics are documented, not
  reproduced → **Tier-A body**.
- **Environment:** the test **site** supplies real density, current, sea-state and
  (for AIS/collision relevance) harbour traffic context via
  `scaleup/physics/environment.py`.
- **MMSI** `419000234` uses India's MID (419) so the own-vessel identity is a
  valid Indian ship MMSI.

## Attack applicability & expected result
| Vector | Applies? | Expected | Why |
|---|---|---|---|
| `gps_spoof` (fdm_relay) | yes | **VULNERABLE** | stock EKF has no external GPS cross-check → believed position walks off |
| `ais_spoof` | yes (**N/A to autopilot**) | detectability-only | ArduPilot doesn't consume AIS; it's an ECDIS/operator-layer attack caught on the wire |
| `c2_replay` (mode) | yes | **VULNERABLE** | ArduRover does not authenticate `SET_MODE` by default |
| `c2_replay` (RC override) | yes | **VULNERABLE** | stock `SYSID_MYGCS` honours the default GCS |

## Run
```bash
MCR_SITE=mumbai tools/run_vehicle.sh vehicle_twins/interceptor_usv up
python3 tools/test_target.py --target vehicle_twins/interceptor_usv/target.json
python3 tools/report.py target_runs/interceptor_usv/<run>/verdicts.json   # layman report
tools/run_vehicle.sh vehicle_twins/interceptor_usv down
```
