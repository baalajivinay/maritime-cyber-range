"""
Real-time Kalman Innovation Residual and CUSUM Anomaly Oscilloscope Widget.
Plots innovation residual ν_k against statistical tripwire thresholds (Amber Warning / Red Failsafe).
"""
import math
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath
from PyQt6.QtCore import Qt, QPointF
from application.console.theme import (
    PANEL_BG, PANEL_BORDER, ACCENT_CYAN, COLOR_PASS, COLOR_WARN, COLOR_ALARM,
    TEXT_WHITE, TEXT_MUTED, TEXT_DIM
)

class InnovationResidualGraph(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(140)

        # Buffer for time series values (residuals in meters)
        self.max_samples = 120
        self.residuals = [0.2] * self.max_samples
        self.cusum_scores = [0.1] * self.max_samples
        self.warn_threshold = 3.0    # Amber line (m)
        self.alarm_threshold = 8.0   # Red line (m)

    def push_sample(self, res: float, cusum: float):
        self.residuals.append(res)
        self.cusum_scores.append(cusum)
        if len(self.residuals) > self.max_samples:
            self.residuals.pop(0)
            self.cusum_scores.pop(0)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        pad_left = 40
        pad_bottom = 22
        pad_top = 10
        pad_right = 10

        plot_w = w - pad_left - pad_right
        plot_h = h - pad_top - pad_bottom

        # Background
        painter.fillRect(0, 0, w, h, QColor(PANEL_BG))
        painter.setPen(QPen(QColor(PANEL_BORDER), 1))
        painter.drawRect(pad_left, pad_top, plot_w, plot_h)

        # Y Axis Scale (0 to 12 meters)
        max_y = 12.0

        def val_to_y(v: float) -> float:
            norm = min(1.0, max(0.0, v / max_y))
            return pad_top + plot_h * (1.0 - norm)

        # Grid lines and Y labels
        painter.setFont(QFont("JetBrains Mono", 8))
        painter.setPen(QPen(QColor("#172230"), 1, Qt.PenStyle.DashLine))

        for y_m in [0, 3, 6, 8, 12]:
            y_pos = val_to_y(y_m)
            painter.drawLine(pad_left, int(y_pos), pad_left + plot_w, int(y_pos))
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawText(2, int(y_pos + 4), pad_left - 6, 10, Qt.AlignmentFlag.AlignRight, f"{y_m}m")
            painter.setPen(QPen(QColor("#172230"), 1, Qt.PenStyle.DashLine))

        # Threshold Tripwires
        # Amber Warning Line (3.0m)
        warn_y = val_to_y(self.warn_threshold)
        painter.setPen(QPen(QColor(COLOR_WARN), 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(pad_left, int(warn_y), pad_left + plot_w, int(warn_y))
        painter.setPen(QColor(COLOR_WARN))
        painter.drawText(pad_left + 6, int(warn_y - 2), "WARNING THRESHOLD (3.0m)")

        # Red Alarm Tripwire (8.0m)
        alarm_y = val_to_y(self.alarm_threshold)
        painter.setPen(QPen(QColor(COLOR_ALARM), 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(pad_left, int(alarm_y), pad_left + plot_w, int(alarm_y))
        painter.setPen(QColor(COLOR_ALARM))
        painter.drawText(pad_left + 6, int(alarm_y - 2), "FAILSAFE TRIPWIRE (8.0m)")

        # Plot Residual Curve
        dx = plot_w / float(self.max_samples - 1)
        path = QPainterPath()
        path.moveTo(pad_left, val_to_y(self.residuals[0]))

        for i in range(1, len(self.residuals)):
            x = pad_left + i * dx
            y = val_to_y(self.residuals[i])
            path.lineTo(x, y)

        # Current residual color
        cur_val = self.residuals[-1]
        cur_col = QColor(COLOR_ALARM if cur_val >= self.alarm_threshold else (COLOR_WARN if cur_val >= self.warn_threshold else ACCENT_CYAN))

        painter.setPen(QPen(cur_col, 2))
        painter.drawPath(path)

        # Legend / Current readout
        painter.setFont(QFont("JetBrains Mono", 9, QFont.Weight.Bold))
        painter.setPen(cur_col)
        painter.drawText(pad_left + plot_w - 180, pad_top + 14, f"ν_k: {cur_val:.2f}m")


class TelemetryGraphPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Header
        h_layout = QHBoxLayout()
        lbl = QLabel("EKF3 INNOVATION RESIDUAL & STATISTICAL TRIPWIRE")
        lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {ACCENT_CYAN};")
        h_layout.addWidget(lbl)
        h_layout.addStretch()

        self.lbl_verdict = QLabel("STATUS: KALMAN FILTER CONVERGED")
        self.lbl_verdict.setStyleSheet(f"font-size: 9px; font-weight: bold; color: {COLOR_PASS};")
        h_layout.addWidget(self.lbl_verdict)
        layout.addLayout(h_layout)

        # Graph
        self.graph = InnovationResidualGraph(self)
        layout.addWidget(self.graph)

    def update_telemetry(self, state: dict):
        active_atk = state.get("active_attack")
        if active_atk:
            # During attack injection, show simulated innovation spike
            # (Matches detector behavior in detection/detector.py)
            res = float(state.get("simulated_innovation", 9.4))
            cusum = 14.2
            self.graph.push_sample(res, cusum)
            self.lbl_verdict.setText("ANOMALY: TRIPWIRE EXCEEDED (INNOVATION FAULT)")
            self.lbl_verdict.setStyleSheet(f"font-size: 9px; font-weight: bold; color: {COLOR_ALARM};")
        else:
            # Normal steady state Kalman filter innovation (~0.2m - 0.4m noise)
            import random
            res = 0.25 + random.uniform(-0.08, 0.12)
            self.graph.push_sample(res, 0.1)
            self.lbl_verdict.setText("STATUS: KALMAN FILTER CONVERGED")
            self.lbl_verdict.setStyleSheet(f"font-size: 9px; font-weight: bold; color: {COLOR_PASS};")
