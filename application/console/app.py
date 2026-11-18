"""
Maritime Cyber Range — Professional Desktop Testbed Console.
Main Application Window conforming to IEC 62288, IEC 61174, and IACS UR E26/E27.
"""
import os
import sys
import threading
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QMessageBox, QFileDialog
)
from PyQt6.QtCore import QTimer, Qt

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from application.console.theme import TACTICAL_QSS
from application.console.widgets.bam_header import BAMHeaderWidget
from application.console.widgets.conning import ConningPanel
from application.console.widgets.ecdis import ECDISPanel
from application.console.widgets.attack_panel import AttackPanel
from application.console.widgets.telemetry_graph import TelemetryGraphPanel
from application.console.widgets.bus_inspector import BusInspectorPanel
from application.console.report_generator import generate_pdf_report
from communication.unified_backend import UnifiedBackend

SITE_COORDS = {
    "mumbai": (18.92000, 72.80000),
    "kochi": (9.90000, 76.20000),
    "visakhapatnam": (17.70000, 83.30000)
}

TWIN_DOMAINS = {
    "mt_andaman_tug": "surface",
    "interceptor_usv": "surface",
    "survey_usv": "surface",
    "maya_auv": "underwater",
    "auv150": "underwater"
}

class MCRMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Maritime Cyber Range — Resilience & Certification Testbed [IACS UR E26/E27]")
        self.resize(1480, 920)
        self.setStyleSheet(TACTICAL_QSS)

        # Initialize Simulation / Hardware-in-the-Loop Backend
        self.backend = UnifiedBackend()
        self.active_site = "mumbai"
        self.active_twin = "mt_andaman_tug"

        # Central Layout
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_vbox = QVBoxLayout(central_widget)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)

        # 1. Top BAM & Mission Header
        self.header = BAMHeaderWidget(self)
        self.header.boot_requested.connect(self._on_boot_requested)
        self.header.teardown_requested.connect(self._on_teardown_requested)
        main_vbox.addWidget(self.header)

        # Vertical Splitter: Top Operational Layer vs Bottom Diagnostic Layer
        v_splitter = QSplitter(Qt.Orientation.Vertical)
        v_splitter.setHandleWidth(2)

        # 2. Main Operational Workstation (Horizontal Splitter)
        h_workstation = QSplitter(Qt.Orientation.Horizontal)
        h_workstation.setHandleWidth(2)

        # Left: Conning Instrumentation
        self.conning = ConningPanel(self)
        self.conning.arm_toggled.connect(self._on_arm_toggled)
        h_workstation.addWidget(self.conning)

        # Center: Tactical 2D Vector Nautical Chart (ECDIS)
        self.ecdis = ECDISPanel(self)
        self.ecdis.waypoint_commanded.connect(self._on_waypoint_commanded)
        h_workstation.addWidget(self.ecdis)

        # Right: Cyber Resilience Test Suite & Fault Injection
        self.attacks = AttackPanel(self)
        self.attacks.attack_triggered.connect(self._on_attack_triggered)
        self.attacks.attack_stopped.connect(self._on_attack_stopped)
        self.attacks.failsafe_triggered.connect(self._on_failsafe_triggered)
        h_workstation.addWidget(self.attacks)

        h_workstation.setStretchFactor(0, 0)  # Conning fixed width
        h_workstation.setStretchFactor(1, 1)  # ECDIS expands
        h_workstation.setStretchFactor(2, 0)  # Attacks fixed width
        v_splitter.addWidget(h_workstation)

        # 3. Bottom Diagnostic Layer (Splitter: Telemetry Plot vs OT Bus Inspector)
        diag_splitter = QSplitter(Qt.Orientation.Horizontal)
        diag_splitter.setHandleWidth(2)

        # Lower-Left: EKF3 Innovation Residual Graph
        self.graph = TelemetryGraphPanel(self)
        diag_splitter.addWidget(self.graph)

        # Lower-Right: OT Fieldbus / NMEA / MAVLink Inspector
        self.inspector = BusInspectorPanel(self)
        self.inspector.export_requested.connect(self._on_export_report)
        diag_splitter.addWidget(self.inspector)

        diag_splitter.setStretchFactor(0, 1)
        diag_splitter.setStretchFactor(1, 1)
        v_splitter.addWidget(diag_splitter)

        v_splitter.setStretchFactor(0, 3)     # Operational view takes 75% height
        v_splitter.setStretchFactor(1, 1)     # Diagnostic view takes 25% height
        main_vbox.addWidget(v_splitter)

        # 30 Hz Telemetry Refresh Timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_telemetry)
        self.timer.start(33)  # ~30 FPS

        # Set initial site coordinates
        coords = SITE_COORDS[self.active_site]
        self.ecdis.set_origin(coords[0], coords[1])

    # ---------------- User Action Handlers ----------------
    def _on_boot_requested(self, site_id: str, twin_id: str):
        self.active_site = site_id
        self.active_twin = twin_id
        domain = TWIN_DOMAINS.get(twin_id, "surface")

        coords = SITE_COORDS.get(site_id, (18.92, 72.80))
        self.ecdis.set_origin(coords[0], coords[1])

        # Boot in background thread to avoid freezing GUI
        t = threading.Thread(
            target=self.backend.boot,
            args=(site_id, twin_id, domain),
            daemon=True
        )
        t.start()

    def _on_teardown_requested(self):
        t = threading.Thread(target=self.backend.teardown, daemon=True)
        t.start()

    def _on_arm_toggled(self, arm: bool):
        if arm:
            self.backend.arm()
        else:
            self.backend.disarm()

    def _on_waypoint_commanded(self, lat: float, lon: float):
        # Transmit destination waypoint to ArduPilot in GUIDED mode
        self.backend.goto(lat, lon)

    def _on_attack_triggered(self, atk_name: str, params: dict):
        self.backend.attack(atk_name)

    def _on_attack_stopped(self):
        self.backend.stop_attack()

    def _on_failsafe_triggered(self):
        # Force vessel into Loiter / Return-to-Launch holding pattern
        if self.backend.engine and hasattr(self.backend.engine, "m"):
            try:
                self.backend.engine.m.set_mode("LOITER")
            except Exception:
                pass

    def _on_export_report(self):
        out_dir = os.path.join(REPO, "docs", "audit_reports")
        os.makedirs(out_dir, exist_ok=True)
        filename = f"IACS_UR_E26_Resilience_Audit_{self.active_twin}_{time.strftime('%Y%m%d_%H%M%S')}.pdf"
        out_path = os.path.join(out_dir, filename)

        site_name = self.header.site_combo.currentText()
        twin_name = self.header.twin_combo.currentText()

        generate_pdf_report(out_path, twin_name, site_name)
        QMessageBox.information(
            self,
            "Audit Certificate Exported",
            f"Formal IACS UR E26 / E27 Type-Approval Certificate successfully generated:\n\n{out_path}"
        )

    # ---------------- 30 Hz Telemetry Polling ----------------
    def _poll_telemetry(self):
        state = self.backend.state.copy()
        connected = self.backend.connected
        booting = self.backend.booting

        # Propagate to all widgets
        self.header.update_telemetry(state, connected, booting)
        self.conning.update_telemetry(state)
        self.ecdis.update_telemetry(state)
        self.attacks.update_telemetry(state)
        self.graph.update_telemetry(state)
        self.inspector.update_telemetry(state)

    def closeEvent(self, ev):
        if self.backend.engine is not None:
            try:
                self.backend.teardown()
            except Exception:
                pass
        ev.accept()


def main():
    app = QApplication(sys.argv)
    window = MCRMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
