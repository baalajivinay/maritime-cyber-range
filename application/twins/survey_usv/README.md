# survey_usv — small Indian coastal survey USV twin

A digital twin of a **small (~4–6 m) Indian autonomous hydrographic-survey USV**
— the catamaran class used for harbour-approach and coastal survey work. One of
**two Indian USVs** in this range (the other is the fast interceptor). Unlike the
AUV twins there is **no single named Indian platform with fully published specs**,
so this is a **representative** small survey USV modelled on a BlueBoat-class
differential-thrust catamaran and typical Indian coastal-survey requirements
(NIOT / academic survey programmes).

## Representative class specifications
| Property | Value | Notes |
|---|---|---|
| Hull | twin-hull catamaran | differential (skid-steer) thrust |
| Length | ~4–6 m | small, trailerable |
| Survey speed | ~1–2 kn | slow, for sonar swath quality |
| Role | harbour-approach / coastal bathymetric survey | |
| Sensors | GPS, AIS, IMU/compass, MBES/side-scan | GPS + AIS present (surface) |

Context sources: Makar-class hydrographic catamaran (Indian Navy, larger manned
class); commercial survey-USV catamarans (ME120, 2.5 m) for scale; USV-survey
design literature. Treat the figures as representative of the class, not a
certified single platform.

## Fidelity (honest)
- **Autopilot:** runs **ArduRover** to test the MAVLink/autopilot attack surface;
  command-authentication findings are **firmware-accurate**.
- **Hull/physics:** **BlueBoat** Gazebo body (small catamaran). Tier-A body.
- **Environment:** site dataset supplies real density/current/sea-state (harbour
  traffic context for AIS) via `scaleup/physics/environment.py`.
- **MMSI** `419000567` uses India's MID (419).

## Attack applicability & expected result
| Vector | Applies? | Expected | Why |
|---|---|---|---|
| `gps_spoof` (fdm_relay) | yes | **VULNERABLE** | stock EKF has no external-GPS cross-check → believed position walks off |
| `ais_spoof` | yes (**N/A to autopilot**) | detectability-only | ArduPilot doesn't consume AIS; operator/ECDIS-layer attack caught on the wire |
| `c2_replay` (mode) | yes | **VULNERABLE** | ArduRover does not authenticate `SET_MODE` by default |
| `c2_replay` (RC override) | yes | **VULNERABLE** | stock `SYSID_MYGCS` honours the default GCS |

## Run
```bash
MCR_SITE=kochi tools/run_vehicle.sh vehicle_twins/survey_usv up
python3 tools/test_target.py --target vehicle_twins/survey_usv/target.json
python3 tools/report.py target_runs/survey_usv/<run>/verdicts.json
tools/run_vehicle.sh vehicle_twins/survey_usv down
```
