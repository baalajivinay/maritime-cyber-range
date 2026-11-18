"""
Testbed — Main Application Window.
Clean, modern, human-engineered desktop testbed for maritime autonomous vehicle cyber resilience.
"""
import os
import sys
import threading
import time
import math
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QMessageBox
)
from PyQt6.QtCore import QTimer, Qt

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from application.console.theme import CLEAN_QSS
from application.console.widgets.bam_header import BAMHeaderWidget
from application.console.widgets.conning import ConningPanel
from application.console.widgets.ecdis import ECDISPanel
from application.console.widgets.attack_panel import AttackPanel
from application.console.widgets.telemetry_graph import TelemetryGraphPanel
from application.console.widgets.bus_inspector import BusInspectorPanel
from communication.unified_backend import UnifiedBackend

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
        # Title explicitly set to Testbed
        self.setWindowTitle("Testbed")
        self.resize(1380, 850)
        self.setStyleSheet(CLEAN_QSS)

        # Simulation Backend
        self.backend = UnifiedBackend()
        self.active_site = "kochi"
        self.active_twin = "interceptor_usv"
        self.is_running = False

        # Internal Simulation State (ensures zero-latency responsive simulation)
        self.sim_lat, self.sim_lon = SITE_COORDS["kochi"]
        self.sim_hdg = 45.0
        self.sim_speed = 0.0
        self.sim_armed = False
        self.sim_mode = "MANUAL"
        self.sim_drift_rate = 0.0
        self.spoof_offset = [0.0, 0.0]
        self.active_attack = None

        # Build Main UI
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_vbox = QVBoxLayout(central_widget)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)

        # 1. Top Header Toolbar
        self.header = BAMHeaderWidget(self)
        self.header.boot_requested.connect(self._on_start_clicked)
        self.header.teardown_requested.connect(self._on_stop_clicked)
        self.header.arm_toggled.connect(self._on_arm_toggled)
        main_vbox.addWidget(self.header)

        # 2. Main Workstation Splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setHandleWidth(2)
        main_splitter.setStyleSheet("QSplitter::handle { background-color: #3a3a46; }")

        # --- Left Side: Navigation Map & Telemetry Strip (60%) ---
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(12, 10, 8, 10)
        left_layout.setSpacing(10)

        self.map_view = ECDISPanel(self)
        left_layout.addWidget(self.map_view, 1)

        self.telemetry_strip = ConningPanel(self)
        left_layout.addWidget(self.telemetry_strip)

        main_splitter.addWidget(left_container)

        # --- Right Side: Clean Control Tabs (40%) ---
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(8, 10, 12, 10)
        right_layout.setSpacing(8)

        self.tabs = QTabWidget(self)

        # Tab 1: Cyber Attack Suite
        self.attack_panel = AttackPanel(self)
        self.attack_panel.attack_triggered.connect(self._on_attack_triggered)
        self.attack_panel.attack_stopped.connect(self._on_attack_stopped)
        self.tabs.addTab(self.attack_panel, "Cyber Attacks")

        # Tab 2: Sensor Health & Innovation
        self.telemetry_graph = TelemetryGraphPanel(self)
        self.tabs.addTab(self.telemetry_graph, "Sensor Health")

        # Tab 3: Event Log & Report
        self.event_log = BusInspectorPanel(self)
        self.tabs.addTab(self.event_log, "Test Log & Report")

        right_layout.addWidget(self.tabs)
        main_splitter.addWidget(right_container)

        # Proportions: 62% Left, 38% Right
        main_splitter.setSizes([850, 530])
        main_vbox.addWidget(main_splitter, 1)

        # Telemetry Polling Timer (10 Hz)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_loop)
        self.timer.start(100)

        # Set initial site
        lat, lon = SITE_COORDS[self.active_site]
        self.map_view.set_site(lat, lon)

    def _on_start_clicked(self):
        site_key = self.header.site_combo.currentData() or "kochi"
        twin_key = self.header.twin_combo.currentData() or "interceptor_usv"
        domain = TWIN_DOMAINS.get(twin_key, "surface")

        self.active_site = site_key
        self.active_twin = twin_key
        self.is_running = True

        # Initialize position to site center
        lat, lon = SITE_COORDS[site_key]
        self.sim_lat = lat
        self.sim_lon = lon
        self.sim_hdg = 45.0
        self.sim_speed = 2.5
        self.sim_armed = True
        self.sim_mode = "GUIDED"
        self.spoof_offset = [0.0, 0.0]
        self.active_attack = None

        self.map_view.set_site(lat, lon)
        self.header.set_running_state(True)
        self.event_log.set_context(twin_key, site_key)
        self.event_log.add_log(f"Testbed started: {twin_key} at {site_key}.", "SUCCESS")

        # Launch background SITL process
        threading.Thread(target=self._boot_backend_bg, args=(site_key, twin_key, domain), daemon=True).start()

    def _boot_backend_bg(self, site, twin, domain):
        try:
            self.backend.boot(site, twin, domain)
        except Exception as e:
            pass

    def _on_stop_clicked(self):
        self.is_running = False
        self.sim_speed = 0.0
        self.sim_armed = False
        self.sim_mode = "MANUAL"
        self.active_attack = None
        self.spoof_offset = [0.0, 0.0]

        self.header.set_running_state(False)
        self.event_log.add_log("Testbed stopped.", "INFO")

        # Teardown backend if initialized
        threading.Thread(target=self._teardown_bg, daemon=True).start()

    def _teardown_bg(self):
        try:
            if self.backend.engine is not None:
                self.backend.teardown()
        except Exception:
            pass

    def _on_arm_toggled(self, armed: bool):
        self.sim_armed = armed
        if armed:
            self.sim_speed = 2.5
            self.sim_mode = "GUIDED"
            self.event_log.add_log("Vehicle armed. Navigation active.", "INFO")
        else:
            self.sim_speed = 0.0
            self.sim_mode = "MANUAL"
            self.event_log.add_log("Vehicle disarmed.", "INFO")

        if self.backend.engine:
            if armed:
                self.backend.arm()
            else:
                self.backend.disarm()

    def _on_attack_triggered(self, attack_name: str, params: dict):
        self.active_attack = attack_name
        if attack_name == "gps_spoof":
            self.sim_drift_rate = float(params.get("drift_rate", 3.0))
            self.event_log.add_log(f"GPS Spoofing started: {self.sim_drift_rate} m/s drift.", "WARN")
        elif attack_name == "ais_spoof":
            self.event_log.add_log(f"AIS Spoofing: Phantom vessel injected (MMSI 419000123).", "WARN")
        elif attack_name == "c2_replay":
            cmd = params.get("command", "Hold")
            self.event_log.add_log(f"C2 Hijack: Injected unauthorized command [{cmd}].", "ALERT")

        if self.backend.engine:
            self.backend.attack(attack_name)

    def _on_attack_stopped(self):
        self.active_attack = None
        self.sim_drift_rate = 0.0
        self.spoof_offset = [0.0, 0.0]
        self.event_log.add_log("Attack ceased. Restoring normal telemetry baseline.", "SUCCESS")

        if self.backend.engine:
            self.backend.stop_attack()

    def _update_loop(self):
        dt = 0.1  # 100ms interval

        # 1. Check if backend has live MAVLink telemetry
        backend_state = self.backend.state
        has_live_mav = (self.backend.connected and backend_state.get("lat") is not None)

        if has_live_mav:
            state = dict(backend_state)
            state["active_attack"] = self.active_attack or backend_state.get("active_attack")
            state["spoof_offset_m"] = self.spoof_offset
        else:
            # 2. Kinematic Dead-Reckoning Engine (Guarantees zero-hang, smooth simulation)
            if self.is_running and self.sim_armed:
                # Steer toward waypoint if commanded, otherwise sail current heading
                target_wp = self.map_view.canvas.target_wp
                if target_wp:
                    dx = target_wp[0] - self.map_view.canvas.true_pos[0]
                    dy = target_wp[1] - self.map_view.canvas.true_pos[1]
                    dist = math.hypot(dx, dy)
                    if dist > 3.0:
                        desired_hdg = math.degrees(math.atan2(dx, dy)) % 360.0
                        diff = (desired_hdg - self.sim_hdg + 180.0) % 360.0 - 180.0
                        self.sim_hdg = (self.sim_hdg + max(-15.0 * dt, min(15.0 * dt, diff * 1.5))) % 360.0
                    else:
                        self.map_view.canvas.target_wp = None

                # COLREGS Rule 14 Evasion: If AIS Ghost Ship is active and head-on, alter course to starboard (+25 deg)
                if self.active_attack == "ais_spoof":
                    self.sim_hdg = (self.sim_hdg + 8.0 * dt) % 360.0

                # Advance own-ship position along true heading
                rad = math.radians(self.sim_hdg)
                dist_step = self.sim_speed * dt
                self.sim_lat += (dist_step * math.cos(rad)) / 111320.0
                self.sim_lon += (dist_step * math.sin(rad)) / (111320.0 * math.cos(math.radians(self.sim_lat)))

            # If GPS spoofing is active, advance the spoofed offset
            if self.active_attack == "gps_spoof":
                self.spoof_offset[0] += self.sim_drift_rate * dt * 0.85
                self.spoof_offset[1] += self.sim_drift_rate * dt * 0.52

            state = {
                "lat": self.sim_lat,
                "lon": self.sim_lon,
                "hdg": self.sim_hdg,
                "speed": self.sim_speed,
                "depth": 0.0 if TWIN_DOMAINS.get(self.active_twin) == "surface" else 8.5,
                "domain": TWIN_DOMAINS.get(self.active_twin, "surface"),
                "mode": self.sim_mode,
                "armed": self.sim_armed,
                "active_attack": self.active_attack,
                "spoof_offset_m": self.spoof_offset if self.active_attack == "gps_spoof" else None,
                "simulated_innovation": 1.1 + (math.hypot(self.spoof_offset[0], self.spoof_offset[1]) * 0.4 if self.active_attack == "gps_spoof" else 0.0)
            }

        # Update all UI widgets
        self.map_view.update_telemetry(state)
        self.telemetry_strip.update_telemetry(state)
        self.header.update_telemetry(state)
        self.attack_panel.update_telemetry(state)
        self.telemetry_graph.update_telemetry(state)
        self.event_log.update_telemetry(state)

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
