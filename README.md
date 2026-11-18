# Autonomous Maritime Cyber Range & Certification Testbed

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6_Tactical_ECDIS-41CD52?style=flat-square&logo=qt&logoColor=white)](https://riverbankcomputing.com/software/pyqt/)
[![ArduPilot](https://img.shields.io/badge/ArduPilot-SITL%2FMAVLink_2-CC2936?style=flat-square)](https://ardupilot.org/)
[![Standards](https://img.shields.io/badge/Conformance-IACS_UR_E26%2FE27_%7C_IEC_62288-0052CC?style=flat-square)](https://iacs.org.uk/)
[![Linux](https://img.shields.io/badge/Platform-Linux_x86__64-FCC624?style=flat-square&logo=linux&logoColor=black)](https://kernel.org/)

An industrial-grade **Software-in-the-Loop (SITL) Digital Twin & Cyber-Physical Resilience Testbed** for Unmanned Surface Vessels (USVs) and Autonomous Underwater Vehicles (AUVs), engineered to verify compliance against mandatory **IACS Unified Requirements (UR) E26 / E27** and **DNV-ST-0373** standards.

The platform provides a type-approved tactical human-machine interface (IEC 62288 Conning Information Display + IEC 61174 2D Vector ECDIS), production autopilot SIL sensor fusion (24-state EKF3), deterministic cyber-physical fault injection (GNSS spoofing, AIS ghost vessels, MAVLink C2 hijack, and acoustic USBL disruption), real-time Kalman innovation residual tracking, and automated one-click PDF audit certificate generation for classification surveyors.

---

## Tactical Marine Workstation Showcase

<p align="center">
  <img src="screenshots/mcr_tactical_testbed_v2.png" width="98%" alt="Maritime Cyber Range Tactical Testbed Workstation" />
</p>

---

## Workstation Architecture & Standards Conformance

The testbed operates across four integrated functional layers:

1. **Bridge Alert Management & Conning Workstation (`mcr_console/widgets/`):**
   * **BAM Header (IEC 62288):** Standardized multi-status alert banner with prioritized Alarm / Warning / Normal states, vessel twin selector, and mission lifecycle controls.
   * **Conning Information Display (CID):** High-contrast gyro compass rose, Rate-of-Turn (ROT) meter, dual-rudder deflection gauge, Speed Over Ground (SOG), and propulsion telemetry.
   * **Tactical 2D Vector Nautical Chart (ECDIS - IEC 61174):** Real-time S-57 nautical chart showing bathymetry fairway, lateral navigational buoys, true own-ship ground truth vs. autopilot believed ghost position, dynamic drift divergence vector (`Δpos`), and interactive click-to-guide waypoint routing.
2. **Cyber-Physical Resilience Test Suite (`attacks/` & `mcr_console/widgets/attack_panel.py`):**
   * Pre-configured IACS UR E26 / UR E27 test cases (`MCR-SEC-01` to `MCR-SEC-04`) with live walk-off drift rate and power ratio parameter sliders.
   * Instant fail-safe trigger and autonomous containment logging.
3. **Real-Time Innovation Anomaly Filter (`detection/` & `mcr_console/widgets/telemetry_graph.py`):**
   * Live scrolling oscilloscope tracking the Extended Kalman Filter innovation residual $\nu_k$ against Amber Warning ($3.0\text{ m}$) and Red Failsafe ($8.0\text{ m}$) statistical tripwires.
4. **OT Fieldbus Inspector & One-Click Audit Generator (`mcr_console/report_generator.py`):**
   * Real-time Wireshark-style stream of NMEA 0183 (`$GPRMC`, `$GPGGA`, `$AIVDM`) and MAVLink 2 frames with invalid checksum and kinematic violation flags.
   * One-click export of formal **IACS UR E26 Type-Approval PDF Audit Certificates** with cryptographic SHA-256 seals.

---

## 🚀 Quick Start: Running the Application

### Launching the Tactical Console

```bash
# Launch the primary Tactical Conning & Cyber Testbed Workstation
./run_app.sh        # Or: tools/app.sh
```

### Operator Workflow:
1. **Mission Setup:** Select the test harbour (**Mumbai**, **Kochi**, or **Visakhapatnam**) and choose the vessel digital twin (e.g., **MT Andaman Tug**).
2. **Start Mission:** Click **BOOT SITL & TESTBED**. The application initializes the physics and connects to the ArduPilot SIL core.
3. **Arm & Navigate:** Click **ARM PROPULSION**, then left-click on the 2D nautical chart to assign dynamic destination waypoints in `GUIDED` mode.
4. **Execute Cyber Resilience Attack:** Select a test case (e.g., `MCR-SEC-01: GNSS Walk-off Spoof`), adjust the drift rate slider, and click **⚡ INJECT ATTACK**.
5. **Observe Containment:** Watch the ghost vessel diverge on the chart, observe the red tripwire breach on the EKF3 innovation graph, and inspect the flagged NMEA sentences in the fieldbus log.
6. **Export Evidence:** Click **📄 EXPORT CLASS AUDIT REPORT (PDF)** to generate the formal compliance certificate.

---

## 🚢 Calibrated Vehicle Twins

| Vehicle Twin | Domain | Physics Engine | Dynamics & Role |
| :--- | :--- | :--- | :--- |
| **Fast Interceptor USV** | Surface | Gazebo DART | Monohull planing craft, twin waterjets, high-speed patrol ($\sim 30\text{ knots}$). |
| **Coastal Survey USV** | Surface | Gazebo DART | Twin-demihull catamaran, high roll stability for hydrographic sonar survey. |
| **Maya AUV** | Subsurface | Stonefish | Torpedo-class autonomous submersible with 3D waypoint following. |
| **AUV-150** | Subsurface | Stonefish | Deep-rated survey submersible operating under closed-loop depth-hold control. |

---

## 🌊 Calibrated Naval Harbors

Each geographical test harbor reproduces cited Indian regional oceanography:

* **Kochi Naval Base (Littoral):** Water density $1022.4\text{ kg/m}^3$, tidal current $0.35\text{ m/s}$ ($160^\circ$), shallow-water acoustic multipath.
* **Mumbai Offshore (Shipping Corridor):** Water density $1022.9\text{ kg/m}^3$, tidal current $0.60\text{ m/s}$ ($20^\circ$), high-density AIS traffic.
* **Visakhapatnam (Eastern Fleet Basin):** Water density $1020.5\text{ kg/m}^3$, tidal current $0.45\text{ m/s}$ ($40^\circ$), deep-water approaches.

---

## 📁 Repository Structure

```
maritime-cyber-range/
├── godot_app/          # Godot 4 3D tactical viewer (world.gd, shaders, assets)
├── tools/              # Launchers (tools/app.sh, godot_relay.py, teardown_all.sh)
├── vehicle_twins/      # Parameters & configurations for all 4 vehicle models
├── attacks/            # Cyber-physical attack injection suite (GPS, AIS, C2, Acoustic)
├── detection/          # Real-time statistical anomaly detectors (CUSUM, Kinematic)
├── sim_config/         # Gazebo worlds, SDF vehicle models & hydrodynamic plugins
├── stonefish/          # Stonefish 6-DOF hydrodynamics bridge & scenario definitions
├── nodes/              # Backend MAVLink telemetry bridges & AIS avoidance logic
├── scaleup/            # Oceanographic site definitions, acoustic physics & unit tests
├── screenshots/        # High-resolution 3D app screenshots & architecture diagram
└── docs/               # Detailed technical documentation & run guides
```

---

## 🧪 Running the Verification Test Suite

Run the full automated physics, adversarial, and detection test suite:

```bash
python3 -m pytest scaleup/tests/
```
*(All 58 test suites pass in sub-second execution verifying acoustic latency, CUSUM drift detection, hydrodynamic drag, and schema parity).*

---

## 👤 Author

**Vinaybaalaji PNS** (CB.SC.U4CYS24061)  
Department of TIFAC-CORE in Cyber Security  
Amrita Vishwa Vidyapeetham, Coimbatore  
GitHub: [@baalajivinay](https://github.com/baalajivinay)
