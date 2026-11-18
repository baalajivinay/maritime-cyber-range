"""
Conning Information Display (CID) Widget conforming to IEC 62288.
Draws gyro compass rose, rate of turn, rudder angle, speed meters, and thruster feedback.
"""
import math
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
)
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from application.console.theme import (
    PANEL_BG, PANEL_BORDER, ACCENT_CYAN, COLOR_PASS, COLOR_WARN, COLOR_ALARM,
    TEXT_WHITE, TEXT_MUTED, TEXT_DIM
)

class CompassRoseWidget(QWidget):
    """Custom drawn marine gyro compass rose with rotating dial."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(170, 170)
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
        radius = int(min(cx, cy) - 10)

        # Background circle
        painter.setPen(QPen(QColor(PANEL_BORDER), 2))
        painter.setBrush(QBrush(QColor("#080D14")))
        painter.drawEllipse(QPointF(cx, cy), float(radius), float(radius))

        # Draw compass tick marks
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self.heading)

        font_cardinal = QFont("Inter", 8, QFont.Weight.Bold)
        font_minor = QFont("Inter", 6)

        for deg in range(0, 360, 10):
            painter.save()
            painter.rotate(deg)

            if deg % 90 == 0:
                painter.setPen(QPen(QColor(ACCENT_CYAN), 2))
                painter.drawLine(0, -radius, 0, -radius + 12)
                # Cardinal label
                painter.setFont(font_cardinal)
                lbl = {0: "N", 90: "E", 180: "S", 270: "W"}[deg]
                painter.setPen(QColor(TEXT_WHITE if deg != 0 else COLOR_ALARM))
                painter.drawText(-10, -radius + 24, 20, 12, Qt.AlignmentFlag.AlignCenter, lbl)
            elif deg % 30 == 0:
                painter.setPen(QPen(QColor(TEXT_MUTED), 1.5))
                painter.drawLine(0, -radius, 0, -radius + 8)
                painter.setFont(font_minor)
                painter.drawText(-15, -radius + 20, 30, 10, Qt.AlignmentFlag.AlignCenter, f"{deg:03d}")
            else:
                painter.setPen(QPen(QColor(TEXT_DIM), 1))
                painter.drawLine(0, -radius, 0, -radius + 5)

            painter.restore()

        painter.restore()

        # Fixed top Lubber Line (Ship's Head Pointer)
        painter.setPen(QPen(QColor(COLOR_ALARM), 2))
        painter.drawLine(int(cx), int(cy - radius - 5), int(cx), int(cy - radius + 10))

        # Center Own-Ship Needle
        painter.setBrush(QBrush(QColor(ACCENT_CYAN)))
        painter.setPen(QPen(QColor(TEXT_WHITE), 1))
        ship_poly = QPolygonF([
            QPointF(cx, cy - 24),
            QPointF(cx + 8, cy + 16),
            QPointF(cx, cy + 8),
            QPointF(cx - 8, cy + 16)
        ])
        painter.drawPolygon(ship_poly)

        # Heading Digital Readout Box in Center
        painter.setPen(QPen(QColor(PANEL_BORDER), 1))
        painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
        painter.drawRect(int(cx - 32), int(cy + 28), 64, 20)
        painter.setPen(QColor(ACCENT_CYAN))
        painter.setFont(QFont("JetBrains Mono", 10, QFont.Weight.Bold))
        painter.drawText(int(cx - 32), int(cy + 28), 64, 20, Qt.AlignmentFlag.AlignCenter, f"{self.heading:05.1f}°")


class RudderAngleWidget(QWidget):
    """Dual horizontal rudder indicator (PORT 35° <---> STBD 35°)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
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

        # Background slot
        slot_y = 18
        slot_h = 10
        painter.setPen(QPen(QColor(PANEL_BORDER), 1))
        painter.setBrush(QBrush(QColor("#080D14")))
        painter.drawRoundedRect(10, slot_y, w - 20, slot_h, 2, 2)

        # Center line (0°)
        painter.setPen(QPen(QColor(TEXT_MUTED), 2))
        painter.drawLine(int(mid_x), slot_y - 4, int(mid_x), slot_y + slot_h + 4)

        # Draw fill bar
        bar_len = (self.angle / 35.0) * (mid_x - 15)
        if bar_len > 0:
            painter.setBrush(QBrush(QColor(COLOR_PASS)))  # STBD Green
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(int(mid_x), slot_y + 1, int(bar_len), slot_h - 2)
        elif bar_len < 0:
            painter.setBrush(QBrush(QColor(COLOR_ALARM))) # PORT Red
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(int(mid_x + bar_len), slot_y + 1, int(-bar_len), slot_h - 2)

        # Labels
        painter.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        painter.setPen(QColor(COLOR_ALARM))
        painter.drawText(10, 12, "PORT 35°")
        painter.setPen(QColor(COLOR_PASS))
        painter.drawText(w - 70, 12, "35° STBD")

        painter.setFont(QFont("JetBrains Mono", 9, QFont.Weight.Bold))
        side = "P" if self.angle < -0.1 else ("S" if self.angle > 0.1 else "MID")
        painter.setPen(QColor(TEXT_WHITE))
        painter.drawText(int(mid_x - 30), slot_y + slot_h + 14, 60, 12, Qt.AlignmentFlag.AlignCenter, f"{abs(self.angle):04.1f}° {side}")


