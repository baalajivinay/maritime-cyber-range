"""
Testbed Top Toolbar & Bridge Alert Management (BAM) Header.
Conforming to IEC 62923 (Bridge Alert Management) and IMO MSC.302(87).

Features:
- Title strictly "Testbed".
- Vessel Twin selector with domain indicators (Surface USV vs Underwater AUV).
- Harbour Site selector with live sea state and environmental data.
- Start/Stop simulation and Arm/Disarm operational controls.
- BAM Alert lights: Emergency Alarm, Warning, Caution, Normal.
- Dynamic active threat indicator banner.
"""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt

from application.console.theme import (
    BG_PANEL_HEADER, BORDER_COLOR, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    COLOR_GREEN, COLOR_RED, COLOR_AMBER, COLOR_BLUE
)


class BAMHeaderWidget(QWidget):
    boot_requested = pyqtSignal()
    teardown_requested = pyqtSignal()
    arm_toggled = pyqtSignal(bool)
    twin_changed = pyqtSignal(str)
    site_changed = pyqtSignal(str)
    defense_toggled = pyqtSignal(bool)
    fullscreen_toggled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_PANEL_HEADER};
                border-bottom: 1px solid {BORDER_COLOR};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(10)

        # 1. Main Title
        title = QLabel("Testbed")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {TEXT_PRIMARY}; letter-spacing: 0.5px;")
        layout.addWidget(title)

        # Subtle Vertical Divider
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet(f"color: {BORDER_COLOR};")
        layout.addWidget(sep1)

        # 2. Vessel Selector
        lbl_twin = QLabel("Vehicle:")
        lbl_twin.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: 500; font-size: 11px;")
        layout.addWidget(lbl_twin)

        self.twin_combo = QComboBox()
        self.twin_combo.addItem("Fast Interceptor USV (Surface)", "interceptor_usv")
        self.twin_combo.addItem("Coastal Survey USV (Surface)", "survey_usv")
        self.twin_combo.addItem("MT Andaman Tug (Displacement)", "mt_andaman_tug")
        self.twin_combo.addItem("Maya AUV (Underwater Subsea)", "maya_auv")
        self.twin_combo.addItem("AUV-150 (Deep Flatfish)", "auv150")
        self.twin_combo.setFixedWidth(210)
        self.twin_combo.currentIndexChanged.connect(lambda: self.twin_changed.emit(self.twin_combo.currentData()))
        layout.addWidget(self.twin_combo)

        # 3. Location Selector
        lbl_site = QLabel("Location:")
        lbl_site.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: 500; font-size: 11px;")
        layout.addWidget(lbl_site)

        self.site_combo = QComboBox()
        self.site_combo.addItem("Kochi Port (09.90°N, 76.20°E)", "kochi")
        self.site_combo.addItem("Mumbai Harbour (18.92°N, 72.80°E)", "mumbai")
        self.site_combo.addItem("Visakhapatnam (17.70°N, 83.30°E)", "visakhapatnam")
        self.site_combo.setFixedWidth(220)
        self.site_combo.currentIndexChanged.connect(lambda: self.site_changed.emit(self.site_combo.currentData()))
        layout.addWidget(self.site_combo)

        layout.addSpacing(4)

        # 4. Start & Stop Buttons
        self.btn_boot = QPushButton("Start Testbed")
        self.btn_boot.setProperty("class", "success")
        self.btn_boot.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_GREEN};
                color: #ffffff;
                font-weight: 600;
                padding: 6px 14px;
                border-radius: 4px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: #219653;
            }}
        """)
        self.btn_boot.clicked.connect(self.boot_requested.emit)
        layout.addWidget(self.btn_boot)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setStyleSheet(f"""
            QPushButton {{
                background-color: #383844;
                color: {TEXT_PRIMARY};
                font-weight: 500;
                padding: 6px 12px;
                border-radius: 4px;
                border: 1px solid {BORDER_COLOR};
            }}
            QPushButton:hover {{
                background-color: {COLOR_RED};
                color: #ffffff;
                border: none;
            }}
        """)
        self.btn_stop.clicked.connect(self.teardown_requested.emit)
        layout.addWidget(self.btn_stop)

        layout.addStretch()

        # 5. BAM Alert Status Banner
        self.lbl_bam_alert = QLabel("BAM: NORMAL (NO THREAT)")
        self.lbl_bam_alert.setStyleSheet(f"""
            background-color: #1a2920;
            color: {COLOR_GREEN};
            border: 1px solid #234832;
            border-radius: 10px;
            padding: 3px 10px;
            font-size: 10px;
            font-weight: bold;
        """)
        layout.addWidget(self.lbl_bam_alert)

        # 6. Mode & Arm Indicators
        self.mode_pill = QLabel("MANUAL")
        self.mode_pill.setStyleSheet("""
            background-color: #222533;
            color: #2f80ed;
            border: 1px solid #33405c;
            border-radius: 10px;
            padding: 3px 10px;
            font-size: 10px;
            font-weight: bold;
        """)
        layout.addWidget(self.mode_pill)

        self.btn_arm = QPushButton("Arm Vehicle")
        self.btn_arm.setCheckable(True)
        self.btn_arm.setStyleSheet(f"""
            QPushButton {{
                background-color: #2e303b;
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: 600;
            }}
            QPushButton:checked {{
                background-color: {COLOR_RED};
                border-color: {COLOR_RED};
                color: #ffffff;
            }}
        """)
        self.btn_arm.toggled.connect(self._on_arm_toggled)
        layout.addWidget(self.btn_arm)

        # Autonomous Defense arming toggle (Task 3)
        self.btn_defense = QPushButton("Auto-Defense")
        self.btn_defense.setCheckable(True)
        self.btn_defense.setToolTip(
            "Arm autonomous fail-safe: GNSS/acoustic failover, COLREGS phantom "
            "gate, and C2 actuator quarantine + loiter")
        self.btn_defense.setStyleSheet(f"""
            QPushButton {{
                background-color: #2e303b;
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: 600;
            }}
            QPushButton:checked {{
                background-color: {COLOR_BLUE};
                border-color: {COLOR_BLUE};
                color: #ffffff;
            }}
        """)
        self.btn_defense.toggled.connect(self.defense_toggled.emit)
        layout.addWidget(self.btn_defense)

        # Fullscreen Toggle Button
        self.btn_fullscreen = QPushButton("⛶ Fullscreen")
        self.btn_fullscreen.setToolTip("Toggle Full Screen Mode (F11)")
        self.btn_fullscreen.setStyleSheet(f"""
            QPushButton {{
                background-color: #2e303b;
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: 600;
                color: {TEXT_PRIMARY};
            }}
            QPushButton:hover {{
                background-color: #383a48;
                color: #ffffff;
            }}
        """)
        self.btn_fullscreen.clicked.connect(self.fullscreen_toggled.emit)
        layout.addWidget(self.btn_fullscreen)

    def _on_arm_toggled(self, checked: bool):
        self.btn_arm.setText("Disarm" if checked else "Arm Vehicle")
        self.arm_toggled.emit(checked)

    def set_running_state(self, is_running: bool):
        if is_running:
            self.btn_boot.setEnabled(False)
            self.twin_combo.setEnabled(False)
            self.site_combo.setEnabled(False)
        else:
            self.btn_boot.setEnabled(True)
            self.twin_combo.setEnabled(True)
            self.site_combo.setEnabled(True)
            self.lbl_bam_alert.setText("BAM: NORMAL (NO THREAT)")
            self.lbl_bam_alert.setStyleSheet(f"""
                background-color: #1a2920;
                color: {COLOR_GREEN};
                border: 1px solid #234832;
                border-radius: 10px;
                padding: 3px 10px;
                font-size: 10px;
                font-weight: bold;
            """)

    def update_telemetry(self, state: dict):
        mode = state.get("mode", "MANUAL")
        self.mode_pill.setText(str(mode).upper())

        # Autonomous-defense banner takes precedence over the raw threat banner
        defense_banner = state.get("defense_banner")
        if defense_banner:
            self.lbl_bam_alert.setText(defense_banner)
            self.lbl_bam_alert.setStyleSheet(f"""
                background-color: #16263b;
                color: {COLOR_BLUE};
                border: 1px solid #27486e;
                border-radius: 10px;
                padding: 3px 10px;
                font-size: 10px;
                font-weight: bold;
            """)
            armed = state.get("armed", False)
            if armed != self.btn_arm.isChecked():
                self.btn_arm.blockSignals(True)
                self.btn_arm.setChecked(armed)
                self.btn_arm.setText("Disarm" if armed else "Arm Vehicle")
                self.btn_arm.blockSignals(False)
            mode = state.get("mode", "MANUAL")
            self.mode_pill.setText(str(mode).upper())
            return

        active_atk = state.get("active_attack")
        if active_atk == "gps_spoof":
            self.lbl_bam_alert.setText("ALARM: GNSS WALK-OFF SPOOFING")
            self.lbl_bam_alert.setStyleSheet(f"""
                background-color: #3b1c1c;
                color: {COLOR_RED};
                border: 1px solid #632626;
                border-radius: 10px;
                padding: 3px 10px;
                font-size: 10px;
                font-weight: bold;
            """)
        elif active_atk == "ais_spoof":
            risk = state.get("collision_risk", False)
            if risk:
                self.lbl_bam_alert.setText("ALARM: AIS GHOST COLLISION RISK (COLREGS)")
                self.lbl_bam_alert.setStyleSheet(f"""
                    background-color: #3b1c1c;
                    color: {COLOR_RED};
                    border: 1px solid #632626;
                    border-radius: 10px;
                    padding: 3px 10px;
                    font-size: 10px;
                    font-weight: bold;
                """)
            else:
                self.lbl_bam_alert.setText("WARNING: AIS PHANTOM TARGET DETECTED")
                self.lbl_bam_alert.setStyleSheet(f"""
                    background-color: #3b2a1a;
                    color: {COLOR_AMBER};
                    border: 1px solid #5e3f20;
                    border-radius: 10px;
                    padding: 3px 10px;
                    font-size: 10px;
                    font-weight: bold;
                """)
        elif active_atk == "c2_replay":
            self.lbl_bam_alert.setText("ALARM: UNAUTHORIZED C2 OVERRIDE")
            self.lbl_bam_alert.setStyleSheet(f"""
                background-color: #3b1c1c;
                color: {COLOR_RED};
                border: 1px solid #632626;
                border-radius: 10px;
                padding: 3px 10px;
                font-size: 10px;
                font-weight: bold;
            """)
        elif active_atk == "acoustic_spoof":
            self.lbl_bam_alert.setText("ALARM: USBL ACOUSTIC FIX SPOOFING")
            self.lbl_bam_alert.setStyleSheet(f"""
                background-color: #3b1c1c;
                color: {COLOR_RED};
                border: 1px solid #632626;
                border-radius: 10px;
                padding: 3px 10px;
                font-size: 10px;
                font-weight: bold;
            """)
        else:
            self.lbl_bam_alert.setText("BAM: NORMAL (NO THREAT)")
            self.lbl_bam_alert.setStyleSheet(f"""
                background-color: #1a2920;
                color: {COLOR_GREEN};
                border: 1px solid #234832;
                border-radius: 10px;
                padding: 3px 10px;
                font-size: 10px;
                font-weight: bold;
            """)

        armed = state.get("armed", False)
        if armed != self.btn_arm.isChecked():
            self.btn_arm.blockSignals(True)
            self.btn_arm.setChecked(armed)
            self.btn_arm.setText("Disarm" if armed else "Arm Vehicle")
            self.btn_arm.blockSignals(False)
