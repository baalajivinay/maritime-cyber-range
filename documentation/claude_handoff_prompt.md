# Maritime Cyber Range ("Testbed") — Claude Engineer Handoff Prompt

```markdown
You are acting as a Senior Principal Maritime Cybernetics & Autonomous Systems Engineer.
You have been tasked with completing 5 major engineering upgrades to the **Maritime Cyber Resilience Testbed ("Testbed")**, an industrial-grade cyber-physical digital twin conforming to **IACS UR E26 (Rev. 1), UR E27, DNV-ST-0373, IEC 61174 (ECDIS), and IEC 62288 (Presentation)**.

---

### 1. REPOSITORY & ENVIRONMENT SETUP

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/baalajivinay/maritime-cyber-range.git
   cd maritime-cyber-range
   git checkout -b feat/claude-upgrades
   ```

2. **System Dependencies:**
   - Linux environment (Ubuntu 22.04 / 24.04 or compatible X11/Wayland display).
   - Python 3.10+ / 3.12.
   - Install requirements if not present:
     ```bash
     pip install PyQt6 pygame pymavlink pytest reportlab
     ```

3. **Running the Application:**
   ```bash
   ./run_app.sh
   ```
   *(Or with explicit display: `DISPLAY=:1 ./run_app.sh` or `python3 application/console/app.py`).*

4. **Running the Automated Test Suites:**
   - Full Integration Testbed Suite (12 Scenarios):
     ```bash
     PYTHONPATH=$PWD:$PWD/application:$PWD/communication:$PWD/attacks python3 communication/test_aggressive_debugging.py
     ```
   - Core Pytest Suite (64 unit tests):
     ```bash
     PYTHONPATH=$PWD:$PWD/application:$PWD/communication:$PWD/attacks pytest application/scaleup/tests
     ```
   - Vehicle Contract Validation (All 5 Twins):
     ```bash
     for p in interceptor_usv survey_usv mt_andaman_tug maya_auv auv150; do
       PYTHONPATH=$PWD:$PWD/application:$PWD/communication python3 communication/validate_vehicle.py "$p" || exit 1
     done
     ```

---

### 2. RIGID ARCHITECTURAL CONSTRAINTS & CODING RULES

- **Strict 5-Folder Layout:** The repository root MUST contain ONLY these 5 directories:
  1. `application/`: PyQt6 console (`console/`), 5 vehicle twin profiles (`twins/`), hydrodynamics (`scaleup/physics/`).
  2. `attacks/`: Attack execution engines, detection tripwires, scenario definitions.
  3. `communication/`: MAVLink 2.0 cryptographic signing, anti-replay sliding window, AIS authenticators, backend SITL bridges.
  4. `documentation/`: System specifications, compliance matrices, guides.
  5. `logs/`: Runtime telemetry traces, audit CSVs, and incident logs.
  *DO NOT create any new directories in the repository root or leave stray files outside.*
- **Window Title:** The main application window title MUST remain strictly **`"Testbed"`** (never rename it).
- **Core Instruments:** Retain the IMO BAM header, Gyro Compass Rose, analog Rudder Indicator (-35° to +35°), Rate of Turn (ROT), and Speed Over Ground (SOG).
- **Physics Core:** High-fidelity Thor I. Fossen 3-DOF / 6-DOF hydrodynamics engine with realistic mass, added mass, quadratic damping, rudder lag, and site environmental ocean currents.

---

### 3. THE 5 UPGRADE TASKS & DELIVERABLES

Execute the following 5 tasks in order, maintaining 100% test passing at every stage:

---

#### TASK 1: Multi-Stage Cyber Attack Campaigns & Scenario Engine (Weight: 25%)
* **Current State:** Attacks are triggered manually one-by-one via UI toggle buttons.
* **Objective:** Build a robust, schema-driven multi-stage cyber attack scenario runner.
* **Key Deliverables:**
  1. Create `attacks/scenarios/` with scenario definitions (JSON/YAML) and a player engine `attacks/scenario_runner.py`:
     - **Scenario 1: "Strait of Malacca Port Approach Ambush"**:
       - *Stage 0 (0–15s):* Normal transit underway.
       - *Stage 1 (15–35s):* Insidious sub-threshold GNSS walk-off spoofing pulling vessel off fairway.
       - *Stage 2 (35–60s):* AIS phantom collision threat injected on starboard crossing (COLREGS Rule 15).
       - *Stage 3 (60–90s):* Unauthorized C2 RC override seizing throttle and rudder near hazard.
     - **Scenario 2: "Deep Subsea AUV Sabotage"**:
       - Acoustic USBL delay-skew attack + acoustic transponder jamming.
  2. Add a **Scenario Control Bar** in the UI (`attacks/` widget or toolbar) with `Load Scenario`, `Play`, `Pause`, `Scrub Timeline`, and `Reset`.
  3. Real-time **Resilience Scoring & Evaluation**:
     - Compute Time-to-Detection (TTD), Max Cross-Track Error (XTE), and CPA Margin.
     - Export incident audit score into the PDF Compliance Certificate.

---