class ConningPanel(QFrame):
    """Main Conning Instrumentation Panel conforming to IEC 62288."""
    arm_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "panel")
        self.setFixedWidth(290)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Header
        lbl_head = QLabel("CONNING INSTRUMENTATION")
        lbl_head.setStyleSheet(f"font-weight: 800; font-size: 11px; color: {ACCENT_CYAN}; letter-spacing: 0.8px;")
        layout.addWidget(lbl_head)

        # Gyro Compass Rose
        comp_box = QHBoxLayout()
        comp_box.addStretch()
        self.compass = CompassRoseWidget()
        comp_box.addWidget(self.compass)
        comp_box.addStretch()
        layout.addLayout(comp_box)

        # Rudder Angle
        layout.addWidget(QLabel("RUDDER ANGLE / STEERING"))
        self.rudder = RudderAngleWidget()
        layout.addWidget(self.rudder)

        # Metrics Grid (Speed, Rate of Turn, Depth, Position)
        self.lbl_sog = self._create_metric_row("SPEED OVER GROUND (SOG):", "0.00 m/s (0.0 kts)", layout)
        self.lbl_rot = self._create_metric_row("RATE OF TURN (ROT):", "0.0 °/min", layout)
        self.lbl_depth = self._create_metric_row("DEPTH / UNDER-KEEL:", "14.2 m (UKC: 10.4 m)", layout)
        self.lbl_lat = self._create_metric_row("LATITUDE:", "18.92000° N", layout)
        self.lbl_lon = self._create_metric_row("LONGITUDE:", "72.80000° E", layout)

        # Thruster / Propulsion Bar
        layout.addWidget(QLabel("PROPULSION LOAD / THRUST"))
        self.thrust_bar = QProgressBar()
        self.thrust_bar.setRange(0, 100)
        self.thrust_bar.setValue(0)
        self.thrust_bar.setFixedHeight(12)
        self.thrust_bar.setTextVisible(False)
        self.thrust_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #080D14;
                border: 1px solid {PANEL_BORDER};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {ACCENT_CYAN};
            }}
        """)
        layout.addWidget(self.thrust_bar)

        self.lbl_power = QLabel("24.2 V | 0.0 A | 0 RPM")
        self.lbl_power.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED}; font-family: monospace;")
        layout.addWidget(self.lbl_power)

        layout.addStretch()

        # Arming Controls
        btn_box = QHBoxLayout()
        self.btn_arm = QPushButton("ARM PROPULSION")
        self.btn_arm.setProperty("class", "btn-primary")
        self.btn_arm.clicked.connect(lambda: self.arm_toggled.emit(True))
        btn_box.addWidget(self.btn_arm)

        self.btn_disarm = QPushButton("DISARM")
        self.btn_disarm.clicked.connect(lambda: self.arm_toggled.emit(False))
        btn_box.addWidget(self.btn_disarm)
        layout.addLayout(btn_box)

    def _create_metric_row(self, title: str, default_val: str, layout: QVBoxLayout) -> QLabel:
        row = QHBoxLayout()
        t = QLabel(title)
        t.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED}; font-weight: 600;")
        val = QLabel(default_val)
        val.setStyleSheet("font-size: 11px; font-weight: bold; font-family: 'JetBrains Mono', monospace;")
        val.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(t)
        row.addWidget(val)
        layout.addLayout(row)
        return val

    def update_telemetry(self, state: dict):
        hdg = float(state.get("hdg") or 0.0)
        self.compass.set_heading(hdg)

        speed = float(state.get("speed") or 0.0)
        kts = speed * 1.94384
        self.lbl_sog.setText(f"{speed:.2f} m/s ({kts:.1f} kts)")

        depth = float(state.get("depth") or 0.0)
        domain = state.get("domain", "surface")
        if domain == "underwater":
            self.lbl_depth.setText(f"{depth:.1f} m DEPTH")
        else:
            self.lbl_depth.setText(f"14.5 m (UKC: 11.2 m)")

        lat = state.get("lat")
        lon = state.get("lon")
        if lat is not None and lon is not None:
            self.lbl_lat.setText(f"{float(lat):.5f}° N")
            self.lbl_lon.setText(f"{float(lon):.5f}° E")

        # Mock / computed rudder and thrust from speed & turn
        rot = float(state.get("rot") or 0.0)
        self.lbl_rot.setText(f"{rot:+.1f} °/min")
        self.rudder.set_angle(float(state.get("rudder") or 0.0))

        pwm = int(min(100, max(0, speed / 3.5 * 100))) if state.get("armed") else 0

        self.thrust_bar.setValue(pwm)
        volts = 24.2 - (pwm * 0.02)
        amps = pwm * 0.35
        self.lbl_power.setText(f"{volts:.1f} V | {amps:.1f} A | {pwm * 18} RPM")
