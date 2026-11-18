"""
Testbed — Main Application Window.
Professional maritime resilience testbed replicating proven industrial workstation layouts
(Conning Gyro Compass, ECDIS Navigation Chart, Cyber Attack Suite, EKF3 Diagnostics, and Protocol Stream).
"""
import os
import sys
import threading
import time
import math
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QMessageBox
)
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
        self.resize(1440, 880)
        self.setStyleSheet(TESTBED_QSS)

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

        # 2. Main Vertical Splitter (Top Operational Workstation / Bottom Diagnostics)
        v_splitter = QSplitter(Qt.Orientation.Vertical)
        v_splitter.setHandleWidth(2)

        # --- Upper Workstation Splitter (Horizontal: Conning | ECDIS Chart | Cyber Attacks) ---
        h_upper = QSplitter(Qt.Orientation.Horizontal)
        h_upper.setHandleWidth(2)

        # Left: Conning & Gyro Compass
        self.conning = ConningPanel(self)
        h_upper.addWidget(self.conning)

        # Center: Interactive 2D Navigation Chart
        self.map_view = ECDISPanel(self)
        h_upper.addWidget(self.map_view)

        # Right: Cyber Attack Panel
        self.attack_panel = AttackPanel(self)
        self.attack_panel.attack_triggered.connect(self._on_attack_triggered)
        self.attack_panel.attack_stopped.connect(self._on_attack_stopped)
        h_upper.addWidget(self.attack_panel)

        # Sizes: Conning ~240px, Chart flex, Attacks ~290px
        h_upper.setSizes([240, 910, 290])
        v_splitter.addWidget(h_upper)

        # --- Lower Diagnostic Splitter (Horizontal: Innovation Graph | Protocol Stream & Export) ---
        h_lower = QSplitter(Qt.Orientation.Horizontal)
        h_lower.setHandleWidth(2)

        # Left: EKF3 Innovation Residual Graph
        self.telemetry_graph = TelemetryGraphPanel(self)
        h_lower.addWidget(self.telemetry_graph)

        # Right: Telemetry / Protocol Stream Table & Export PDF
        self.inspector = BusInspectorPanel(self)
        h_lower.addWidget(self.inspector)

        h_lower.setSizes([600, 840])
        v_splitter.addWidget(h_lower)

        # Height Splitter: 65% Top Workstation / 35% Bottom Diagnostics
        v_splitter.setSizes([570, 310])
        main_vbox.addWidget(v_splitter, 1)

        # Telemetry Polling Timer (10 Hz)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_loop)
        self.timer.start(100)

        # Set initial site
        lat, lon = SITE_COORDS[self.active_site]
        self.map_view.set_site(lat, lon)
        self.inspector.set_context(self.active_twin, self.active_site)

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
        self.inspector.set_context(twin_key, site_key)

        # Launch background SITL process
        threading.Thread(target=self._boot_backend_bg, args=(site_key, twin_key, domain), daemon=True).start()

    def _boot_backend_bg(self, site, twin, domain):
        try:
            self.backend.boot(site, twin, domain)
        except Exception:
            pass

    def _on_stop_clicked(self):
        self.is_running = False
        self.sim_speed = 0.0
        self.sim_armed = False
        self.sim_mode = "MANUAL"
        self.active_attack = None
        self.spoof_offset = [0.0, 0.0]

        self.header.set_running_state(False)

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
        else:
            self.sim_speed = 0.0
            self.sim_mode = "MANUAL"

        if self.backend.engine:
            if armed:
                self.backend.arm()
            else:
                self.backend.disarm()

    def _on_attack_triggered(self, attack_name: str, params: dict):
        self.active_attack = attack_name
        if attack_name == "gps_spoof":
            self.sim_drift_rate = float(params.get("drift_rate", 3.0))

        if self.backend.engine:
            self.backend.attack(attack_name)

    def _on_attack_stopped(self):
        self.active_attack = None
        self.sim_drift_rate = 0.0
        self.spoof_offset = [0.0, 0.0]

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
            # 2. Kinematic Dead-Reckoning Engine
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

                # COLREGS Rule 14 Evasion: If AIS Ghost Ship is active, alter course to starboard (+15 deg)
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
