# Testbed Engineering Upgrades

This document describes five capability upgrades layered onto the Maritime
Cyber Resilience Testbed. All additions are kept inside the strict five-folder
layout (`application/`, `attacks/`, `communication/`, `documentation/`,
`logs/`), the main window title remains **`Testbed`**, and the core instrument
suite (BAM header, gyro compass rose, rudder indicator, ROT, SOG) and the
Fossen hydrodynamics engine are retained.

## 1. Multi-Stage Cyber Attack Campaigns & Scenario Engine
- `attacks/scenarios/*.json` — schema-driven campaigns:
  - **Strait of Malacca Port Approach Ambush** (normal transit → sub-threshold
    GNSS walk-off → AIS phantom starboard crossing → unauthorized C2 override).
  - **Deep Subsea AUV Sabotage** (USBL delay-skew → acoustic transponder jamming).
- `attacks/scenario_runner.py` — a Qt-free `ScenarioRunner` that drives the live
  `AttackExecutionManager` and `MarineDynamicsEngine` stage-by-stage and scores
  **resilience**: Time-to-Detection (TTD), max Cross-Track Error (XTE), and CPA
  margin, graded A–D.
- **Scenario Control Bar** (`console/widgets/scenario_bar.py`): Load / Play /
  Pause / Scrub / Reset plus a live score readout.
- The resilience evidence is exported into the PDF audit certificate.

## 2. Expanded Maritime Bridge & OT Protocols
- `attacks/ot_protocols.py` — `OTProtocolEngine`:
  - NMEA 0183/2000 tampering: echo-sounder depth (`$SDDPT`/`$SDDBT`),
    gyrocompass heading (`$HEHDT`), speed-through-water (`$VHW`).
  - Radar/ARPA false-target generator rendered on the ECDIS overlay.
  - Engine CAN / SAE J1939 sabotage (RPM/torque/coolant) with governor limp mode.
- Every frame is tagged `VALID` / `CORRUPTED` / `UNAUTHENTICATED` in the
  Bus Inspector. Toggles live in the attack panel's *Integrated Bridge / Engine
  OT Bus* group.

## 3. Autonomous Defense & Failover Autopilot
- `attacks/detection/defense.py` — `DefenseController` (armed via the header
  **Auto-Defense** toggle; auto-engaged by scenarios):
  - **Sensor-fusion failover**: innovation > 3.5σ during a positioning spoof
    isolates the primary sensor and fails over to DVL + DR (+ USBL submerged).
  - **COLREGS verification gate**: AIS contacts with no radar/optical correlation
    are classified phantom; course is held, IEC 62320-1 logged, false evasion
    suppressed.
  - **Failsafe actuator quarantine**: a C2/HMAC/RC-override anomaly severs the
    channel and commands an autonomous station-keeping loiter.

## 4. Tactical ECDIS Enrichment (IHO S-52 / S-57, IEC 62288)
- Multi-waypoint route planning with a route table (leg distance, true course,
  XTE limit, turn radius), XTE corridor lines and turn-radius circles.
- IHO S-52 symbology: IALA lateral buoyage, cardinal marks, a lighthouse with a
  nominal-range arc, and bathymetric depth contours with a safety contour and
  shallow-water shading.
- IEC 62288 **Day / Dusk / Night** palette modes.

## 5. Harbor Traffic & Background Merchant Fleet
- `application/scaleup/physics/harbor_traffic.py` — `HarborTrafficSim` spawns
  5–8 background vessels on the Traffic Separation Scheme lanes of Kochi,
  Mumbai and Visakhapatnam.
- Multi-contact COLREGS autopilot computes CPA/TCPA for every contact and
  applies Rules 8, 13, 14, 15, 16 and 17 simultaneously; a give-way obligation
  dominates when several crossings occur at once.

## Tests
New automated coverage (all under `application/scaleup/tests/`):
- `test_scenario_runner.py` — scenario engine + resilience scoring
- `test_ot_protocols.py` — NMEA / ARPA / J1939 tampering
- `test_defense.py` — autonomous failover / COLREGS gate / quarantine
- `test_ecdis_route.py` — route planning / symbology / palettes
- `test_harbor_traffic.py` — TSS traffic + multi-contact COLREGS

Run everything:
```bash
PYTHONPATH=$PWD:$PWD/application:$PWD/communication:$PWD/attacks pytest application/scaleup/tests
PYTHONPATH=$PWD:$PWD/application:$PWD/communication:$PWD/attacks python3 communication/test_aggressive_debugging.py
for p in interceptor_usv survey_usv mt_andaman_tug maya_auv auv150; do \
  PYTHONPATH=$PWD:$PWD/application:$PWD/communication python3 communication/validate_vehicle.py "$p" || exit 1; done
```
