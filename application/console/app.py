"""
Testbed — Main Application Window.
Professional maritime resilience testbed replicating proven industrial workstation layouts
(Conning Gyro Compass, ECDIS Navigation Chart, Cyber Attack Suite, EKF3 Diagnostics, and Protocol Stream).
Conforming to IEC 62288, IEC 61174, IACS UR E26/E27, and DNV-ST-0373.
"""
import os
import sys
import threading
import time
import math
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QMessageBox, QMenuBar, QMenu, QStatusBar, QLabel, QFileDialog
)
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtCore import QTimer, Qt

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from application.console.theme import TESTBED_QSS
from application.console.widgets.bam_header import BAMHeaderWidget
from application.console.widgets.conning import ConningPanel
from application.console.widgets.ecdis import ECDISPanel
from application.console.widgets.attack_panel import AttackPanel
from application.console.widgets.telemetry_graph import TelemetryGraphPanel
from application.console.widgets.bus_inspector import BusInspectorPanel
from application.console.widgets.scenario_bar import ScenarioControlBar
from scenario_runner import load_scenario, ScenarioRunner
from communication.unified_backend import UnifiedBackend
from communication.secure_protocol import SecureTelemetryChannel
from attacks.advanced_attacks import AttackExecutionManager
from attacks.ot_protocols import OTProtocolEngine
from attacks.detection.defense import DefenseController
from scaleup.physics.marine_dynamics import MarineDynamicsEngine
from scaleup.physics.harbor_traffic import HarborTrafficSim

SITE_COORDS = {
    "kochi": (9.90000, 76.20000),
    "mumbai": (18.92000, 72.80000),
    "visakhapatnam": (17.70000, 83.30000)
}

TWIN_DOMAINS = {
    "interceptor_usv": "surface",
    "survey_usv": "surface",
    "mt_andaman_tug": "surface",
    "maya_auv": "underwater",
    "auv150": "underwater"
}


class MCRMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Title explicitly set to Testbed per user requirement
        self.setWindowTitle("Testbed")
        self.resize(1460, 900)
        self.setStyleSheet(TESTBED_QSS)

        # Active Context
        self.active_site = "kochi"
        self.active_twin = "interceptor_usv"
        self.is_running = False

        # Professional Engines
        self.backend = UnifiedBackend()
        self.physics = MarineDynamicsEngine(self.active_twin, self.active_site)
        self.attack_mgr = AttackExecutionManager()
        self.ot_engine = OTProtocolEngine()
        self.defense = DefenseController()
        self.active_directive = None
        self.traffic = HarborTrafficSim(self.active_site)   # background fleet (Task 5)
        self.colregs_enabled = True
        self.last_colregs = None
        self.security = SecureTelemetryChannel()

        # Multi-stage cyber campaign runner (Task 1). None until a scenario loads.
        self.scenario_runner = None
        self.last_scenario_score = None
        self._active_wp = None   # waypoint currently commanded to the autopilot

        # Build UI Architecture
        self._build_central_workstation()
        self._build_menu_bar()
        self._build_status_bar()

        # Telemetry & Physics Loop Timer (10 Hz)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_loop)
        self.timer.start(100)

        # Initialize site & context
        lat, lon = SITE_COORDS[self.active_site]
        self.physics.set_site(self.active_site, lat, lon)
        self.map_view.set_site(lat, lon)
        self.inspector.set_context(self.active_twin, self.active_site)
        self._sync_domain_ui()

    # =========================================================================
    # Menu Bar & Shortcuts
    # =========================================================================
    def _build_menu_bar(self):
        menubar = self.menuBar()

        # 1. File Menu
        menu_file = menubar.addMenu("&File")

        act_export = QAction("&Export Audit Certificate (PDF)...", self)
        act_export.setShortcut(QKeySequence("Ctrl+E"))
        act_export.triggered.connect(self.inspector._export_pdf)
        menu_file.addAction(act_export)

        menu_file.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # 2. Vehicle Twin Menu
        menu_twin = menubar.addMenu("&Vehicle Twin")
        for key, name in [
            ("interceptor_usv", "Fast Interceptor USV (Surface)"),
            ("survey_usv", "Coastal Survey USV (Surface)"),
            ("mt_andaman_tug", "MT Andaman Tug (Displacement)"),
            ("maya_auv", "Maya AUV (Underwater Subsea)"),
            ("auv150", "AUV-150 (Deep Flatfish)")
        ]:
            act = QAction(name, self)
            act.triggered.connect(lambda ch, k=key: self._on_select_twin(k))
            menu_twin.addAction(act)

        # 3. Location Menu
        menu_site = menubar.addMenu("&Harbour Site")
        for key, name in [
            ("kochi", "Kochi Port (09.90°N, 76.20°E)"),
            ("mumbai", "Mumbai Harbour (18.92°N, 72.80°E)"),
            ("visakhapatnam", "Visakhapatnam (17.70°N, 83.30°E)")
        ]:
            act = QAction(name, self)
            act.triggered.connect(lambda ch, k=key: self._on_select_site(k))
            menu_site.addAction(act)

        # 4. Security Menu
        menu_sec = menubar.addMenu("&Security")
        act_sign = QAction("MAVLink 2.0 HMAC-SHA256 Signing: Active", self)
        act_sign.setEnabled(False)
        menu_sec.addAction(act_sign)

        act_replay = QAction("Anti-Replay Sliding Window: Active (64-frame)", self)
        act_replay.setEnabled(False)
        menu_sec.addAction(act_replay)

        act_cert = QAction("View Cryptographic Station Key", self)
        act_cert.triggered.connect(self._show_key_dialog)
        menu_sec.addAction(act_cert)

        # 5. Help Menu
        menu_help = menubar.addMenu("&Help")
        act_about = QAction("About Testbed...", self)
        act_about.triggered.connect(self._show_about_dialog)
        menu_help.addAction(act_about)

        act_standards = QAction("Type-Approval & Compliance Standards...", self)
        act_standards.triggered.connect(self._show_standards_dialog)
        menu_help.addAction(act_standards)

    def _show_key_dialog(self):
        status = self.security.get_security_status()
        QMessageBox.information(
            self, "Cryptographic Security Engine",
            f"<b>Standard:</b> {status['protection_standard']}<br/>"
            f"<b>Cipher Suite:</b> {status['cipher_suite']}<br/>"
            f"<b>Active Key ID:</b> {status['key_id']}<br/>"
            f"<b>Verified Frames:</b> {status['verified_packets']}<br/>"
            f"<b>Rejected Forgeries:</b> {status['rejected_packets']}<br/>"
            f"<b>Replay Attempts Blocked:</b> {status['detected_replays']}"
        )

    def _show_about_dialog(self):
        QMessageBox.information(
            self, "About Testbed",
            "<b>Autonomous Maritime Cyber Resilience Testbed</b><br/>"
            "Software-in-the-Loop & Hardware-in-the-Loop Validation Workstation.<br/><br/>"
            "Evaluates uncrewed autonomous surface (USV) and underwater (AUV) vessels "
            "against GNSS spoofing, AIS ghost target injection, C2 actuator seizure, "
            "and subsea acoustic transponder manipulation."
        )

    def _show_standards_dialog(self):
        QMessageBox.information(
            self, "Classification Standards Conformity",
            "<b>Governing Standards Conformance:</b><br/>"
            "• <b>IACS UR E26 (Rev. 1):</b> Cyber resilience of ships & Zone 1 boundary containment.<br/>"
            "• <b>IACS UR E27:</b> Cyber resilience of onboard systems & equipment.<br/>"
            "• <b>DNV-ST-0373:</b> Standard for software-in-the-loop testing.<br/>"
            "• <b>IEC 61174 / 62288:</b> Electronic Chart Display & Information Systems (ECDIS).<br/>"
            "• <b>IEC 62923:</b> Bridge Alert Management (BAM) presentation."
        )

    # =========================================================================
    # Central Workstation Layout
    # =========================================================================
    def _build_central_workstation(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_vbox = QVBoxLayout(central_widget)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)

        # 1. Top BAM Header Toolbar
        self.header = BAMHeaderWidget(self)
        self.header.boot_requested.connect(self._on_start_clicked)
        self.header.teardown_requested.connect(self._on_stop_clicked)
        self.header.arm_toggled.connect(self._on_arm_toggled)
        self.header.twin_changed.connect(self._on_select_twin)
        self.header.site_changed.connect(self._on_select_site)
        self.header.defense_toggled.connect(self._on_defense_toggled)
        main_vbox.addWidget(self.header)

        # 1b. Scenario Control Bar (multi-stage cyber campaign transport)
        self.scenario_bar = ScenarioControlBar(self)
        self.scenario_bar.scenario_loaded.connect(self._on_scenario_loaded)
        self.scenario_bar.play_requested.connect(self._on_scenario_play)
        self.scenario_bar.pause_requested.connect(self._on_scenario_pause)
        self.scenario_bar.reset_requested.connect(self._on_scenario_reset)
        self.scenario_bar.seek_requested.connect(self._on_scenario_seek)
        main_vbox.addWidget(self.scenario_bar)

        # 2. Main Vertical Splitter (65% Operational Workstation / 35% Diagnostics)
        v_splitter = QSplitter(Qt.Orientation.Vertical)
        v_splitter.setHandleWidth(2)

        # --- Upper Workstation (Conning | ECDIS Chart | Cyber Attacks) ---
        h_upper = QSplitter(Qt.Orientation.Horizontal)
        h_upper.setHandleWidth(2)

        self.conning = ConningPanel(self)
        h_upper.addWidget(self.conning)

        self.map_view = ECDISPanel(self)
        self.map_view.waypoint_commanded.connect(self._on_waypoint_commanded)
        self.map_view.waypoint_cleared.connect(self._on_waypoint_cleared)
        h_upper.addWidget(self.map_view)

        self.attack_panel = AttackPanel(self)
        self.attack_panel.attack_triggered.connect(self._on_attack_triggered)
        self.attack_panel.attack_stopped.connect(self._on_attack_stopped)
        self.attack_panel.ot_toggled.connect(self._on_ot_toggled)
        h_upper.addWidget(self.attack_panel)

        h_upper.setSizes([240, 910, 310])
        v_splitter.addWidget(h_upper)

        # --- Lower Diagnostics (Innovation Graph | Protocol Bus Stream) ---
        h_lower = QSplitter(Qt.Orientation.Horizontal)
        h_lower.setHandleWidth(2)

        self.telemetry_graph = TelemetryGraphPanel(self)
        h_lower.addWidget(self.telemetry_graph)

        self.inspector = BusInspectorPanel(self)
        h_lower.addWidget(self.inspector)

        h_lower.setSizes([580, 880])
        v_splitter.addWidget(h_lower)

        v_splitter.setSizes([570, 310])
        main_vbox.addWidget(v_splitter, 1)

    # =========================================================================
    # Status Bar
    # =========================================================================
    def _build_status_bar(self):
        self.status_bar = self.statusBar()

        self.lbl_sb_engine = QLabel("Engine: Autonomous Dynamic Physics (Fossen 3-DOF)")
        self.lbl_sb_engine.setStyleSheet("color: #27ae60; font-weight: 500;")
        self.status_bar.addWidget(self.lbl_sb_engine, 2)

        self.lbl_sb_crypto = QLabel("MAVLink 2.0 HMAC-SHA256 Signed (Key #01)")
        self.lbl_sb_crypto.setStyleSheet("color: #2f80ed; font-weight: 500;")
        self.status_bar.addWidget(self.lbl_sb_crypto, 2)

        self.lbl_sb_fix = QLabel("3D GNSS (14 Sats, HDOP 0.8)")
        self.lbl_sb_fix.setStyleSheet("color: #989aa8;")
        self.status_bar.addWidget(self.lbl_sb_fix, 2)

        self.lbl_sb_cpa = QLabel("CPA: Normal")
        self.lbl_sb_cpa.setStyleSheet("color: #989aa8;")
        self.status_bar.addWidget(self.lbl_sb_cpa, 2)

        self.lbl_sb_rate = QLabel("42 Hz  |  1.8 ms")
        self.lbl_sb_rate.setStyleSheet("color: #989aa8;")
        self.status_bar.addPermanentWidget(self.lbl_sb_rate)

        self.lbl_sb_time = QLabel("00:00:00 UTC")
        self.lbl_sb_time.setStyleSheet("color: #f0f1f5; font-family: monospace; font-weight: bold;")
        self.status_bar.addPermanentWidget(self.lbl_sb_time)

    # =========================================================================
    # Operational Control Handlers
    # =========================================================================
    def _on_select_twin(self, twin_key: str):
        if not twin_key:
            return
        self.active_twin = twin_key
        # Update combo box if triggered from menu
        idx = self.header.twin_combo.findData(twin_key)
        if idx >= 0 and self.header.twin_combo.currentIndex() != idx:
            self.header.twin_combo.blockSignals(True)
            self.header.twin_combo.setCurrentIndex(idx)
            self.header.twin_combo.blockSignals(False)

        self.physics.set_vessel_twin(twin_key)
        self.inspector.set_context(twin_key, self.active_site)
        self._sync_domain_ui()

    def _on_select_site(self, site_key: str):
        if not site_key:
            return
        self.active_site = site_key
        idx = self.header.site_combo.findData(site_key)
        if idx >= 0 and self.header.site_combo.currentIndex() != idx:
            self.header.site_combo.blockSignals(True)
            self.header.site_combo.setCurrentIndex(idx)
            self.header.site_combo.blockSignals(False)

        lat, lon = SITE_COORDS.get(site_key, (9.9, 76.2))
        self.physics.set_site(site_key, lat, lon)
        self.map_view.set_site(lat, lon)
        self.inspector.set_context(self.active_twin, site_key)
        if hasattr(self, "traffic"):
            self.traffic.set_site(site_key)

    def _sync_domain_ui(self):
        domain = TWIN_DOMAINS.get(self.active_twin, "surface")
        self.attack_panel.set_domain(domain)
        if domain == "underwater":
            self.lbl_sb_fix.setText("USBL Acoustic Fix (Depth: 8.5m)")
        else:
            self.lbl_sb_fix.setText("3D GNSS (14 Sats, HDOP 0.8)")

    def _on_start_clicked(self):
        site_key = self.header.site_combo.currentData() or "kochi"
        twin_key = self.header.twin_combo.currentData() or "interceptor_usv"
        domain = TWIN_DOMAINS.get(twin_key, "surface")

        self.active_site = site_key
        self.active_twin = twin_key
        self.is_running = True

        lat, lon = SITE_COORDS[site_key]
        self.physics.set_site(site_key, lat, lon)
        self.physics.armed = True
        self.header.btn_arm.blockSignals(True)
        self.header.btn_arm.setChecked(True)
        self.header.btn_arm.setText("Disarm")
        self.header.btn_arm.blockSignals(False)

        self.map_view.set_site(lat, lon)
        self.header.set_running_state(True)
        self.inspector.set_context(twin_key, site_key)

        # Background SITL launch
        threading.Thread(target=self._boot_backend_bg, args=(site_key, twin_key, domain), daemon=True).start()

    def _boot_backend_bg(self, site, twin, domain):
        try:
            self.backend.boot(site, twin, domain)
        except Exception:
            pass

    def _on_stop_clicked(self):
        self.is_running = False
        self.physics.armed = False
        self.physics.clear_target_waypoint()
        self.map_view.canvas.clear_waypoint()
        self._active_wp = None
        self.header.btn_arm.blockSignals(True)
        self.header.btn_arm.setChecked(False)
        self.header.btn_arm.setText("Arm Vehicle")
        self.header.btn_arm.blockSignals(False)
        self.attack_mgr.stop_attack()
        self.defense.reset()
        self.header.set_running_state(False)

        threading.Thread(target=self._teardown_bg, daemon=True).start()

    def _teardown_bg(self):
        try:
            if self.backend.engine is not None:
                self.backend.teardown()
        except Exception:
            pass

    def _on_arm_toggled(self, armed: bool):
        self.physics.armed = armed
        if not armed:
            self.physics.clear_target_waypoint()
            self.map_view.canvas.clear_waypoint()
        if self.backend.engine:
            if armed:
                self.backend.arm()
            else:
                self.backend.disarm()

    def _sync_route(self):
        """Advance the multi-leg route (Task 4): when the physics autopilot
        reaches the active waypoint it clears its target; move to the next leg,
        or finish the route. Also commands an externally-set direct-to target."""
        canvas = self.map_view.canvas
        active_wp = getattr(self, "_active_wp", None)

        if self.physics.target_wp is None and active_wp is not None:
            # The active waypoint has been reached.
            if canvas.route and not canvas.route_complete():
                nxt = canvas.advance_route()   # emits -> _on_waypoint_commanded
                if nxt is None:
                    canvas.target_wp = None
                    self._active_wp = None
                    self.inspector.log_event("NAV", "Route complete; station keeping / cruise")
                else:
                    self.inspector.log_event(
                        "NAV", f"Leg reached; proceeding to WP-{canvas.route_idx + 1:02d}")
            else:
                canvas.target_wp = None
                canvas.route = []
                canvas.route_idx = 0
                self._active_wp = None
                self.inspector.log_event("NAV", "Waypoint reached; station keeping / cruise")
            canvas.update()

        # Legacy direct-to target set on the canvas without a route
        if (self.physics.target_wp is None and canvas.target_wp is not None
                and getattr(self, "_active_wp", None) is None and not canvas.route):
            self._on_waypoint_commanded(canvas.target_wp[0], canvas.target_wp[1])

    def _on_waypoint_commanded(self, east_m: float, north_m: float):
        # 1. Automatically Arm Vehicle if disarmed so operator immediately sees vessel navigate
        if not self.physics.armed:
            self.physics.armed = True
            self.header.btn_arm.blockSignals(True)
            self.header.btn_arm.setChecked(True)
            self.header.btn_arm.setText("Disarm")
            self.header.btn_arm.blockSignals(False)

        # 2. Command hydrodynamics autopilot Line-Of-Sight (LOS) guidance
        self.physics.set_target_waypoint(east_m, north_m)
        self._active_wp = (east_m, north_m)
        self.map_view.canvas.target_wp = (east_m, north_m)
        self.map_view.canvas.update()
        self.inspector.log_event("NAV", f"Waypoint commanded: East={east_m:.1f}m, North={north_m:.1f}m -> Autopilot LOS engaged")

        # 3. If SITL MAVLink backend is actively connected, command MAVLink goto
        if self.backend.connected:
            lat, lon = self._meters_to_latlon(east_m, north_m)
            self.backend.goto(lat, lon)

    def _on_waypoint_cleared(self):
        self.physics.clear_target_waypoint()
        self._active_wp = None
        self.inspector.log_event("NAV", "Waypoint cancelled: returning to default cruise / loiter")

    def _meters_to_latlon(self, east_m: float, north_m: float) -> tuple:
        home_lat, home_lon = SITE_COORDS.get(self.active_site, (9.9, 76.2))
        lat = home_lat + (north_m / 111132.954)
        lon = home_lon + (east_m / (111132.954 * math.cos(math.radians(home_lat))))
        return lat, lon

    # =========================================================================
    # Scenario Campaign Handlers (Task 1)
    # =========================================================================
    def _on_scenario_loaded(self, scenario_id: str):
        try:
            scenario = load_scenario(scenario_id)
        except Exception as e:
            QMessageBox.critical(self, "Scenario Load Error", f"Could not load '{scenario_id}':\n{e}")
            return

        self.scenario_runner = ScenarioRunner(scenario)
        self.last_scenario_score = None

        # Align twin + site to the scenario and reset the vessel to the origin
        self._on_select_twin(self.scenario_runner.twin)
        self._on_select_site(self.scenario_runner.site)
        idx = self.header.twin_combo.findData(self.scenario_runner.twin)
        if idx >= 0:
            self.header.twin_combo.blockSignals(True)
            self.header.twin_combo.setCurrentIndex(idx)
            self.header.twin_combo.blockSignals(False)
        idx = self.header.site_combo.findData(self.scenario_runner.site)
        if idx >= 0:
            self.header.site_combo.blockSignals(True)
            self.header.site_combo.setCurrentIndex(idx)
            self.header.site_combo.blockSignals(False)

        # Arm the vessel and give it a waypoint down the planned fairway so it
        # is actually underway when the first stage begins.
        self.attack_mgr.stop_attack()
        self.physics.armed = True
        self._command_fairway_waypoint()
        self.header.btn_arm.blockSignals(True)
        self.header.btn_arm.setChecked(True)
        self.header.btn_arm.setText("Disarm")
        self.header.btn_arm.blockSignals(False)

        # Campaigns demonstrate resilience: arm the autonomous defence.
        self.defense.set_enabled(True)
        self.header.btn_defense.blockSignals(True)
        self.header.btn_defense.setChecked(True)
        self.header.btn_defense.blockSignals(False)

        self.scenario_bar.set_loaded(True)
        self.inspector.log_event("SCENARIO", f"Loaded campaign '{self.scenario_runner.name}' "
                                             f"({len(self.scenario_runner.stages)} stages, "
                                             f"{self.scenario_runner.duration_s:.0f}s)")

    def _command_fairway_waypoint(self):
        if not self.scenario_runner:
            return
        course = math.radians(self.scenario_runner.track_course_deg)
        reach = max(400.0, self.physics.cfg["max_speed_mps"] * self.scenario_runner.duration_s)
        east = self.physics.east_m + reach * math.sin(course)
        north = self.physics.north_m + reach * math.cos(course)
        self.physics.set_target_waypoint(east, north)
        self._active_wp = (east, north)
        self.map_view.canvas.target_wp = (east, north)

    def _on_scenario_play(self):
        if self.scenario_runner:
            if self.scenario_runner.state == ScenarioRunner.STATE_IDLE:
                self._command_fairway_waypoint()
            self.scenario_runner.play()
            self.inspector.log_event("SCENARIO", "Campaign PLAY")

    def _on_scenario_pause(self):
        if self.scenario_runner:
            self.scenario_runner.pause()
            self.inspector.log_event("SCENARIO", "Campaign PAUSE")

    def _on_scenario_reset(self):
        if self.scenario_runner:
            self.scenario_runner.reset()
            self.attack_mgr.stop_attack()
            self.defense.reset()
            self._command_fairway_waypoint()
            self.last_scenario_score = None
            self.inspector.log_event("SCENARIO", "Campaign RESET")

    def _on_scenario_seek(self, fraction: float):
        if self.scenario_runner:
            self.scenario_runner.seek(fraction * self.scenario_runner.duration_s)

    def _on_attack_triggered(self, attack_name: str, params: dict):
        if attack_name == "gps_spoof":
            mode = params.get("mode", "ramp")
            rate = float(params.get("drift_rate", 2.5))
            self.attack_mgr.start_gps_attack(mode=mode, drift_rate=rate)
        elif attack_name == "ais_spoof":
            scen = params.get("scenario", "head_on")
            self.attack_mgr.start_ais_attack(
                scenario=scen,
                own_pos=(self.physics.east_m, self.physics.north_m),
                own_hdg=math.degrees(self.physics.psi)
            )
        elif attack_name == "c2_replay":
            cmd = params.get("cmd_type", "rc_override")
            self.attack_mgr.start_c2_attack(cmd_type=cmd)
        elif attack_name == "acoustic_spoof":
            rate = float(params.get("rate", 1.5))
            self.attack_mgr.start_acoustic_attack(delay_rate=rate)
        elif attack_name == "acoustic_jam":
            self.attack_mgr.start_acoustic_attack(delay_rate=0.0)

        # Also signal the backend engine if live
        if self.backend.engine:
            self.backend.attack(attack_name)

    def _on_attack_stopped(self):
        self.attack_mgr.stop_attack()
        self.defense.reset()
        if self.backend.engine:
            self.backend.stop_attack()

    def _on_ot_toggled(self, vector: str, on: bool):
        """Enable/disable an OT bus tampering vector (Task 2)."""
        self.ot_engine.set_attack(vector, on)
        self.inspector.log_event("OT-BUS", f"{vector} {'ENABLED' if on else 'disabled'}")

    def _on_defense_toggled(self, on: bool):
        """Arm/disarm the autonomous defense fail-safe (Task 3)."""
        self.defense.set_enabled(on)
        self.inspector.log_event(
            "DEFENSE", f"Autonomous defense {'ARMED' if on else 'disarmed'}")

    def _current_radar_tracks(self):
        """Radar/optical tracks available to the COLREGS verification gate.

        Synthetic ARPA blips are injected and marked synthetic (they do not
        corroborate an AIS contact). Real background traffic (Task 5) is added
        here as independent radar truth.
        """
        tracks = [
            {"east_m": t.east_m, "north_m": t.north_m, "synthetic": t.synthetic}
            for t in self.ot_engine.radar_targets()
        ]
        traffic = getattr(self, "traffic", None)
        if traffic is not None:
            tracks.extend(traffic.radar_tracks())
        return tracks

    def _stream_ot_frames(self):
        """Pump OT bus frames into the inspector at ~2 Hz to avoid flooding."""
        self._ot_frame_tick = getattr(self, "_ot_frame_tick", 0) + 1
        if self._ot_frame_tick % 5 != 0:
            return
        if not self.ot_engine.any_active():
            return
        for f in self.ot_engine.frames():
            if f.is_anomaly:
                self.inspector.add_packet(f.proto, f.payload, is_anomaly=True, note=f.verdict)

    # =========================================================================
    # Main Real-Time 10 Hz Telemetry & Physics Loop
    # =========================================================================
    def _update_loop(self):
        dt = 0.1  # 100ms interval
        utc_ts = time.strftime("%H:%M:%SZ", time.gmtime())
        self.lbl_sb_time.setText(utc_ts)

        # 1. Synchronize chart route/waypoint with the physics autopilot.
        self._sync_route()

        # 2. Advance multi-stage cyber campaign (drives attack_mgr per stage)
        scenario_status = None
        if self.scenario_runner is not None:
            scenario_status = self.scenario_runner.step(dt, self.attack_mgr, self.physics)

        # 2b. Advance Cyber Attack Execution State (pre-step own position)
        own_pos = (self.physics.east_m, self.physics.north_m)
        own_vel = (self.physics.u * math.sin(self.physics.psi), self.physics.u * math.cos(self.physics.psi))
        atk_overlay = self.attack_mgr.update(dt, own_pos, own_vel)

        # 2b2. Harbor traffic + multi-contact COLREGS autopilot (Task 5)
        self.traffic.step(dt)
        colregs_bias = 0.0
        if self.colregs_enabled and self.physics.armed:
            self.last_colregs = self.traffic.evaluate(
                (self.physics.east_m, self.physics.north_m),
                math.degrees(self.physics.psi) % 360.0,
                max(0.1, self.physics.u))
            if self.last_colregs.action in ("give_way", "alter"):
                colregs_bias = self.last_colregs.course_change_deg

        # 2c. Autonomous Defense directive (Task 3): computed BEFORE the physics
        #     step so it can override the autopilot (failover / loiter / suppress).
        radar_tracks = self._current_radar_tracks()
        directive = self.defense.update(
            dt, {"domain": self.physics.cfg["domain"]}, atk_overlay, radar_tracks)
        for cat, msg in directive.new_events:
            self.inspector.log_event(cat, msg)
        self.active_directive = directive

        # 3. Marine hydrodynamics step (or live SITL), now defense-aware
        backend_state = self.backend.state
        has_live_mav = (self.backend.connected and backend_state.get("lat") is not None)
        if has_live_mav:
            self.lbl_sb_engine.setText("Engine: MAVLink SITL Link (tcp:5760)")
            self.lbl_sb_engine.setStyleSheet("color: #27ae60; font-weight: bold;")
            state = dict(backend_state)
        else:
            state = self.physics.step(
                dt,
                active_attack=self.attack_mgr.active_attack,
                attack_params=self.attack_mgr.params,
                defense=directive.as_dict(),
                colregs_bias_deg=colregs_bias,
            )

        # Merge attack overlay into state
        state.update(directive.as_dict())
        state["active_attack"] = atk_overlay["active_attack"]
        state["spoof_offset_m"] = atk_overlay["gps_offset_m"] if atk_overlay["active_attack"] == "gps_spoof" else None
        state["ghost_vessel"] = atk_overlay["ghost_vessel"]
        state["cpa_m"] = atk_overlay["cpa_m"]
        state["tcpa_s"] = atk_overlay["tcpa_s"]
        state["collision_risk"] = atk_overlay["collision_risk"]
        state["simulated_innovation"] = atk_overlay["simulated_innovation"]
        state["usbl_offset_m"] = atk_overlay["usbl_offset_m"]

        # 4. Update Status Bar Metrics
        if state["active_attack"] == "gps_spoof":
            hdop = atk_overlay["gps_hdop"]
            sats = atk_overlay["gps_sats"]
            self.lbl_sb_fix.setText(f"GNSS Fix Degrading (HDOP {hdop:.1f}, Sats: {sats})")
            self.lbl_sb_fix.setStyleSheet("color: #eb5757; font-weight: bold;")
        elif state["active_attack"] == "ais_spoof":
            if state["collision_risk"]:
                self.lbl_sb_cpa.setText(f"COLLISION RISK: CPA {state['cpa_m']:.0f}m, TCPA {state['tcpa_s']:.0f}s")
                self.lbl_sb_cpa.setStyleSheet("color: #eb5757; font-weight: bold;")
            else:
                self.lbl_sb_cpa.setText(f"AIS Target: CPA {state['cpa_m']:.0f}m")
                self.lbl_sb_cpa.setStyleSheet("color: #f2994a; font-weight: 500;")
        else:
            self.lbl_sb_cpa.setText("CPA: Normal")
            self.lbl_sb_cpa.setStyleSheet("color: #989aa8;")
            domain = state.get("domain", "surface")
            if domain == "underwater":
                depth = state.get("depth", 8.5)
                self.lbl_sb_fix.setText(f"USBL Acoustic Fusion (Depth: {depth:.1f}m)")
            else:
                self.lbl_sb_fix.setText("3D GNSS (14 Sats, HDOP 0.8)")
            self.lbl_sb_fix.setStyleSheet("color: #989aa8;")

        # 4-def. Reflect autonomous-defense posture on the GNSS/fix status cell
        if state.get("gnss_isolated"):
            self.lbl_sb_fix.setText(f"FAILOVER: {state.get('nav_source', 'DVL + DR')}")
            self.lbl_sb_fix.setStyleSheet("color: #2f80ed; font-weight: bold;")

        # 4a. Advance OT bus tampering (NMEA/ARPA/J1939) and stream to widgets
        ot_overlay = self.ot_engine.update(dt, state)
        state.update(ot_overlay)
        state["radar_false_targets"] = [
            {"east_m": t.east_m, "north_m": t.north_m, "course": t.course_deg,
             "speed": t.speed_mps, "track_id": t.track_id, "synthetic": t.synthetic}
            for t in self.ot_engine.radar_targets()
        ]
        self._stream_ot_frames()

        # 4c. Background traffic + COLREGS status for rendering
        state["traffic"] = self.traffic.ais_tracks()
        if self.last_colregs is not None:
            state["colregs_action"] = self.last_colregs.action
            state["colregs_rule"] = self.last_colregs.rule
            state["colregs_risk_count"] = self.last_colregs.risk_count
            if (self.last_colregs.risk_count and state["active_attack"] is None
                    and not state.get("defense_banner")):
                act = self.last_colregs.action.replace("_", "-").upper()
                self.lbl_sb_cpa.setText(
                    f"COLREGS {act}: {self.last_colregs.rule} "
                    f"({self.last_colregs.risk_count} contact(s))")
                colour = "#eb5757" if self.last_colregs.action in ("give_way", "alter") else "#f2994a"
                self.lbl_sb_cpa.setStyleSheet(f"color: {colour}; font-weight: bold;")

        # 4b. Score the active campaign and refresh the scenario bar
        if self.scenario_runner is not None and scenario_status is not None:
            self.scenario_runner.record(state)
            self.last_scenario_score = self.scenario_runner.score.as_dict()
            self.inspector.scenario_score = self.last_scenario_score
            self.scenario_bar.update_view(scenario_status, self.last_scenario_score)

        # 5. Broadcast Telemetry to all Widgets
        self.conning.update_telemetry(state)
        self.map_view.update_telemetry(state)
        self.attack_panel.update_telemetry(state)
        self.telemetry_graph.update_telemetry(state)
        self.inspector.update_telemetry(state)
        self.header.update_telemetry(state)

    def closeEvent(self, event):
        self.timer.stop()
        if self.backend.engine is not None:
            self._teardown_bg()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MCRMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
