"""
Live Telemetry & Protocol Stream Inspector Widget.
Displays streaming NMEA 0183 & MAVLink packets with live anomaly highlighting and PDF report export.
"""
import time
import os
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QComboBox, QFileDialog, QMessageBox
)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import pyqtSignal, Qt

from application.console.theme import (
    PANEL_BG, PANEL_BORDER, PANEL_HEADER, COLOR_BLUE, COLOR_GREEN,
    COLOR_RED, COLOR_AMBER, TEXT_WHITE, TEXT_MUTED
)
from application.console.report_generator import generate_pdf_report


class BusInspectorPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Header Bar
        head_layout = QHBoxLayout()
        lbl = QLabel("Telemetry & Protocol Stream")
        lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {TEXT_WHITE};")
        head_layout.addWidget(lbl)

        head_layout.addStretch()

        # Filter
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All Frames", "all")
        self.filter_combo.addItem("Anomalies Only", "anomalies")
        self.filter_combo.addItem("NMEA 0183", "nmea")
        self.filter_combo.addItem("MAVLink 2", "mavlink")
        self.filter_combo.setFixedHeight(24)
        head_layout.addWidget(self.filter_combo)

        # Export Report Button
        self.btn_export = QPushButton("Export PDF Report")
        self.btn_export.setFixedHeight(24)
        self.btn_export.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BLUE};
                color: #ffffff;
                font-weight: 600;
                padding: 4px 12px;
                border-radius: 4px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: #1b6cd4;
            }}
        """)
        self.btn_export.clicked.connect(self._export_pdf)
        head_layout.addWidget(self.btn_export)

        layout.addLayout(head_layout)

        # Table Stream
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["TIME", "PROTOCOL", "RAW FRAME / MESSAGE PAYLOAD", "STATUS"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        self._row_count = 0
        self.max_rows = 100
        self.active_twin = "interceptor_usv"
        self.active_site = "kochi"

    def set_context(self, twin: str, site: str):
        self.active_twin = twin
        self.active_site = site

    def add_packet(self, proto: str, payload: str, is_anomaly: bool = False, note: str = "VALID"):
        filter_mode = self.filter_combo.currentData()
        if filter_mode == "anomalies" and not is_anomaly:
            return
        if filter_mode == "nmea" and "NMEA" not in proto:
            return
        if filter_mode == "mavlink" and "MAV" not in proto:
            return

        row = self.table.rowCount()
        if row >= self.max_rows:
            self.table.removeRow(0)
            row = self.table.rowCount()

        self.table.insertRow(row)

        ts = time.strftime("%H:%M:%S")
        item_time = QTableWidgetItem(ts)
        item_proto = QTableWidgetItem(proto)
        item_payload = QTableWidgetItem(payload)
        item_verdict = QTableWidgetItem(note)

        item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item_proto.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item_verdict.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        font_mono = QFont("DejaVu Sans Mono, monospace", 9)
        item_time.setFont(font_mono)
        item_payload.setFont(font_mono)

        if is_anomaly:
            col_text = QColor(COLOR_RED)
            item_verdict.setBackground(QColor(235, 87, 87, 30))
        else:
            col_text = QColor(TEXT_WHITE)
            item_verdict.setBackground(QColor(39, 174, 96, 20))

        item_time.setForeground(QColor(TEXT_MUTED))
        item_proto.setForeground(QColor(COLOR_BLUE))
        item_payload.setForeground(col_text)
        item_verdict.setForeground(QColor(COLOR_RED if is_anomaly else COLOR_GREEN))

        self.table.setItem(row, 0, item_time)
        self.table.setItem(row, 1, item_proto)
        self.table.setItem(row, 2, item_payload)
        self.table.setItem(row, 3, item_verdict)

        self.table.scrollToBottom()

    def update_telemetry(self, state: dict):
        active_atk = state.get("active_attack")
        lat = state.get("lat") if state.get("lat") is not None else 9.9000
        lon = state.get("lon") if state.get("lon") is not None else 76.2000
        hdg = state.get("hdg") if state.get("hdg") is not None else 45.0
        sog = state.get("speed") if state.get("speed") is not None else 0.0

        if active_atk == "gps_spoof":
            self.add_packet("NMEA 0183", f"$GPGGA,120421.00,{lat:09.5f},N,{lon:010.5f},E,1,08,1.2,0.0,M,,,,*42",
                            is_anomaly=True, note="REJECTED (INNOVATION > 8.0m)")
        elif active_atk == "ais_spoof":
            self.add_packet("AIS VDM", "!AIVDM,1,1,,A,15N7v80P00IS?1rM7nUa?wp00000,0*1E",
                            is_anomaly=True, note="PHANTOM TARGET (MMSI 419000123)")
        elif active_atk == "c2_replay":
            self.add_packet("MAVLink 2", "COMMAND_LONG [cmd=MAV_CMD_DO_SET_MODE, param1=HOLD]",
                            is_anomaly=True, note="UNAUTHORIZED OVERRIDE")
        else:
            import random
            if random.random() < 0.25:
                self.add_packet("NMEA 0183", f"$GPRMC,120421.00,A,{lat:08.4f},N,{lon:09.4f},E,{sog*1.94:.1f},{hdg:.1f},191126,,,A*7A",
                                is_anomaly=False, note="VALID (FIX OK)")
            elif random.random() < 0.35:
                self.add_packet("MAVLink 2", f"GLOBAL_POSITION_INT [lat={int(lat*1e7)}, lon={int(lon*1e7)}, hdg={int(hdg*100)}]",
                                is_anomaly=False, note="VALID (HEARTBEAT OK)")

    def _export_pdf(self):
        default_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs", "audit_reports")
        os.makedirs(default_dir, exist_ok=True)
        default_file = os.path.join(default_dir, f"Testbed_Report_{self.active_twin}.pdf")

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Testbed Audit Certificate", default_file, "PDF Files (*.pdf)"
        )
        if not path:
            return

        try:
            generate_pdf_report(
                out_path=path,
                vessel_name=self.active_twin,
                site_name=self.active_site
            )
            QMessageBox.information(self, "Audit Report Exported", f"Official audit report successfully saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to generate PDF report: {e}")
