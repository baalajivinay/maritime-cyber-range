"""
Live OT Fieldbus & Marine Telemetry Inspector Widget (Wireshark-style).
Displays streaming NMEA 0183 & MAVLink packets with live anomaly highlighting.
"""
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QComboBox
)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import pyqtSignal, Qt
from application.console.theme import (
    PANEL_BG, PANEL_BORDER, ACCENT_CYAN, COLOR_PASS, COLOR_WARN, COLOR_ALARM,
    TEXT_WHITE, TEXT_MUTED
)

class BusInspectorPanel(QWidget):
    export_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header Bar
        head_layout = QHBoxLayout()
        lbl = QLabel("OT FIELDBUS & TELEMETRY STREAM (NMEA 0183 / MAVLINK 2)")
        lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {ACCENT_CYAN};")
        head_layout.addWidget(lbl)

        head_layout.addStretch()

        # Filter
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("Filter: All Frames", "all")
        self.filter_combo.addItem("Filter: Anomalies Only", "anomalies")
        self.filter_combo.addItem("Filter: NMEA 0183", "nmea")
        self.filter_combo.addItem("Filter: MAVLink", "mavlink")
        self.filter_combo.setFixedHeight(22)
        head_layout.addWidget(self.filter_combo)

        # Export Button
        self.btn_export = QPushButton("📄 EXPORT CLASS AUDIT REPORT (PDF)")
        self.btn_export.setProperty("class", "btn-primary")
        self.btn_export.setFixedHeight(24)
        self.btn_export.clicked.connect(self.export_requested.emit)
        head_layout.addWidget(self.btn_export)

        layout.addLayout(head_layout)

        # Table Stream
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["TIME", "BUS / PROTOCOL", "RAW FRAME / MESSAGE PAYLOAD", "SECURITY VERDICT"])
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

        # Color coding
        if is_anomaly:
            text_color = QColor(COLOR_ALARM)
            bg_color = QColor(127, 29, 29, 60)
        else:
            text_color = QColor(TEXT_WHITE)
            bg_color = QColor(PANEL_BG)

        for item in [item_time, item_proto, item_payload, item_verdict]:
            item.setForeground(text_color)
            item.setBackground(bg_color)
            item.setFont(QFont("JetBrains Mono", 9))

        self.table.setItem(row, 0, item_time)
        self.table.setItem(row, 1, item_proto)
        self.table.setItem(row, 2, item_payload)
        self.table.setItem(row, 3, item_verdict)

        self.table.scrollToBottom()

    def update_telemetry(self, state: dict):
        # Generate representative live packet streams matching current vehicle state
        active_atk = state.get("active_attack")
        lat = state.get("lat") if state.get("lat") is not None else 18.92
        lon = state.get("lon") if state.get("lon") is not None else 72.80
        hdg = state.get("hdg") if state.get("hdg") is not None else 45.0
        sog = state.get("speed") if state.get("speed") is not None else 0.0


        if active_atk == "gps_spoof":
            self.add_packet("NMEA 0183", f"$GPGGA,120421.00,{lat:09.5f},N,{lon:010.5f},E,1,08,1.2,0.0,M,,,,*42",
                            is_anomaly=True, note="[REJECTED: Δpos/Δt > 8.0 m/s]")
        elif active_atk == "ais_spoof":
            self.add_packet("AIS VDM", f"!AIVDM,1,1,,A,15N7v80P00IS?1rM7nUa?wp00000,0*1E",
                            is_anomaly=True, note="[PHANTOM: MMSI 419000142 GHOST]")
        elif active_atk == "c2_replay":
            self.add_packet("MAVLink 2", f"RC_CHANNELS_OVERRIDE [tgt_sys=1, ch1=1900, ch3=1850]",
                            is_anomaly=True, note="[UNAUTHORIZED: SEQ_NUM REPLAY]")
        else:
            import random
            if random.random() < 0.25:
                self.add_packet("NMEA 0183", f"$GPRMC,120421.00,A,{lat:08.4f},N,{lon:09.4f},E,{sog*1.94:.1f},{hdg:.1f},181126,,,A*7A",
                                is_anomaly=False, note="VALID (INTEGRITY OK)")
            elif random.random() < 0.4:
                self.add_packet("MAVLink 2", f"GLOBAL_POSITION_INT [lat={int(lat*1e7)}, lon={int(lon*1e7)}, hdg={int(hdg*100)}]",
                                is_anomaly=False, note="VALID (TELEMETRY OK)")
