# maya_auv — CSIR-NIO "Maya" AUV digital twin

A digital twin of the **Maya** small Autonomous Underwater Vehicle, built by the
**CSIR National Institute of Oceanography (NIO), Goa** (in collaboration with the
University of Porto). This is **one real Indian AUV replicated from published
specifications** — not an artificial "vulnerable/resilient" variant. You test it
and read the result; the posture it shows is the stock as-fielded ArduSub-class
command-link configuration.

## Real vehicle — published specifications
| Property | Value | Notes |
|---|---|---|
| Hull | torpedo, flooded-section | single aft thruster |
| Length | ~1.7 m | (academic papers also cite 1.24 m for a sub-section) |
| Diameter | 0.234 m | |
| Mass (air) | ~54–55 kg | foam jacket for buoyancy trim |
| Depth rating | 200 m | |
| Nominal speed | ~1.2–1.5 m/s | |
| Endurance | ~7.2 h | |
| Actuation | 1 aft thruster + 2 stern planes + 2 rudders | |
| Positioning | INS/DVL + acoustic (USBL/LBL); GPS only at surface | |

Sources: CSIR-NIO / India S&T technology listing; "The small Maya AUV — initial
field results" and "Mechanical design and development aspects of a small AUV —
Maya"; Wikipedia "Maya AUV India". Length/speed differ between sources — treat as
representative, not certified.

## Fidelity (honest)
- **Autopilot:** the real Maya used a custom MOOS-IvP/DSPIC controller. This twin
  runs **ArduSub** because the range tests the MAVLink/autopilot attack surface.
  C2 / command-authentication findings are **firmware-accurate**.
- **Hull/physics:** represented by the **REMUS-100** Gazebo body (nearest
  small-torpedo-AUV model). Maya's real hydrodynamic coefficients are documented
  above, **not** reproduced in the SDF → **Tier-A body**. Divergence magnitudes
  are representative; the *vulnerability logic* is not affected by hull fidelity.
- **Environment:** the test **site** (Kochi / Mumbai / Visakhapatnam) supplies the
  real water density, sound-speed, current and sea-state via
  `scaleup/physics/environment.py`. Swap a site's data block for a measured CTD
  cast to climb to Tier B.

## Attack applicability & expected result
| Vector | Applies? | Expected | Why |
|---|---|---|---|
| `gps_spoof` | **N/A** | — | no GPS underwater (RF can't penetrate water) |
| `ais_spoof` | **N/A** | — | no AIS transponder submerged |
| `c2_replay` (mode) | yes | **VULNERABLE** | ArduSub does not authenticate `SET_MODE` by default |
| `c2_replay` (RC override) | yes | **VULNERABLE** | stock `SYSID_MYGCS` honours the default GCS |
| `acoustic_spoof` | yes | **VULNERABLE** | ExternalNav/USBL feed is unauthenticated → believed position walks off |

## Run
```bash
MCR_SITE=kochi tools/run_vehicle.sh vehicle_twins/maya_auv up
python3 tools/test_target.py --target vehicle_twins/maya_auv/target.json
python3 tools/report.py target_runs/maya_auv/<run>/verdicts.json   # layman report
tools/run_vehicle.sh vehicle_twins/maya_auv down
```
