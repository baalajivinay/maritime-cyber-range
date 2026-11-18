# Upscale Roadmap — generic + real-physics

How the range grows from "an ArduPilot attack harness with good oceanography"
into a **generic maritime cyber range** with **real-world physics**. Two axes,
phased against the project's existing fidelity ladder (Tier A representative →
B measured → C trial-validated). Everything below is **additive and default-off**
(the `scaleup/` isolation contract); the frozen release path is untouched.

## Status legend
✅ built & tested · 🟡 adapter + fallback built (needs external data/HW to go live) · ⬜ planned

## Axis 1 — Generic / universal

| Item | Status | Where |
|---|---|---|
| Autopilot-agnostic backend abstraction (ArduPilot + PX4) | ✅ | `scaleup/backends/` |
| PX4 live boot | 🟡 needs PX4 SITL install | `backends/px4.py` |
| Protocol-adapter layer (MAVLink + NMEA 0183) | ✅ | `scaleup/protocols/` |
| NMEA 2000 / radar-ARPA / ECDIS adapters | ⬜ | `scaleup/protocols/` |
| Twin registry + `twin init` scaffolder | ✅ | `scaleup/twins/` |
| Multi-vehicle / swarm scenarios | ⬜ (unlocked by the bus abstraction) | — |
| Multi-framework compliance mapping (IACS/IMO/IEC 62443/NIST/MITRE ATT&CK ICS/DNV) | ✅ | `scaleup/compliance/` |
| Range-as-a-service REST API | ✅ | `scaleup/platform/api.py` |
| Parallel twins on Kubernetes | ⬜ | — |

## Axis 2 — Real-life physics

| Item | Status | Where |
|---|---|---|
| Sensor error models (GNSS multipath, IMU bias/ARW, DVL dropout, mag) | ✅ | `scaleup/physics/sensors.py` |
| Sea state (JONSWAP spectrum + wave disturbance) | ✅ | `scaleup/physics/seastate.py` |
| Harmonic tidal currents (flood/ebb) | ✅ | `scaleup/physics/tides.py` |
| Multipath acoustics (image-method) + Bellhop adapter | ✅ / 🟡 Bellhop needs the binary | `scaleup/physics/acoustics_bellhop.py` |
| Ocean-profile ingest (CTD/WOA/INCOIS CSV → exact eqns) | ✅ (CSV) | `scaleup/physics/ingest.py` |
| Bathymetry (CSV grid ✅ · GEBCO NetCDF 🟡 needs netCDF4) | ✅ / 🟡 | `scaleup/physics/bathymetry.py` |
| Real AIS traffic ingest (file ✅ · live UDP ✅) | ✅ | `scaleup/physics/ais_feed.py` |
| Wiring sea-state/tide/profile into the live Gazebo stack | ⬜ (models ready; injector like `inject_current.py`) | — |
| Hardware-in-the-loop — ESP32 C2 node + NMEA injector | ✅ firmware | `hardware/` |
| HIL — real Pixhawk; SDR RF GNSS/AIS (shielded) | ⬜ | `hardware/README.md` |
| Tier-C trial-data validation (NSTL/NPOL partnership) | ⬜ | — |

## Suggested sequencing
1. **Near-term (data/integration):** PX4 live backend · GEBCO CSV → real grounding · CTD profile → SSP-driven acoustics · live AIS feed into the detectors.
2. **Mid-term (architecture):** wire sea-state/tide into the Gazebo injector · NMEA 2000 + ECDIS adapters · multi-vehicle scenarios · Kubernetes parallelism.
3. **Moonshot:** full HIL rig (Pixhawk + shielded SDR) and the Tier-C trial-data partnership.
