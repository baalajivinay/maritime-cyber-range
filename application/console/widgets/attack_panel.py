"""
Testbed Cyber Attack & Electronic Resilience Suite.
Conforming to IACS UR E26/E27 Zone 1 Boundary Testing and DNV-ST-0373.

Provides domain-adaptive attack execution:
- Surface USV Suite: Multi-Mode GNSS Spoofing (Ramp Walk-Off, Step, Meander, Jamming),
  COLREGS Rule 14/15 AIS Ghost Vessel Injection, and C2 Actuator/Mode Hijack.
- Underwater AUV Suite: USBL Acoustic Positioning Spoofing, Acoustic Blackout/Jamming,
  and MAVLink Surface/Halt Injection.
"""
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QGroupBox, QStackedWidget, QWidget, QScrollArea
)
from PyQt6.QtCore import pyqtSignal, Qt

from application.console.theme import (
    PANEL_BG, PANEL_BORDER, PANEL_HEADER, TEXT_WHITE, TEXT_MUTED,
    COLOR_RED, COLOR_GREEN, COLOR_BLUE, COLOR_AMBER
)


class AttackPanel(QFrame):
    attack_triggered = pyqtSignal(str, dict)
    attack_stopped = pyqtSignal()
    ot_toggled = pyqtSignal(str, bool)   # OT bus tampering vector toggled

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "panel")
        self.setFixedWidth(310)
        self.setMinimumHeight(160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header with domain indicator
        header_row = QHBoxLayout()
        lbl_head = QLabel("Cyber Resilience Suite")
        lbl_head.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_WHITE};")
        header_row.addWidget(lbl_head)
        header_row.addStretch()

        self.lbl_domain_badge = QLabel("SURFACE USV")
        self.lbl_domain_badge.setStyleSheet(f"""
            font-size: 9px;
            font-weight: bold;
            color: {COLOR_BLUE};
            background-color: #1a2233;
            border: 1px solid #2a3a55;
            border-radius: 3px;
            padding: 2px 6px;
        """)
        header_row.addWidget(self.lbl_domain_badge)
        layout.addLayout(header_row)

        # Stacked Widget: Page 0 = Surface Attacks, Page 1 = Underwater Attacks
        self.stack = QStackedWidget(self)

        # Wrap stack in sleek scroll area so attack panels never constrain workstation height
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #15161c;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #2e303b;
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3d4251;
            }
        """)
        self.scroll.setWidget(self.stack)
        layout.addWidget(self.scroll, 1)

        # Build Surface and Underwater pages
        self._build_surface_ui()
        self._build_underwater_ui()

        self.current_domain = "surface"

    def set_domain(self, domain: str):
        self.current_domain = domain
        if domain == "underwater":
            self.lbl_domain_badge.setText("UNDERWATER AUV")
            self.lbl_domain_badge.setStyleSheet(f"""
                font-size: 9px;
                font-weight: bold;
                color: #38bdf8;
                background-color: #162a38;
                border: 1px solid #1e455e;
                border-radius: 3px;
                padding: 2px 6px;
            """)
            self.stack.setCurrentIndex(1)
        else:
            self.lbl_domain_badge.setText("SURFACE USV")
            self.lbl_domain_badge.setStyleSheet(f"""
                font-size: 9px;
                font-weight: bold;
                color: {COLOR_BLUE};
                background-color: #1a2233;
                border: 1px solid #2a3a55;
                border-radius: 3px;
                padding: 2px 6px;
            """)
            self.stack.setCurrentIndex(0)

    # =========================================================================
    # Surface USV Attack Suite
    # =========================================================================
    def _build_surface_ui(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(6)

        # 1. GNSS Spoofing
        box_gps = QGroupBox("GNSS / GPS Spoofing")
        l_gps = QVBoxLayout(box_gps)
        l_gps.setSpacing(4)

        desc_gps = QLabel("Insidious walk-off or step injection into satellite fix.")
        desc_gps.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        l_gps.addWidget(desc_gps)

        # Mode Selection
        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel("Mode:"))
        self.combo_gps_mode = QComboBox()
        self.combo_gps_mode.addItem("Ramp Walk-off (Insidious)", "ramp")
        self.combo_gps_mode.addItem("Step Jump (35m)", "step")
        self.combo_gps_mode.addItem("Harmonic Meander", "meander")
        self.combo_gps_mode.addItem("SNR Jamming (HDOP Spikes)", "jam")
        row_mode.addWidget(self.combo_gps_mode)
        l_gps.addLayout(row_mode)

        # Drift Rate Slider
        row_rate = QHBoxLayout()
        row_rate.addWidget(QLabel("Drift Rate:"))
        self.lbl_gps_rate_val = QLabel("2.5 m/s")
        self.lbl_gps_rate_val.setStyleSheet(f"font-weight: bold; color: {COLOR_BLUE};")
        row_rate.addWidget(self.lbl_gps_rate_val)
        row_rate.addStretch()
        l_gps.addLayout(row_rate)

        self.slider_gps_drift = QSlider(Qt.Orientation.Horizontal)
        self.slider_gps_drift.setRange(5, 60)
        self.slider_gps_drift.setValue(25)
        self.slider_gps_drift.valueChanged.connect(
            lambda v: self.lbl_gps_rate_val.setText(f"{v / 10.0:.1f} m/s")
        )
        l_gps.addWidget(self.slider_gps_drift)

        row_gps_action = QHBoxLayout()
        self.lbl_gps_divergence = QLabel("Drift: 0.0 m")
        self.lbl_gps_divergence.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        row_gps_action.addWidget(self.lbl_gps_divergence)
        row_gps_action.addStretch()

        self.btn_gps = QPushButton("Inject GNSS Spoof")
        self.btn_gps.setCheckable(True)
        self.btn_gps.setStyleSheet(self._btn_style())
        self.btn_gps.toggled.connect(self._toggle_surface_gps)
        row_gps_action.addWidget(self.btn_gps)
        l_gps.addLayout(row_gps_action)

        l.addWidget(box_gps)

        # 2. AIS Spoofing
        box_ais = QGroupBox("AIS Collision Spoofing")
        l_ais = QVBoxLayout(box_ais)
        l_ais.setSpacing(4)

        desc_ais = QLabel("Broadcasts unauthenticated AIVDM collision threats.")
        desc_ais.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        l_ais.addWidget(desc_ais)

        row_ais_scen = QHBoxLayout()
        row_ais_scen.addWidget(QLabel("Encounter:"))
        self.combo_ais_scen = QComboBox()
        self.combo_ais_scen.addItem("Rule 14 Head-On Meeting", "head_on")
        self.combo_ais_scen.addItem("Rule 15 Starboard Crossing", "crossing")
        self.combo_ais_scen.addItem("MMSI Identity Impersonation", "impersonate")
        row_ais_scen.addWidget(self.combo_ais_scen)
        l_ais.addLayout(row_ais_scen)

        self.lbl_ais_cpa = QLabel("Target: Standby  |  CPA: ---")
        self.lbl_ais_cpa.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        l_ais.addWidget(self.lbl_ais_cpa)

        row_ais_action = QHBoxLayout()
        self.lbl_ais_status = QLabel("Standby")
        self.lbl_ais_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        row_ais_action.addWidget(self.lbl_ais_status)
        row_ais_action.addStretch()

        self.btn_ais = QPushButton("Inject Ghost Target")
        self.btn_ais.setCheckable(True)
        self.btn_ais.setStyleSheet(self._btn_style())
        self.btn_ais.toggled.connect(self._toggle_surface_ais)
        row_ais_action.addWidget(self.btn_ais)
        l_ais.addLayout(row_ais_action)

        l.addWidget(box_ais)

        # 3. C2 Hijack
        box_c2 = QGroupBox("C2 Command & Control")
        l_c2 = QVBoxLayout(box_c2)
        l_c2.setSpacing(4)

        desc_c2 = QLabel("Injects forged MAVLink telemetry commands.")
        desc_c2.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        l_c2.addWidget(desc_c2)

        self.combo_c2 = QComboBox()
        self.combo_c2.addItem("RC Override (Seize Actuators)", "rc_override")
        self.combo_c2.addItem("MAVLink SET_MODE (Force HOLD)", "c2_mode_hold")
        self.combo_c2.addItem("Emergency Return to Launch (RTL)", "c2_mode_rtl")
        self.combo_c2.addItem("Malicious Waypoint Injection", "c2_waypoint")
        l_c2.addWidget(self.combo_c2)

        row_c2_action = QHBoxLayout()
        self.lbl_c2_status = QLabel("Link: Authenticated")
        self.lbl_c2_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        row_c2_action.addWidget(self.lbl_c2_status)
        row_c2_action.addStretch()

        self.btn_c2 = QPushButton("Inject C2 Override")
        self.btn_c2.setCheckable(True)
        self.btn_c2.setStyleSheet(self._btn_style())
        self.btn_c2.toggled.connect(self._toggle_surface_c2)
        row_c2_action.addWidget(self.btn_c2)
        l_c2.addLayout(row_c2_action)

        l.addWidget(box_c2)

        # 4. Integrated Bridge / Engine-Room OT Bus Tampering (Task 2)
        l.addWidget(self._build_ot_group())

        l.addStretch()
        self.stack.addWidget(page)

    def _build_ot_group(self) -> QGroupBox:
        """IBS/OT protocol tampering toggles: NMEA sensors, ARPA, engine CAN."""
        box = QGroupBox("Integrated Bridge / Engine OT Bus")
        lo = QVBoxLayout(box)
        lo.setSpacing(3)

        desc = QLabel("Forge IBS sensor & engine CAN traffic (NMEA 0183/2000, J1939).")
        desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        lo.addWidget(desc)

        self.ot_buttons = {}
        specs = [
            ("depth_spoof", "Echo-Sounder Depth Spoof ($SDDPT)"),
            ("heading_spoof", "Gyrocompass Heading Corrupt ($HEHDT)"),
            ("stw_spoof", "Water-Speed (STW) Falsify ($VHW)"),
            ("arpa_false_targets", "Radar / ARPA False Targets"),
            ("engine_sabotage", "Engine CAN J1939 Sabotage (Limp)"),
        ]
        for key, label in specs:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(self._btn_style())
            btn.toggled.connect(lambda on, k=key: self.ot_toggled.emit(k, on))
            lo.addWidget(btn)
            self.ot_buttons[key] = btn

        self.lbl_ot_status = QLabel("Engine: nominal  |  ARPA: clear")
        self.lbl_ot_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        lo.addWidget(self.lbl_ot_status)
        return box

    # =========================================================================
    # Underwater AUV Attack Suite
    # =========================================================================
    def _build_underwater_ui(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(6)

        # 1. USBL Acoustic Positioning Spoofing
        box_usbl = QGroupBox("USBL Acoustic Positioning")
        l_usbl = QVBoxLayout(box_usbl)
        l_usbl.setSpacing(4)

        desc_usbl = QLabel("Manipulates acoustic transponder travel-time delays.")
        desc_usbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        l_usbl.addWidget(desc_usbl)

        row_usbl_rate = QHBoxLayout()
        row_usbl_rate.addWidget(QLabel("Offset Rate:"))
        self.lbl_usbl_rate_val = QLabel("1.5 m/s")
        self.lbl_usbl_rate_val.setStyleSheet(f"font-weight: bold; color: {COLOR_BLUE};")
        row_usbl_rate.addWidget(self.lbl_usbl_rate_val)
        row_usbl_rate.addStretch()
        l_usbl.addLayout(row_usbl_rate)

        self.slider_usbl_drift = QSlider(Qt.Orientation.Horizontal)
        self.slider_usbl_drift.setRange(5, 40)
        self.slider_usbl_drift.setValue(15)
        self.slider_usbl_drift.valueChanged.connect(
            lambda v: self.lbl_usbl_rate_val.setText(f"{v / 10.0:.1f} m/s")
        )
        l_usbl.addWidget(self.slider_usbl_drift)

        row_usbl_action = QHBoxLayout()
        self.lbl_usbl_divergence = QLabel("Bias: 0.0 m")
        self.lbl_usbl_divergence.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        row_usbl_action.addWidget(self.lbl_usbl_divergence)
        row_usbl_action.addStretch()

        self.btn_usbl = QPushButton("Inject USBL Bias")
        self.btn_usbl.setCheckable(True)
        self.btn_usbl.setStyleSheet(self._btn_style())
        self.btn_usbl.toggled.connect(self._toggle_underwater_usbl)
        row_usbl_action.addWidget(self.btn_usbl)
        l_usbl.addLayout(row_usbl_action)

        l.addWidget(box_usbl)

        # 2. Acoustic Telemetry Disruption
        box_ac = QGroupBox("Acoustic Channel Telemetry")
        l_ac = QVBoxLayout(box_ac)
        l_ac.setSpacing(4)

        desc_ac = QLabel("Simulates multipath noise & acoustic telemetry blackout.")
        desc_ac.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        l_ac.addWidget(desc_ac)

        row_ac_action = QHBoxLayout()
        self.lbl_ac_status = QLabel("Link: Clear Fix")
        self.lbl_ac_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        row_ac_action.addWidget(self.lbl_ac_status)
        row_ac_action.addStretch()

        self.btn_ac_jam = QPushButton("Inject Blackout")
        self.btn_ac_jam.setCheckable(True)
        self.btn_ac_jam.setStyleSheet(self._btn_style())
        self.btn_ac_jam.toggled.connect(self._toggle_underwater_jam)
        row_ac_action.addWidget(self.btn_ac_jam)
        l_ac.addLayout(row_ac_action)

        l.addWidget(box_ac)

        # 3. C2 Telecommand Hijack
        box_c2_sub = QGroupBox("Subsea Telecommand Hijack")
        l_c2_sub = QVBoxLayout(box_c2_sub)
        l_c2_sub.setSpacing(4)

        desc_c2_sub = QLabel("Forces emergency surface or thrust cut commands.")
        desc_c2_sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        l_c2_sub.addWidget(desc_c2_sub)

        self.combo_c2_sub = QComboBox()
        self.combo_c2_sub.addItem("Force Emergency Ascent", "c2_ascent")
        self.combo_c2_sub.addItem("Thruster Kill / Power Cut", "c2_disarm")
        self.combo_c2_sub.addItem("Actuator Hard Yaw Override", "c2_override")
        l_c2_sub.addWidget(self.combo_c2_sub)

        row_c2_sub_act = QHBoxLayout()
        self.lbl_c2_sub_status = QLabel("Command: Idle")
        self.lbl_c2_sub_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        row_c2_sub_act.addWidget(self.lbl_c2_sub_status)
        row_c2_sub_act.addStretch()

        self.btn_c2_sub = QPushButton("Inject Telecommand")
        self.btn_c2_sub.setCheckable(True)
        self.btn_c2_sub.setStyleSheet(self._btn_style())
        self.btn_c2_sub.toggled.connect(self._toggle_underwater_c2)
        row_c2_sub_act.addWidget(self.btn_c2_sub)
        l_c2_sub.addLayout(row_c2_sub_act)

        l.addWidget(box_c2_sub)
        l.addStretch()
        self.stack.addWidget(page)

    def _btn_style(self):
        return f"""
            QPushButton {{
                background-color: #2e303b;
                border: 1px solid {PANEL_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #383a48;
            }}
            QPushButton:checked {{
                background-color: {COLOR_RED};
                color: #ffffff;
                border: none;
            }}
        """

    # --- Surface Handlers ---
    def _toggle_surface_gps(self, checked: bool):
        if checked:
            self.btn_gps.setText("Halt GNSS Spoof")
            if self.btn_ais.isChecked():
                self.btn_ais.setChecked(False)
            if self.btn_c2.isChecked():
                self.btn_c2.setChecked(False)

            mode = self.combo_gps_mode.currentData()
            drift_rate = self.slider_gps_drift.value() / 10.0
            self.attack_triggered.emit("gps_spoof", {"mode": mode, "drift_rate": drift_rate, "bearing_deg": 45.0})
        else:
            self.btn_gps.setText("Inject GNSS Spoof")
            self.lbl_gps_divergence.setText("Drift: 0.0 m")
            self.lbl_gps_divergence.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            self.attack_stopped.emit()

    def _toggle_surface_ais(self, checked: bool):
        if checked:
            self.btn_ais.setText("Clear Ghost Target")
            if self.btn_gps.isChecked():
                self.btn_gps.setChecked(False)
            if self.btn_c2.isChecked():
                self.btn_c2.setChecked(False)

            scenario = self.combo_ais_scen.currentData()
            self.lbl_ais_status.setText("THREAT ACTIVE")
            self.lbl_ais_status.setStyleSheet(f"color: {COLOR_RED}; font-weight: bold; font-size: 11px;")
            self.attack_triggered.emit("ais_spoof", {"scenario": scenario})
        else:
            self.btn_ais.setText("Inject Ghost Target")
            self.lbl_ais_status.setText("Standby")
            self.lbl_ais_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            self.lbl_ais_cpa.setText("Target: Standby  |  CPA: ---")
            self.attack_stopped.emit()

    def _toggle_surface_c2(self, checked: bool):
        if checked:
            self.btn_c2.setText("Release C2 Seizure")
            if self.btn_gps.isChecked():
                self.btn_gps.setChecked(False)
            if self.btn_ais.isChecked():
                self.btn_ais.setChecked(False)

            cmd_type = self.combo_c2.currentData()
            self.lbl_c2_status.setText("UNAUTHORIZED OVERRIDE")
            self.lbl_c2_status.setStyleSheet(f"color: {COLOR_RED}; font-weight: bold; font-size: 11px;")
            self.attack_triggered.emit("c2_replay", {"cmd_type": cmd_type})
        else:
            self.btn_c2.setText("Inject C2 Override")
            self.lbl_c2_status.setText("Link: Authenticated")
            self.lbl_c2_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            self.attack_stopped.emit()

    # --- Underwater Handlers ---
    def _toggle_underwater_usbl(self, checked: bool):
        if checked:
            self.btn_usbl.setText("Halt USBL Bias")
            if self.btn_ac_jam.isChecked():
                self.btn_ac_jam.setChecked(False)
            if self.btn_c2_sub.isChecked():
                self.btn_c2_sub.setChecked(False)

            rate = self.slider_usbl_drift.value() / 10.0
            self.attack_triggered.emit("acoustic_spoof", {"rate": rate})
        else:
            self.btn_usbl.setText("Inject USBL Bias")
            self.lbl_usbl_divergence.setText("Bias: 0.0 m")
            self.attack_stopped.emit()

    def _toggle_underwater_jam(self, checked: bool):
        if checked:
            self.btn_ac_jam.setText("Restore Telemetry")
            if self.btn_usbl.isChecked():
                self.btn_usbl.setChecked(False)
            self.lbl_ac_status.setText("CHANNEL BLACKOUT")
            self.lbl_ac_status.setStyleSheet(f"color: {COLOR_RED}; font-weight: bold; font-size: 11px;")
            self.attack_triggered.emit("acoustic_jam", {})
        else:
            self.btn_ac_jam.setText("Inject Blackout")
            self.lbl_ac_status.setText("Link: Clear Fix")
            self.lbl_ac_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            self.attack_stopped.emit()

    def _toggle_underwater_c2(self, checked: bool):
        if checked:
            self.btn_c2_sub.setText("Release Telecommand")
            cmd = self.combo_c2_sub.currentData()
            self.lbl_c2_sub_status.setText("COMMAND SEIZED")
            self.lbl_c2_sub_status.setStyleSheet(f"color: {COLOR_RED}; font-weight: bold; font-size: 11px;")
            self.attack_triggered.emit("c2_replay", {"cmd_type": cmd})
        else:
            self.btn_c2_sub.setText("Inject Telecommand")
            self.lbl_c2_sub_status.setText("Command: Idle")
            self.lbl_c2_sub_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            self.attack_stopped.emit()

    def update_telemetry(self, state: dict):
        active_atk = state.get("active_attack")

        # OT bus status line (engine governor + ARPA false-target count)
        if hasattr(self, "lbl_ot_status"):
            if state.get("ot_active"):
                rpm = state.get("engine_rpm", 0.0)
                cool = state.get("coolant_c", 0.0)
                limp = state.get("engine_limp_mode", False)
                fakes = state.get("arpa_false_target_count", 0)
                eng = "LIMP MODE" if limp else (
                    "OVERHEAT" if state.get("engine_overheat") else f"{rpm:.0f}rpm")
                col = COLOR_RED if (limp or state.get("engine_overheat")) else TEXT_MUTED
                self.lbl_ot_status.setText(
                    f"Engine: {eng} ({cool:.0f}°C)  |  ARPA ghosts: {fakes}")
                self.lbl_ot_status.setStyleSheet(f"color: {col}; font-size: 11px; font-weight: bold;")
            else:
                self.lbl_ot_status.setText("Engine: nominal  |  ARPA: clear")
                self.lbl_ot_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")

        # Update Surface telemetry
        spoof_offset = state.get("spoof_offset_m")
        if active_atk == "gps_spoof" and spoof_offset:
            import math
            dist = math.hypot(spoof_offset[0], spoof_offset[1])
            self.lbl_gps_divergence.setText(f"Drift: {dist:.1f} m")
            self.lbl_gps_divergence.setStyleSheet(f"color: {COLOR_RED}; font-weight: bold; font-size: 11px;")

        cpa = state.get("cpa_m")
        tcpa = state.get("tcpa_s")
        if active_atk == "ais_spoof" and cpa is not None:
            cpa_nm = cpa / 1852.0
            risk = state.get("collision_risk", False)
            risk_color = COLOR_RED if risk else COLOR_AMBER
            self.lbl_ais_cpa.setText(f"CPA: {cpa:.0f}m ({cpa_nm:.2f}nm)  |  TCPA: {tcpa:.0f}s")
            self.lbl_ais_cpa.setStyleSheet(f"color: {risk_color}; font-weight: bold; font-size: 11px;")

        # Update Underwater telemetry
        usbl_bias = state.get("usbl_offset_m", 0.0)
        if active_atk == "acoustic_spoof":
            self.lbl_usbl_divergence.setText(f"Bias: {usbl_bias:.1f} m")
            self.lbl_usbl_divergence.setStyleSheet(f"color: {COLOR_RED}; font-weight: bold; font-size: 11px;")

        # Reset buttons if attack was stopped elsewhere
        if not active_atk:
            if self.btn_gps.isChecked():
                self.btn_gps.blockSignals(True)
                self.btn_gps.setChecked(False)
                self.btn_gps.setText("Inject GNSS Spoof")
                self.btn_gps.blockSignals(False)
            if self.btn_ais.isChecked():
                self.btn_ais.blockSignals(True)
                self.btn_ais.setChecked(False)
                self.btn_ais.setText("Inject Ghost Target")
                self.lbl_ais_status.setText("Standby")
                self.lbl_ais_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
                self.btn_ais.blockSignals(False)
            if self.btn_c2.isChecked():
                self.btn_c2.blockSignals(True)
                self.btn_c2.setChecked(False)
                self.btn_c2.setText("Inject C2 Override")
                self.lbl_c2_status.setText("Link: Authenticated")
                self.lbl_c2_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
                self.btn_c2.blockSignals(False)
            if self.btn_usbl.isChecked():
                self.btn_usbl.blockSignals(True)
                self.btn_usbl.setChecked(False)
                self.btn_usbl.setText("Inject USBL Bias")
                self.btn_usbl.blockSignals(False)
            if self.btn_ac_jam.isChecked():
                self.btn_ac_jam.blockSignals(True)
                self.btn_ac_jam.setChecked(False)
                self.btn_ac_jam.setText("Inject Blackout")
                self.lbl_ac_status.setText("Link: Clear Fix")
                self.lbl_ac_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
                self.btn_ac_jam.blockSignals(False)
            if self.btn_c2_sub.isChecked():
                self.btn_c2_sub.blockSignals(True)
                self.btn_c2_sub.setChecked(False)
                self.btn_c2_sub.setText("Inject Telecommand")
                self.lbl_c2_sub_status.setText("Command: Idle")
                self.lbl_c2_sub_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
                self.btn_c2_sub.blockSignals(False)
