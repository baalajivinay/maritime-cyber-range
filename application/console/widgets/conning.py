"""
Testbed Telemetry Strip.
Clean, legible telemetry status cards for heading, speed, position, and propulsion.
"""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt

from application.console.theme import (
    BG_PANEL, BORDER_COLOR, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    COLOR_BLUE
)


class TelemetryItem(QFrame):
    def __init__(self, title: str, initial_val: str, unit: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_PANEL};
                border: 1px solid {BORDER_COLOR};
                border-radius: 6px;
                padding: 4px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; font-weight: 500;")
        layout.addWidget(self.lbl_title)

        val_box = QHBoxLayout()
        val_box.setSpacing(4)
        self.lbl_val = QLabel(initial_val)
        self.lbl_val.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {TEXT_PRIMARY};")
        val_box.addWidget(self.lbl_val)

        if unit:
            lbl_u = QLabel(unit)
            lbl_u.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY}; padding-top: 2px;")
            val_box.addWidget(lbl_u)

        val_box.addStretch()
        layout.addLayout(val_box)

    def set_value(self, text: str):
        self.lbl_val.setText(text)


class ConningPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(72)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.item_hdg = TelemetryItem("HEADING", "000.0°", "")
        layout.addWidget(self.item_hdg)

        self.item_speed = TelemetryItem("SPEED", "0.0", "kts")
        layout.addWidget(self.item_speed)

        self.item_lat = TelemetryItem("LATITUDE", "--.-----° N", "")
        layout.addWidget(self.item_lat)

        self.item_lon = TelemetryItem("LONGITUDE", "--.-----° E", "")
        layout.addWidget(self.item_lon)

        self.item_depth = TelemetryItem("DEPTH", "14.5", "m")
        layout.addWidget(self.item_depth)

        self.item_thrust = TelemetryItem("THROTTLE", "0", "%")
        layout.addWidget(self.item_thrust)

    def update_telemetry(self, state: dict):
        hdg = float(state.get("hdg") or 0.0)
        self.item_hdg.set_value(f"{hdg:05.1f}°")

        speed_mps = float(state.get("speed") or 0.0)
        speed_kts = speed_mps * 1.94384
        self.item_speed.set_value(f"{speed_kts:.1f}")

        lat = state.get("lat")
        lon = state.get("lon")
        if lat is not None:
            self.item_lat.set_value(f"{float(lat):.5f}° N")
        if lon is not None:
            self.item_lon.set_value(f"{float(lon):.5f}° E")

        depth = float(state.get("depth") or 0.0)
        domain = state.get("domain", "surface")
        if domain == "underwater":
            self.item_depth.set_value(f"{depth:.1f}")
        else:
            self.item_depth.set_value("14.5")

        armed = state.get("armed", False)
        thrust_pct = int(min(100, max(0, speed_mps / 3.5 * 100))) if armed else 0
        self.item_thrust.set_value(f"{thrust_pct}")
