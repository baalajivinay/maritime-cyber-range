"""
Testbed Cyber Attack Suite.
Clean, intuitive control panel for GPS spoofing, AIS ghost injection, and C2 replay attacks.
"""
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QGroupBox
)
from PyQt6.QtCore import pyqtSignal, Qt

from application.console.theme import (
    PANEL_BG, PANEL_BORDER, PANEL_HEADER, TEXT_WHITE, TEXT_MUTED,
    COLOR_RED, COLOR_GREEN, COLOR_BLUE
)


class AttackPanel(QFrame):
    attack_triggered = pyqtSignal(str, dict)
    attack_stopped = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "panel")
        self.setFixedWidth(290)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        lbl_head = QLabel("Cyber Attacks")
        lbl_head.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_WHITE};")
        layout.addWidget(lbl_head)

        # -------------------------------------------------------------
        # 1. GPS Spoofing
        # -------------------------------------------------------------
        box_gps = QGroupBox("GPS Spoofing")
        l_gps = QVBoxLayout(box_gps)
        l_gps.setSpacing(8)

        desc_gps = QLabel("Injects coordinate drift into GNSS position feed.")
        desc_gps.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        l_gps.addWidget(desc_gps)

        # Drift Slider
        row_rate = QHBoxLayout()
        row_rate.addWidget(QLabel("Drift Rate:"))
        self.lbl_rate_val = QLabel("3.0 m/s")
        self.lbl_rate_val.setStyleSheet(f"font-weight: bold; color: {COLOR_BLUE};")
        row_rate.addWidget(self.lbl_rate_val)
        row_rate.addStretch()
        l_gps.addLayout(row_rate)

        self.slider_drift = QSlider(Qt.Orientation.Horizontal)
        self.slider_drift.setRange(10, 80)
        self.slider_drift.setValue(30)
        self.slider_drift.valueChanged.connect(
            lambda v: self.lbl_rate_val.setText(f"{v / 10.0:.1f} m/s")
        )
        l_gps.addWidget(self.slider_drift)

        row_gps_action = QHBoxLayout()
        self.lbl_divergence = QLabel("Drift: 0.0 m")
        self.lbl_divergence.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        row_gps_action.addWidget(self.lbl_divergence)
        row_gps_action.addStretch()

        self.btn_gps = QPushButton("Inject GPS Spoof")
        self.btn_gps.setCheckable(True)
        self.btn_gps.setStyleSheet(f"""
            QPushButton {{
                background-color: #2e303b;
                border: 1px solid {PANEL_BORDER};
                padding: 5px 12px;
                font-weight: 600;
            }}
            QPushButton:checked {{
                background-color: {COLOR_RED};
                color: #ffffff;
                border: none;
            }}
        """)
        self.btn_gps.toggled.connect(self._toggle_gps)
        row_gps_action.addWidget(self.btn_gps)
        l_gps.addLayout(row_gps_action)

        layout.addWidget(box_gps)

        # -------------------------------------------------------------
        # 2. AIS Spoofing
        # -------------------------------------------------------------
        box_ais = QGroupBox("AIS Spoofing")
        l_ais = QVBoxLayout(box_ais)
        l_ais.setSpacing(8)

        desc_ais = QLabel("Broadcasts fake AIS target to test collision avoidance.")
        desc_ais.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        l_ais.addWidget(desc_ais)

        row_ais_info = QHBoxLayout()
        row_ais_info.addWidget(QLabel("Target: MMSI 419000123"))
        row_ais_info.addStretch()
        row_ais_info.addWidget(QLabel("Course: 180°"))
        l_ais.addLayout(row_ais_info)

        row_ais_action = QHBoxLayout()
        self.lbl_ais_status = QLabel("Standby")
        self.lbl_ais_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        row_ais_action.addWidget(self.lbl_ais_status)
        row_ais_action.addStretch()

        self.btn_ais = QPushButton("Inject Ghost Ship")
        self.btn_ais.setCheckable(True)
        self.btn_ais.setStyleSheet(f"""
            QPushButton {{
                background-color: #2e303b;
                border: 1px solid {PANEL_BORDER};
                padding: 5px 12px;
                font-weight: 600;
            }}
            QPushButton:checked {{
                background-color: {COLOR_RED};
                color: #ffffff;
                border: none;
            }}
        """)
        self.btn_ais.toggled.connect(self._toggle_ais)
        row_ais_action.addWidget(self.btn_ais)
        l_ais.addLayout(row_ais_action)

        layout.addWidget(box_ais)

        # -------------------------------------------------------------
        # 3. Command & Control (C2)
        # -------------------------------------------------------------
        box_c2 = QGroupBox("Command & Control (C2)")
        l_c2 = QVBoxLayout(box_c2)
        l_c2.setSpacing(8)

        desc_c2 = QLabel("Injects unauthorized MAVLink override command.")
        desc_c2.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        l_c2.addWidget(desc_c2)

        self.combo_c2 = QComboBox()
        self.combo_c2.addItem("Emergency Return to Launch (RTL)")
        self.combo_c2.addItem("Force Hold Position")
        self.combo_c2.addItem("Manual Steering Override")
        l_c2.addWidget(self.combo_c2)

        row_c2_action = QHBoxLayout()
        self.lbl_c2_status = QLabel("Link: Normal")
        self.lbl_c2_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        row_c2_action.addWidget(self.lbl_c2_status)
        row_c2_action.addStretch()

        self.btn_c2 = QPushButton("Inject C2 Override")
        self.btn_c2.setCheckable(True)
        self.btn_c2.setStyleSheet(f"""
            QPushButton {{
                background-color: #2e303b;
                border: 1px solid {PANEL_BORDER};
                padding: 5px 12px;
                font-weight: 600;
            }}
            QPushButton:checked {{
                background-color: {COLOR_RED};
                color: #ffffff;
                border: none;
            }}
        """)
        self.btn_c2.toggled.connect(self._toggle_c2)
        row_c2_action.addWidget(self.btn_c2)
        l_c2.addLayout(row_c2_action)

        layout.addWidget(box_c2)

        layout.addStretch()

    def _toggle_gps(self, checked: bool):
        if checked:
            self.btn_gps.setText("Stop GPS Spoof")
            if self.btn_ais.isChecked():
                self.btn_ais.setChecked(False)
            if self.btn_c2.isChecked():
                self.btn_c2.setChecked(False)

            drift_rate = self.slider_drift.value() / 10.0
            self.attack_triggered.emit("gps_spoof", {"drift_rate": drift_rate})
        else:
            self.btn_gps.setText("Inject GPS Spoof")
            self.lbl_divergence.setText("Drift: 0.0 m")
            self.lbl_divergence.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            self.attack_stopped.emit()

    def _toggle_ais(self, checked: bool):
        if checked:
            self.btn_ais.setText("Clear Ghost")
            if self.btn_gps.isChecked():
                self.btn_gps.setChecked(False)
            if self.btn_c2.isChecked():
                self.btn_c2.setChecked(False)

            self.lbl_ais_status.setText("Threat Active")
            self.lbl_ais_status.setStyleSheet(f"color: {COLOR_RED}; font-weight: bold; font-size: 11px;")
            self.attack_triggered.emit("ais_spoof", {"mmsi": "419000123", "speed": 4.0, "course": 180.0})
        else:
            self.btn_ais.setText("Inject Ghost Ship")
            self.lbl_ais_status.setText("Standby")
            self.lbl_ais_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            self.attack_stopped.emit()

    def _toggle_c2(self, checked: bool):
        if checked:
            self.btn_c2.setText("Release C2")
            if self.btn_gps.isChecked():
                self.btn_gps.setChecked(False)
            if self.btn_ais.isChecked():
                self.btn_ais.setChecked(False)

            cmd = self.combo_c2.currentText()
            self.lbl_c2_status.setText("Injected")
            self.lbl_c2_status.setStyleSheet(f"color: {COLOR_RED}; font-weight: bold; font-size: 11px;")
            self.attack_triggered.emit("c2_replay", {"command": cmd})
        else:
            self.btn_c2.setText("Inject C2 Override")
            self.lbl_c2_status.setText("Link: Normal")
            self.lbl_c2_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            self.attack_stopped.emit()

    def update_telemetry(self, state: dict):
        active_atk = state.get("active_attack")
        spoof_offset = state.get("spoof_offset_m")

        if active_atk == "gps_spoof" and spoof_offset:
            import math
            dist = math.hypot(spoof_offset[0], spoof_offset[1])
            self.lbl_divergence.setText(f"Drift: {dist:.1f} m")
            self.lbl_divergence.setStyleSheet(f"color: {COLOR_RED}; font-weight: bold; font-size: 11px;")
        elif not active_atk:
            if self.btn_gps.isChecked():
                self.btn_gps.blockSignals(True)
                self.btn_gps.setChecked(False)
                self.btn_gps.setText("Inject GPS Spoof")
                self.lbl_divergence.setText("Drift: 0.0 m")
                self.lbl_divergence.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: bold;")
                self.btn_gps.blockSignals(False)
            if self.btn_ais.isChecked():
                self.btn_ais.blockSignals(True)
                self.btn_ais.setChecked(False)
                self.btn_ais.setText("Inject Ghost Ship")
                self.lbl_ais_status.setText("Standby")
                self.lbl_ais_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
                self.btn_ais.blockSignals(False)
            if self.btn_c2.isChecked():
                self.btn_c2.blockSignals(True)
                self.btn_c2.setChecked(False)
                self.btn_c2.setText("Inject C2 Override")
                self.lbl_c2_status.setText("Link: Normal")
                self.lbl_c2_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
                self.btn_c2.blockSignals(False)
