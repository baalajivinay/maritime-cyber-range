"""
Conning Navigation Instruments Widget.
Features the marine gyro compass rose, rudder indicator, rate of turn, speed, and depth.
"""
import math
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
)
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF
from PyQt6.QtCore import Qt, QPointF

from application.console.theme import (
    PANEL_BG, PANEL_BORDER, PANEL_HEADER, COLOR_BLUE, COLOR_GREEN, COLOR_AMBER,
    COLOR_RED, COLOR_CARDINAL_N, TEXT_WHITE, TEXT_MUTED, TEXT_DIM
)


class CompassRoseWidget(QWidget):
    """Clean marine gyro compass rose with rotating card and digital heading."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(164, 164)
        self.heading = 0.0

    def set_heading(self, hdg: float):
        self.heading = hdg % 360.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        radius = int(min(cx, cy) - 8)

        # Background Dial
        painter.setPen(QPen(QColor(PANEL_BORDER), 1.5))
        painter.setBrush(QBrush(QColor("#13151b")))
        painter.drawEllipse(QPointF(cx, cy), float(radius), float(radius))

        # Rotating Compass Dial
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self.heading)

        font_cardinal = QFont("-apple-system, sans-serif", 8, QFont.Weight.Bold)
        font_minor = QFont("-apple-system, sans-serif", 6)

        for deg in range(0, 360, 10):
            painter.save()
            painter.rotate(deg)

            if deg % 90 == 0:
                painter.setPen(QPen(QColor(COLOR_CARDINAL_N if deg == 0 else TEXT_WHITE), 2))
                painter.drawLine(0, -radius, 0, -radius + 11)
                painter.setFont(font_cardinal)
                lbl = {0: "N", 90: "E", 180: "S", 270: "W"}[deg]
                painter.setPen(QColor(COLOR_CARDINAL_N if deg == 0 else TEXT_WHITE))
                painter.drawText(-10, -radius + 22, 20, 12, Qt.AlignmentFlag.AlignCenter, lbl)
            elif deg % 30 == 0:
                painter.setPen(QPen(QColor(TEXT_MUTED), 1.2))
                painter.drawLine(0, -radius, 0, -radius + 7)
                painter.setFont(font_minor)
                painter.drawText(-15, -radius + 18, 30, 10, Qt.AlignmentFlag.AlignCenter, f"{deg:03d}")
            else:
                painter.setPen(QPen(QColor(TEXT_DIM), 1))
                painter.drawLine(0, -radius, 0, -radius + 4)

            painter.restore()

        painter.restore()

        # Fixed Top Lubber Line (Ship's Head)
        painter.setPen(QPen(QColor(COLOR_RED), 2))
        painter.drawLine(int(cx), int(cy - radius - 3), int(cx), int(cy - radius + 8))

        # Own-Ship Pointer in Center
        painter.save()
        painter.translate(cx, cy)
        ship_poly = QPolygonF([
            QPointF(0, -20),
            QPointF(7, 12),
            QPointF(0, 5),
            QPointF(-7, 12)
        ])
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.setBrush(QBrush(QColor(COLOR_BLUE)))
        painter.drawPolygon(ship_poly)
        painter.restore()

        # Digital Readout Box at Bottom Center of Compass
        box_w, box_h = 60, 18
        bx = int(cx - box_w / 2)
        by = int(cy + 26)
        painter.setPen(QPen(QColor(PANEL_BORDER), 1))
        painter.setBrush(QBrush(QColor(20, 22, 28, 220)))
        painter.drawRoundedRect(bx, by, box_w, box_h, 3, 3)

        painter.setPen(QColor(TEXT_WHITE))
        painter.setFont(QFont("-apple-system, sans-serif", 9, QFont.Weight.Bold))
        painter.drawText(bx, by, box_w, box_h, Qt.AlignmentFlag.AlignCenter, f"{self.heading:05.1f}°")


class RudderAngleWidget(QWidget):
    """Clean horizontal rudder indicator (PORT 35° <---> STBD 35°)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self.angle = 0.0

    def set_angle(self, ang: float):
        self.angle = max(-35.0, min(35.0, ang))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        mid_x = w / 2.0

        # Background track
        slot_y = 16
        slot_h = 8
        painter.setPen(QPen(QColor(PANEL_BORDER), 1))
        painter.setBrush(QBrush(QColor("#13151b")))
        painter.drawRoundedRect(10, slot_y, w - 20, slot_h, 3, 3)

        # Center line (0°)
        painter.setPen(QPen(QColor(TEXT_MUTED), 1))
        painter.drawLine(int(mid_x), slot_y - 2, int(mid_x), slot_y + slot_h + 2)

        # Deflection bar
        max_px = (w - 20) / 2.0
        bar_len = (self.angle / 35.0) * max_px

        if abs(bar_len) > 1.0:
            color = COLOR_RED if self.angle < 0 else COLOR_GREEN
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(color)))
            if self.angle < 0:
                painter.drawRect(int(mid_x + bar_len), slot_y + 1, int(-bar_len), slot_h - 2)
            else:
                painter.drawRect(int(mid_x), slot_y + 1, int(bar_len), slot_h - 2)

        # Text labels
        painter.setFont(QFont("-apple-system, sans-serif", 8))
        painter.setPen(QColor(COLOR_RED))
        painter.drawText(10, slot_y - 4, "PORT 35°")

        painter.setPen(QColor(COLOR_GREEN))
        painter.drawText(int(w - 65), slot_y - 4, "STBD 35°")

        # Current angle readout in center
        painter.setPen(QColor(TEXT_WHITE))
        dir_char = "P" if self.angle < 0 else ("S" if self.angle > 0 else "")
        painter.drawText(0, slot_y + slot_h + 12, w, 12, Qt.AlignmentFlag.AlignCenter, f"{abs(self.angle):.1f}° {dir_char}")


class ConningPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "panel")
        self.setFixedWidth(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Section Header
        lbl_head = QLabel("Navigation Instruments")
        lbl_head.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_WHITE};")
        layout.addWidget(lbl_head)

        # Gyro Compass Rose
        comp_container = QHBoxLayout()
        comp_container.addStretch()
        self.compass = CompassRoseWidget(self)
        comp_container.addWidget(self.compass)
        comp_container.addStretch()
        layout.addLayout(comp_container)

        # Rudder Indicator
        lbl_rudder = QLabel("RUDDER ANGLE")
        lbl_rudder.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {TEXT_MUTED}; margin-top: 4px;")
        layout.addWidget(lbl_rudder)
        self.rudder = RudderAngleWidget(self)
        layout.addWidget(self.rudder)

        # Telemetry Metrics Grid
        grid_frame = QFrame()
        grid_frame.setStyleSheet(f"background-color: {PANEL_HEADER}; border-radius: 4px; padding: 6px;")
        grid_layout = QVBoxLayout(grid_frame)
        grid_layout.setContentsMargins(8, 6, 8, 6)
        grid_layout.setSpacing(6)

        # Speed (SOG)
        self.lbl_sog = self._create_metric_row(grid_layout, "Speed (SOG):", "0.0 kts (0.0 m/s)")
        # Depth
        self.lbl_depth = self._create_metric_row(grid_layout, "Depth (UKC):", "14.5 m (UKC 11.2m)")
        # Rate of Turn
        self.lbl_rot = self._create_metric_row(grid_layout, "Rate of Turn:", "+0.0 °/min")
        # Position
        self.lbl_lat = self._create_metric_row(grid_layout, "Latitude:", "09.90000° N")
        self.lbl_lon = self._create_metric_row(grid_layout, "Longitude:", "076.20000° E")

        layout.addWidget(grid_frame)

        # Propulsion Bar
        lbl_thrust = QLabel("PROPULSION LOAD")
        lbl_thrust.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {TEXT_MUTED}; margin-top: 2px;")
        layout.addWidget(lbl_thrust)

        self.thrust_bar = QProgressBar()
        self.thrust_bar.setRange(0, 100)
        self.thrust_bar.setValue(0)
        self.thrust_bar.setFixedHeight(12)
        self.thrust_bar.setTextVisible(False)
        self.thrust_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #13151b;
                border: 1px solid {PANEL_BORDER};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_BLUE};
            }}
        """)
        layout.addWidget(self.thrust_bar)

        self.lbl_power = QLabel("24.0 V  |  0.0 A  |  0 RPM")
        self.lbl_power.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED}; text-align: center;")
        self.lbl_power.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_power)

        layout.addStretch()

    def _create_metric_row(self, layout, label_text, default_val):
        row = QHBoxLayout()
        row.setSpacing(4)
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; font-weight: 500;")
        val = QLabel(default_val)
        val.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {TEXT_WHITE};")
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(val)
        layout.addLayout(row)
        return val

    def update_telemetry(self, state: dict):
        hdg = float(state.get("hdg") or 0.0)
        self.compass.set_heading(hdg)

        speed_mps = float(state.get("speed") or 0.0)
        speed_kts = float(state.get("speed_knots") or (speed_mps * 1.94384))
        self.lbl_sog.setText(f"{speed_kts:.1f} kts ({speed_mps:.1f} m/s)")

        depth = float(state.get("depth") or 0.0)
        domain = state.get("domain", "surface")
        if domain == "underwater":
            alt = float(state.get("altitude") or 25.0)
            self.lbl_depth.setText(f"{depth:.1f}m (ALT {alt:.1f}m)")
        else:
            self.lbl_depth.setText("14.5 m (UKC 11.2m)")

        lat = state.get("lat")
        lon = state.get("lon")
        if lat is not None:
            self.lbl_lat.setText(f"{float(lat):.5f}° N")
        if lon is not None:
            self.lbl_lon.setText(f"{float(lon):.5f}° E")

        rot = float(state.get("rot_deg_min") or state.get("rot") or 0.0)
        self.lbl_rot.setText(f"{rot:+.1f} °/min")

        rudder_deg = float(state.get("rudder_angle") or state.get("rudder") or 0.0)
        self.rudder.set_angle(rudder_deg)

        armed = state.get("armed", False)
        throttle = float(state.get("throttle_pct") or 0.0)
        if not armed:
            throttle = 0.0
        self.thrust_bar.setValue(int(min(100, max(0, throttle))))

        volts = 24.2 - (throttle * 0.015)
        amps = throttle * 0.42
        rpm = int(throttle * 22)
        self.lbl_power.setText(f"{volts:.1f} V | {amps:.1f} A | {rpm} RPM")
