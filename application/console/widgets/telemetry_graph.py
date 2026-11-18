"""
Testbed Sensor Innovation Residual (EKF3) Widget.
Clean real-time line chart showing Kalman Filter innovation residual (nu_k) and anomaly tripwires.
"""
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtCore import Qt, QPointF

from application.console.theme import (
    PANEL_BG, PANEL_BORDER, PANEL_HEADER, TEXT_WHITE, TEXT_MUTED,
    COLOR_RED, COLOR_AMBER, COLOR_GREEN, COLOR_BLUE
)


class TelemetryGraphPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Header Bar
        h_box = QHBoxLayout()
        lbl = QLabel("Sensor Innovation Residual (EKF3)")
        lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {TEXT_WHITE};")
        h_box.addWidget(lbl)

        self.lbl_status = QLabel("Normal (< 3.0m)")
        self.lbl_status.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {COLOR_GREEN};")
        h_box.addWidget(self.lbl_status)
        h_box.addStretch()

        layout.addLayout(h_box)

        # Graph Canvas
        self.canvas = GraphCanvas(self)
        layout.addWidget(self.canvas, 1)

    def update_telemetry(self, state: dict):
        active_atk = state.get("active_attack")
        spoof_offset = state.get("spoof_offset_m")

        if active_atk == "gps_spoof" and spoof_offset:
            import math
            residual = min(15.0, math.hypot(spoof_offset[0], spoof_offset[1]) * 0.45 + 1.2)
        elif active_atk:
            residual = 5.2
        else:
            residual = float(state.get("simulated_innovation") or 1.1)

        self.canvas.add_sample(residual)

        if residual >= 8.0:
            self.lbl_status.setText(f"TRIPPED: Residual {residual:.1f}m > 8.0m threshold")
            self.lbl_status.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {COLOR_RED};")
        elif residual >= 3.0:
            self.lbl_status.setText(f"WARNING: Residual {residual:.1f}m > 3.0m threshold")
            self.lbl_status.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {COLOR_AMBER};")
        else:
            self.lbl_status.setText(f"Normal (Residual {residual:.1f}m < 3.0m)")
            self.lbl_status.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {COLOR_GREEN};")


class GraphCanvas(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.samples = [1.1] * 60

    def add_sample(self, val: float):
        self.samples.append(val)
        if len(self.samples) > 60:
            self.samples.pop(0)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin_left = 38
        margin_bottom = 20
        plot_w = w - margin_left - 12
        plot_h = h - margin_bottom - 8

        # Background
        p.fillRect(self.rect(), QColor("#14151b"))
        p.setPen(QPen(QColor(PANEL_BORDER), 1))
        p.drawRect(margin_left, 8, plot_w, plot_h)

        max_val = 15.0
        p.setFont(QFont("-apple-system, sans-serif", 8))

        # 8.0m Tripwire Line (Red)
        y_alarm = int(8 + plot_h * (1.0 - 8.0 / max_val))
        p.setPen(QPen(QColor(COLOR_RED), 1, Qt.PenStyle.DashLine))
        p.drawLine(margin_left, y_alarm, margin_left + plot_w, y_alarm)
        p.setPen(QColor(COLOR_RED))
        p.drawText(6, y_alarm + 4, "8.0m")

        # 3.0m Warning Line (Amber)
        y_warn = int(8 + plot_h * (1.0 - 3.0 / max_val))
        p.setPen(QPen(QColor(COLOR_AMBER), 1, Qt.PenStyle.DashLine))
        p.drawLine(margin_left, y_warn, margin_left + plot_w, y_warn)
        p.setPen(QColor(COLOR_AMBER))
        p.drawText(6, y_warn + 4, "3.0m")

        # 0.0m Baseline
        y_base = int(8 + plot_h)
        p.setPen(QColor(TEXT_MUTED))
        p.drawText(6, y_base, "0.0m")

        if len(self.samples) < 2:
            return

        dx = plot_w / (len(self.samples) - 1)
        points = []
        for i, val in enumerate(self.samples):
            v_clamped = max(0.0, min(max_val, val))
            px = margin_left + i * dx
            py = 8 + plot_h * (1.0 - v_clamped / max_val)
            points.append(QPointF(px, py))

        for i in range(len(points) - 1):
            val = self.samples[i + 1]
            if val >= 8.0:
                p.setPen(QPen(QColor(COLOR_RED), 2))
            elif val >= 3.0:
                p.setPen(QPen(QColor(COLOR_AMBER), 2))
            else:
                p.setPen(QPen(QColor(COLOR_BLUE), 2))
            p.drawLine(points[i], points[i + 1])
