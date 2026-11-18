"""
Bridge Alert Management (BAM) & Testbed Mission Header (IEC 62288 Conformance).
"""
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QComboBox, QPushButton
)
from PyQt6.QtCore import pyqtSignal, Qt
from application.console.theme import (
    PANEL_BG, PANEL_BORDER, ACCENT_CYAN, COLOR_PASS, COLOR_WARN, COLOR_ALARM, TEXT_WHITE, TEXT_MUTED
)

class BAMHeaderWidget(QFrame):
    boot_requested = pyqtSignal(str, str)     # site_id, twin_id
    teardown_requested = pyqtSignal()
    arm_requested = pyqtSignal()
    disarm_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bam_header")
        self.setStyleSheet(f"""
            QFrame#bam_header {{
                background-color: {PANEL_BG};
                border-bottom: 2px solid {PANEL_BORDER};
                padding: 4px 12px;
            }}
        """)
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(14)

        # Title Block
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel("MCR TACTICAL TESTBED")
        title.setStyleSheet(f"font-size: 14px; font-weight: 800; color: {ACCENT_CYAN}; letter-spacing: 1px;")
        sub = QLabel("IACS UR E26 / E27 & DNV-ST-0373 CYBER RESILIENCE SUITE")
        sub.setStyleSheet(f"font-size: 9px; font-weight: 600; color: {TEXT_MUTED}; letter-spacing: 0.5px;")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        layout.addLayout(title_box)

        layout.addSpacing(15)

        # Site Selector
        lbl_site = QLabel("SITE:")
        lbl_site.setStyleSheet(f"color: {TEXT_MUTED}; font-weight: bold; font-size: 11px;")
        layout.addWidget(lbl_site)

        self.site_combo = QComboBox()
        self.site_combo.addItem("Mumbai Harbour Approaches (18.92°N, 72.80°E)", "mumbai")
        self.site_combo.addItem("Kochi Port Channel (9.90°N, 76.20°E)", "kochi")
        self.site_combo.addItem("Visakhapatnam Roadstead (17.70°N, 83.30°E)", "visakhapatnam")
        self.site_combo.setFixedWidth(270)
        layout.addWidget(self.site_combo)

        # Vehicle Twin Selector
        lbl_twin = QLabel("VESSEL TWIN:")
        lbl_twin.setStyleSheet(f"color: {TEXT_MUTED}; font-weight: bold; font-size: 11px;")
        layout.addWidget(lbl_twin)

        self.twin_combo = QComboBox()
        self.twin_combo.addItem("MT Andaman Tug (30m Autonomous)", "mt_andaman_tug")
        self.twin_combo.addItem("Fast Interceptor USV (Naval CUSV)", "interceptor_usv")
        self.twin_combo.addItem("Coastal Survey USV (Catamaran)", "survey_usv")
        self.twin_combo.addItem("Maya AUV (Subsea Autonomous)", "maya_auv")
        self.twin_combo.addItem("AUV-150 (Deep Exploration)", "auv150")
        self.twin_combo.setFixedWidth(240)
        layout.addWidget(self.twin_combo)

        layout.addSpacing(10)

        # Autopilot Mode / Arm Pills
        self.pill_mode = QLabel("MODE: --")
        self.pill_mode.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pill_mode.setFixedSize(110, 26)
        self.pill_mode.setStyleSheet("background-color: #17202E; border: 1px solid #2B3A4E; border-radius: 3px; font-weight: bold; font-size: 10px;")
        layout.addWidget(self.pill_mode)

        self.pill_arm = QLabel("SAFE (DISARMED)")
        self.pill_arm.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pill_arm.setFixedSize(130, 26)
        self.pill_arm.setStyleSheet(f"background-color: #064E3B; border: 1px solid {COLOR_PASS}; color: #A7F3D0; border-radius: 3px; font-weight: bold; font-size: 10px;")
        layout.addWidget(self.pill_arm)

        # EKF3 Health Status Pill
        self.pill_ekf = QLabel("EKF3: CONVERGED")
        self.pill_ekf.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pill_ekf.setFixedSize(130, 26)
        self.pill_ekf.setStyleSheet(f"background-color: #064E3B; border: 1px solid {COLOR_PASS}; color: #A7F3D0; border-radius: 3px; font-weight: bold; font-size: 10px;")
        layout.addWidget(self.pill_ekf)

        layout.addStretch()

        # Primary Control Buttons
        self.btn_boot = QPushButton("BOOT SITL & TESTBED")
        self.btn_boot.setProperty("class", "btn-primary")
        self.btn_boot.setFixedHeight(30)
        self.btn_boot.clicked.connect(self._on_boot_clicked)
        layout.addWidget(self.btn_boot)

        self.btn_teardown = QPushButton("STOP")
        self.btn_teardown.setFixedHeight(30)
        self.btn_teardown.clicked.connect(self.teardown_requested.emit)
        layout.addWidget(self.btn_teardown)

    def _on_boot_clicked(self):
        site_id = self.site_combo.currentData()
        twin_id = self.twin_combo.currentData()
        self.boot_requested.emit(site_id, twin_id)

    def update_telemetry(self, state: dict, connected: bool, booting: bool):
        if booting:
            self.pill_mode.setText("BOOTING SITL...")
            self.pill_mode.setStyleSheet("background-color: #451A03; border: 1px solid #F59E0B; color: #FDE68A; border-radius: 3px; font-weight: bold; font-size: 10px;")
            self.btn_boot.setEnabled(False)
            return

        self.btn_boot.setEnabled(True)
        if not connected:
            self.pill_mode.setText("STANDBY")
            self.pill_mode.setStyleSheet("background-color: #17202E; border: 1px solid #2B3A4E; color: #94A3B8; border-radius: 3px; font-weight: bold; font-size: 10px;")
            self.pill_arm.setText("OFFLINE")
            self.pill_arm.setStyleSheet("background-color: #1E293B; border: 1px solid #334155; color: #64748B; border-radius: 3px; font-weight: bold; font-size: 10px;")
            self.pill_ekf.setText("EKF3: WAITING")
            self.pill_ekf.setStyleSheet("background-color: #1E293B; border: 1px solid #334155; color: #64748B; border-radius: 3px; font-weight: bold; font-size: 10px;")
            return

        mode = state.get("mode", "MANUAL")
        self.pill_mode.setText(f"MODE: {mode}")
        self.pill_mode.setStyleSheet(f"background-color: #0F2942; border: 1px solid {ACCENT_CYAN}; color: {TEXT_WHITE}; border-radius: 3px; font-weight: bold; font-size: 10px;")

        armed = state.get("armed", False)
        if armed:
            self.pill_arm.setText("ARMED (LIVE)")
            self.pill_arm.setStyleSheet(f"background-color: #7F1D1D; border: 1px solid {COLOR_ALARM}; color: #FEE2E2; border-radius: 3px; font-weight: bold; font-size: 10px;")
        else:
            self.pill_arm.setText("SAFE (DISARMED)")
            self.pill_arm.setStyleSheet(f"background-color: #064E3B; border: 1px solid {COLOR_PASS}; color: #A7F3D0; border-radius: 3px; font-weight: bold; font-size: 10px;")

        # Active cyber attack status overrides EKF pill
        active_atk = state.get("active_attack")
        if active_atk:
            self.pill_ekf.setText(f"ALERT: {active_atk.upper()}")
            self.pill_ekf.setStyleSheet(f"background-color: #7F1D1D; border: 1px solid {COLOR_ALARM}; color: #FEE2E2; border-radius: 3px; font-weight: bold; font-size: 10px;")
        else:
            self.pill_ekf.setText("EKF3: CONVERGED")
            self.pill_ekf.setStyleSheet(f"background-color: #064E3B; border: 1px solid {COLOR_PASS}; color: #A7F3D0; border-radius: 3px; font-weight: bold; font-size: 10px;")
