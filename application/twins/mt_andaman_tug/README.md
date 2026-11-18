# mt_andaman_tug — 30m Autonomous Harbour Tug Digital Twin

A digital twin of the **MT Andaman**, an active 30-metre harbour tugboat operating in **Mumbai Harbour**, retrofitted and certified for **IRS Degree 4 Maritime Autonomy to COLREGs** by the **Indian Register of Shipping (IRS)** in collaboration with **Mazagon Dock Shipbuilders Limited (MDL)** and **Robosys Automation & Robotics Pvt. Ltd.**.

## Real Vehicle Class — Published Naval Architecture Data
| Marine Architectural Property | Engineering Value | Operational Meaning |
|---|---|---|
| **Hull Form** | Displacement Workboat / Harbour Tug | Deep round-bilge steel hull with heavy bow push-knees |
| **Length Overall (LOA)** | 30.0 m | Total length of the vessel from stem to stern |
| **Beam Overall (B)** | 9.0 m | Maximum breadth of the hull; governs transverse stability |
| **Draft (T)** | 3.2 m | Depth of keel below waterline; limits navigation in shallow harbour channels |
| **Displacement ($\Delta$)** | ~300 metric tonnes | Total mass of water displaced by the floating hull |
| **Bollard Pull** | ~42 tonnes | Continuous static pulling force at zero knots forward speed |
| **Cruising Speed** | 10.7 knots (~5.5 m/s) | Economic transit speed in harbour channels |
| **Maximum Speed** | 12.2 knots (~6.3 m/s) | Maximum speed ahead under full engine power |
| **Turning Diameter** | ~35.0 m | Diameter of turning circle using Azimuth Stern Drive (ASD) steering |
| **Autonomy Stack** | Robosys Voyager AI | IRS Degree 4 autonomous decision-making & COLREGs avoidance |
| **Operating Site** | Mumbai Harbour (`[18.92, 72.80]`) | Western Naval Command / Mazagon Dock approaches |

Sources: Indian Register of Shipping (IRS) Official Press Release (May 2024); Mazagon Dock Shipbuilders Ltd (MDL) Autonomy Demonstration Notices; Robosys Automation Global Autonomy Case Studies.

## RF Spectrum & Communications Architecture
| Link / Sensor | Operating Frequency | Protocol / Signal Type |
|---|---|---|
| **GNSS Satellite** | GPS L1 (1575.42 MHz) / L2 (1227.60 MHz) + NavIC L5 (1176.45 MHz) | CDMA BPSK / NMEA 0183 (`$GPGGA`, `$GPRMC`) |
| **AIS Class A** | VHF Channel 87B (161.975 MHz) & Channel 88B (162.025 MHz) | SOTDMA GMSK 9600 bps (ITU-R M.1371) |
| **Remote Control Centre (RCC)** | Tactical UHF (868 MHz) / COFDM IP Radio (2.4 GHz) | Serialized UDP Telemetry & MAVLink v2 |
| **Marine Navigation Radar** | Marine X-Band (9.41 GHz) | Pulse Doppler primary echoes |

## Fidelity (Honest)
- **Autopilot:** The real vessel runs Robosys Voyager AI interfacing with dual-redundant commercial bridge electronics. In this testbed, the vehicle stack is exercised against ArduRover in boat mode with heavy-displacement ASD skid-steer tuning (`tug.parm`) to evaluate standard firmware and MAVLink attack surfaces.
- **Physics Engine:** Evaluated in Gazebo Harmonic with mass, inertia, and hydrodynamics calibrated to a 30m displacement hull, set against the real bathymetry and reversing tidal currents (0.6 m/s) of Mumbai Harbour (`scaleup/sites/data/mumbai.json`).
- **MMSI:** `419000888` uses India's Maritime Identification Digit (MID 419) allocated for commercial harbour craft.

## Attack Applicability & Expected Resilience Results
| Attack Vector | Frequency / Layer | Applies? | Resilience Assessment | Explanation of Vulnerability & Reaction |
|---|---|---|---|---|
| `gps_spoof` | 1575.42 MHz (L1) | Yes | **VULNERABLE without CUSUM / RESILIENT with CUSUM** | Stock autopilot blindly tracks the spoofed lateral drift. With CUSUM innovation monitoring enabled, the residual $r_k$ exceeds threshold $h=4.2\sigma$, rejecting the GPS fix and reverting to dead reckoning. |
| `ais_spoof` | 161.975 MHz (VHF) | Yes | **DETECTED on Wire (N/A to raw autopilot)** | Autopilot requires an external bridge/ECDIS module to execute COLREGs evasive maneuvers. The injected ghost vessel (MMSI `419000999`) is flagged by cross-referencing with X-band radar returns. |
| `c2_replay` | 868.0 MHz (UHF) | Yes | **VULNERABLE (Unauthenticated MAVLink)** | An unauthorized `SET_MODE: HOLD` or RC channel override freezes propulsion unless cryptographically authenticated tokens or physical heartbeat dead-man timers are enforced. |

## Run
```bash
MCR_SITE=mumbai tools/run_vehicle.sh vehicle_twins/mt_andaman_tug up
python3 tools/test_target.py --target vehicle_twins/mt_andaman_tug/target.json
python3 tools/report.py target_runs/mt_andaman_tug/<run>/verdicts.json
tools/run_vehicle.sh vehicle_twins/mt_andaman_tug down
```