#### TASK 2: Expanded Maritime Bridge & OT Protocols (Weight: 20%)
* **Current State:** Covers GNSS, AIS, C2 MAVLink, and USBL acoustic spoofing.
* **Objective:** Model operational technology (OT) protocols common to integrated bridge systems (IBS) and engine rooms.
* **Key Deliverables:**
  1. **NMEA 0183 & NMEA 2000 Tampering Engine:**
     - `$SDDPT` / `$SDDBT`: Echo sounder depth spoofing (reporting false deep water to induce vessel grounding).
     - `$HEHDT`: Gyrocompass heading corruption inducing false course calculations.
     - `$VHW`: Water speed through the water (STW) falsification.
  2. **Radar / ARPA False Target Generator:**
     - Generate synthetic radar target blips and target tracking vector distortion on the ECDIS radar overlay.
  3. **Engine CAN Bus / J1939 Telemetry Sabotage:**
     - Model engine shaft RPM, torque, and cooling water overheating alarms causing engine governor limp mode.
  4. Stream all new OT messages into the `BusInspectorPanel` with cryptographic integrity flags (`VALID`, `CORRUPTED`, `UNAUTHENTICATED`).

---

#### TASK 3: Autonomous Defense & Failover Autopilot (Weight: 25%)
* **Current State:** Tripwires detect attacks (EKF3 innovation monitoring, AIS station validation, HMAC verification), but mitigation is passive.
* **Objective:** Implement active autonomous fail-safe and countermeasure behaviors.
* **Key Deliverables:**
  1. **Dynamic Sensor Fusion Failover:**
     - If GNSS spoofing is tripped (EKF3 innovation $> 3.5\sigma$ or sudden drift):
       - Autonomously isolate GNSS sensor.
       - Seamlessly fall back to Doppler Velocity Log (DVL) + Dead Reckoning (DR) + Acoustic USBL positioning.
       - Alert BAM banner to `"DEFENSE: GNSS ISOLATED — SENSOR FAILOVER ACTIVE"`.
  2. **COLREGS Verification Gate:**
     - Before executing evasive maneuvers for an AIS target, cross-correlate contact bearing and distance against radar/optical sensors.
     - If contact exists only in AIS and not in radar (phantom ghost), maintain course, log IEC 62320-1 warning, and suppress false evasion.
  3. **Failsafe Actuator Quarantine & Loiter:**
     - If MAVLink 2.0 HMAC verification fails or RC override anomaly occurs:
       - Instantly sever hijacked control channel.
       - Command autonomous emergency dynamic positioning (loiter / station-keeping circle).

---

#### TASK 4: Tactical ECDIS Chart Enrichment & IHO S-52 / S-57 Symbology (Weight: 15%)
* **Current State:** 2D canvas with navigable fairway, grid lines, own-ship vectors, waypoint reticle, and contact icons.
* **Objective:** Enrich chart display to match commercial ECDIS workstations (Kongsberg K-Bridge, Furuno ECDIS).
* **Key Deliverables:**
  1. **Multi-Waypoint Route Planning & Execution:**
     - Click to plot sequential route legs (`WP-01` $\to$ `WP-02` $\to$ `WP-03`).
     - Display Route Table showing leg distances, true courses, cross-track error (XTE) limit lines, and turn radius circles.
  2. **IHO S-52 Symbology:**
     - Lateral buoyage (Port red cans, Starboard green cones).
     - Cardinal marks (North, East, South, West marks).
     - Lighthouses / Sector lights with nominal range arcs.
     - Bathymetric depth contours (safety contour, shallow water shading).
  3. **Color Palette Modes (IEC 62288):**
     - Add Day, Dusk, and Night display themes with high contrast and dark adaptation.

---

#### TASK 5: Harbor Traffic & Background Merchant Fleet (Weight: 15%)
* **Current State:** 1 own-ship vessel against 1 injected AIS ghost.
* **Objective:** Introduce realistic dynamic multi-vessel marine traffic corridors.
* **Key Deliverables:**
  1. Simulate 5–8 background merchant vessels (cargo ships, pilot boats, passenger ferries) traversing Traffic Separation Schemes (TSS) in Kochi Port, Mumbai Harbour, and Visakhapatnam.
  2. Dynamic COLREGS Multi-Contact Autopilot:
     - Own-ship autopilot actively monitors all AIS/radar targets.
     - Calculates CPA/TCPA for every contact simultaneously.
     - Automatically applies COLREGS Rules 8, 14, 15, and 16 when multiple crossing vessels are encountered simultaneously.

---

### 4. ACCEPTANCE CRITERIA & HANDOFF CHECKLIST

Before concluding your work and pushing back to GitHub:
- [ ] `./run_app.sh` launches cleanly without errors or thread lockups on Linux.
- [ ] Window Title is verified to be strictly `"Testbed"`.
- [ ] All 12 scenarios in `communication/test_aggressive_debugging.py` PASS.
- [ ] All pytest test suites in `application/scaleup/tests` PASS.
- [ ] All 5 vehicle twin contracts in `communication/validate_vehicle.py` PASS.
- [ ] Add new automated tests verifying the Scenario Engine (Task 1), OT Protocols (Task 2), and Autonomous Defense (Task 3).
- [ ] Commit all changes cleanly using conventional commit syntax (e.g. `feat(scenarios): ...`, `feat(protocols): ...`).
- [ ] Push to `origin feat/claude-upgrades` (or `origin feat/upscale`).
```
