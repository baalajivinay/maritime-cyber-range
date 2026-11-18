"""
Testbed Top Toolbar & Header.
Clean, intuitive control bar with vessel selection, location, start/stop, and status.
"""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt

from application.console.theme import (
    BG_PANEL_HEADER, BORDER_COLOR, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    COLOR_GREEN, COLOR_RED, COLOR_BLUE
)


class BAMHeaderWidget(QWidget):
    boot_requested = pyqtSignal()
    teardown_requested = pyqtSignal()
    arm_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(54)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_PANEL_HEADER};
                border-bottom: 1px solid {BORDER_COLOR};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(14)

        # 1. Main Title
        title = QLabel("Testbed")
        title.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {TEXT_PRIMARY}; letter-spacing: 0.5px;")
        layout.addWidget(title)

        # Subtle Vertical Divider
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet(f"color: {BORDER_COLOR};")
        layout.addWidget(sep1)

        # 2. Vessel Selector
        lbl_twin = QLabel("Vehicle:")
        lbl_twin.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: 500;")
        layout.addWidget(lbl_twin)

        self.twin_combo = QComboBox()
        self.twin_combo.addItem("Fast Interceptor USV", "interceptor_usv")
        self.twin_combo.addItem("Coastal Survey USV", "survey_usv")
        self.twin_combo.addItem("MT Andaman Tug", "mt_andaman_tug")
        self.twin_combo.addItem("Maya AUV (Underwater)", "maya_auv")
        self.twin_combo.addItem("AUV-150 (Underwater)", "auv150")
        self.twin_combo.setFixedWidth(200)
        layout.addWidget(self.twin_combo)

        # 3. Location Selector
        lbl_site = QLabel("Location:")
        lbl_site.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: 500;")
        layout.addWidget(lbl_site)

        self.site_combo = QComboBox()
        self.site_combo.addItem("Kochi Port (9.90°N, 76.20°E)", "kochi")
        self.site_combo.addItem("Mumbai Harbour (18.92°N, 72.80°E)", "mumbai")
        self.site_combo.addItem("Visakhapatnam (17.70°N, 83.30°E)", "visakhapatnam")
        self.site_combo.setFixedWidth(220)
        layout.addWidget(self.site_combo)

        layout.addSpacing(6)

        # 4. Start & Stop Buttons
        self.btn_boot = QPushButton("Start Testbed")
        self.btn_boot.setProperty("class", "success")
        self.btn_boot.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_GREEN};
                color: #ffffff;
                font-weight: 600;
                padding: 6px 16px;
                border-radius: 5px;
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
                padding: 6px 14px;
                border-radius: 5px;
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

        # 5. Status Indicators
        self.status_pill = QLabel("Ready")
        self.status_pill.setStyleSheet("""
            background-color: #2b2b36;
            color: #b0b0c0;
            border: 1px solid #3d3d4c;
            border-radius: 12px;
            padding: 4px 12px;
            font-size: 11px;
            font-weight: 600;
        """)
        layout.addWidget(self.status_pill)

        self.mode_pill = QLabel("MANUAL")
        self.mode_pill.setStyleSheet("""
            background-color: #2b2b36;
            color: #2f80ed;
            border: 1px solid #3d3d4c;
            border-radius: 12px;
            padding: 4px 12px;
            font-size: 11px;
            font-weight: 600;
        """)
        layout.addWidget(self.mode_pill)

        self.btn_arm = QPushButton("Arm Vehicle")
        self.btn_arm.setCheckable(True)
        self.btn_arm.setStyleSheet(f"""
            QPushButton {{
                background-color: #32323c;
                border: 1px solid {BORDER_COLOR};
                border-radius: 5px;
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

    def _on_arm_toggled(self, checked: bool):
        self.btn_arm.setText("Disarm" if checked else "Arm Vehicle")
        self.arm_toggled.emit(checked)

    def set_running_state(self, is_running: bool):
        if is_running:
            self.status_pill.setText("Running")
            self.status_pill.setStyleSheet("""
                background-color: rgba(39, 174, 96, 0.2);
                color: #27ae60;
                border: 1px solid #27ae60;
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 600;
            """)
            self.btn_boot.setEnabled(False)
            self.twin_combo.setEnabled(False)
            self.site_combo.setEnabled(False)
        else:
            self.status_pill.setText("Ready")
            self.status_pill.setStyleSheet("""
                background-color: #2b2b36;
                color: #b0b0c0;
                border: 1px solid #3d3d4c;
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 600;
            """)
            self.btn_boot.setEnabled(True)
            self.twin_combo.setEnabled(True)
            self.site_combo.setEnabled(True)

    def update_telemetry(self, state: dict):
        mode = state.get("mode", "MANUAL")
        self.mode_pill.setText(str(mode).upper())

        armed = state.get("armed", False)
        if armed != self.btn_arm.isChecked():
            self.btn_arm.blockSignals(True)
            self.btn_arm.setChecked(armed)
            self.btn_arm.setText("Disarm" if armed else "Arm Vehicle")
            self.btn_arm.blockSignals(False)
