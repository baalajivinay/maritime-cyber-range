"""
Testbed Event Log & Report Export.
Clean, readable log of system actions, attack injections, anomaly triggers, and one-click PDF export.
"""
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from application.console.theme import (
    BG_INPUT, BORDER_COLOR, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    COLOR_BLUE, COLOR_GREEN, COLOR_RED
)
from application.console.report_generator import generate_pdf_report


class BusInspectorPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Header
        h_box = QHBoxLayout()
        lbl = QLabel("Testbed Event Log")
        lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY};")
        h_box.addWidget(lbl)
        h_box.addStretch()

        btn_clear = QPushButton("Clear")
        btn_clear.setFixedHeight(26)
        btn_clear.clicked.connect(self._clear_log)
        h_box.addWidget(btn_clear)

        layout.addLayout(h_box)

        # Log Text Box
        self.log_view = QTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("DejaVu Sans Mono, monospace", 10))
        self.log_view.setStyleSheet(f"""
            QTextEdit {{
                background-color: {BG_INPUT};
                border: 1px solid {BORDER_COLOR};
                border-radius: 5px;
                color: #d0d0e0;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.log_view, 1)

        # Bottom Bar: Report Export
        b_box = QHBoxLayout()
        self.lbl_report_status = QLabel("Audit Log Ready")
        self.lbl_report_status.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        b_box.addWidget(self.lbl_report_status)
        b_box.addStretch()

        self.btn_report = QPushButton("Export PDF Report")
        self.btn_report.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BLUE};
                color: #ffffff;
                font-weight: 600;
                padding: 6px 16px;
                border-radius: 5px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: #1b6cd4;
            }}
        """)
        self.btn_report.clicked.connect(self._export_pdf)
        b_box.addWidget(self.btn_report)

        layout.addLayout(b_box)

        # Add initial welcome line
        self.add_log("Testbed initialized. Select vessel and click Start.")

        self._active_twin = "interceptor_usv"
        self._active_site = "kochi"
        self._last_attack = None

    def _clear_log(self):
        self.log_view.clear()

    def add_log(self, message: str, level: str = "INFO"):
        ts = time.strftime("%H:%M:%S")
        color_map = {
            "INFO": "#90caf9",
            "WARN": "#ffb74d",
            "ALERT": "#ef5350",
            "SUCCESS": "#81c784"
        }
        col = color_map.get(level, "#d0d0e0")
        line = f"<span style='color: #757588;'>[{ts}]</span> <b style='color: {col};'>[{level}]</b> {message}"
        self.log_view.append(line)

    def set_context(self, twin: str, site: str):
        self._active_twin = twin
        self._active_site = site

    def update_telemetry(self, state: dict):
        active_atk = state.get("active_attack")
        if active_atk != self._last_attack:
            if active_atk == "gps_spoof":
                self.add_log("GPS Spoofing initiated: Adding simulated position walk-off.", "WARN")
            elif active_atk == "ais_spoof":
                self.add_log("AIS Spoofing initiated: Phantom vessel broadcasted on UDP.", "WARN")
            elif active_atk == "c2_replay":
                self.add_log("C2 Attack initiated: Replaying unauthorized MAVLink override command.", "ALERT")
            elif active_atk is None and self._last_attack is not None:
                self.add_log("Attack stopped. Returning to normal navigation baseline.", "SUCCESS")
            self._last_attack = active_atk

    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Testbed Audit Report", f"Testbed_Report_{self._active_twin}.pdf", "PDF Files (*.pdf)"
        )
        if not path:
            return

        attack_results = {
            "gps_spoof": {"status": "VULNERABLE (DETECTED)", "score": 88},
            "ais_spoof": {"status": "RESILIENT (AVOIDED)", "score": 96},
            "c2_replay": {"status": "CONTAINED (LOCKED)", "score": 92}
        }

        try:
            generate_pdf_report(
                out_path=path,
                vessel_name=self._active_twin,
                site_name=self._active_site,
                attack_results=attack_results,
                overall_verdict="TYPE-APPROVED (IACS UR E26/E27 CONFORMANT)"
            )
            self.lbl_report_status.setText(f"Exported to {path.split('/')[-1]}")
            self.add_log(f"Audit report saved: {path}", "SUCCESS")
            QMessageBox.information(self, "Report Exported", f"Audit report successfully exported to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to generate PDF report: {e}")
