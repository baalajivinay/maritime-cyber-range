"""
Tactical 2D Vector Nautical Chart (ECDIS Canvas conforming to IEC 61174 & IEC 62288).
Renders bathymetry, fairway, buoys, true own-ship position, spoofed ghost divergence, and interactive waypoint routing.
"""
import math
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QPainterPath
)
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from application.console.theme import (
    CHART_WATER_DEEP, CHART_WATER_SHALLOW, CHART_WATER_FAIRWAY, CHART_LAND,
    CHART_GRID, CHART_BUOY_PORT, CHART_BUOY_STBD, CHART_TRUE_VESSEL,
    CHART_SPOOFED_GHOST, CHART_WAYPOINT, TEXT_WHITE, TEXT_MUTED, COLOR_ALARM, COLOR_WARN,
    PANEL_BORDER
)

DEG_TO_M = 111320.0

class TacticalECDISWidget(QWidget):
    waypoint_selected = pyqtSignal(float, float)   # lat, lon

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(450, 400)

        # Map state (origin coordinates)
        self.center_lat = 18.92000
        self.center_lon = 72.80000
        self.scale_px_per_m = 0.85    # Zoom scale (pixels per meter)
        self.pan_offset = QPointF(0, 0)
        self.dragging = False
        self.drag_start = QPointF(0, 0)

        # Vehicle & Telemetry
        self.true_pos = (0.0, 0.0)      # East, North (m) relative to center
        self.true_hdg = 0.0
        self.spoofed_pos = None          # East, North (m) during attack
        self.waypoint = None             # East, North (m)
        self.waypoint_latlon = None
        self.trail = []                  # History of true positions [(E, N), ...]
        self.speed = 0.0
        self.active_attack = ""

        # Navigational Aids (Buoys around harbour in local meters East, North)
        self.buoys = [
            (80.0, 60.0, "port"), (-100.0, 90.0, "stbd"),
            (180.0, 160.0, "port"), (-160.0, 200.0, "stbd"),
            (50.0, 280.0, "port"), (-120.0, 320.0, "stbd"),
            (220.0, -90.0, "port"), (-190.0, -110.0, "stbd"),
            (10.0, 150.0, "fairway"), (0.0, 250.0, "fairway")
        ]

    def set_origin(self, lat: float, lon: float):
        self.center_lat = lat
        self.center_lon = lon
        self.trail.clear()
        self.waypoint = None
        self.update()

    def update_telemetry(self, state: dict):
        lat = state.get("lat")
        lon = state.get("lon")
        hdg = float(state.get("hdg") or 0.0)
        self.speed = float(state.get("speed") or 0.0)

        self.true_hdg = hdg
        self.active_attack = state.get("active_attack", "")

        if lat is not None and lon is not None:
            # Convert Lat/Lon to meters East, North from center
            d_north = (float(lat) - self.center_lat) * DEG_TO_M
            d_east = (float(lon) - self.center_lon) * DEG_TO_M * math.cos(math.radians(self.center_lat))
            self.true_pos = (d_east, d_north)

            # Record trail
            if not self.trail or math.hypot(d_east - self.trail[-1][0], d_north - self.trail[-1][1]) > 2.0:
                self.trail.append((d_east, d_north))
                if len(self.trail) > 150:
                    self.trail.pop(0)

            # Check if attack injected spoofed offset
            spoof_offset = state.get("spoof_offset_m")
            if spoof_offset:
                self.spoofed_pos = (d_east + spoof_offset[0], d_north + spoof_offset[1])
            elif "gps" in self.active_attack.lower():
                # Visual synthetic walk-off divergence during active attack test
                self.spoofed_pos = (d_east + 18.5, d_north - 12.0)
            else:
                self.spoofed_pos = None

        self.update()

    # Coordinate transformation helpers
    def _world_to_screen(self, east: float, north: float) -> QPointF:
        cx = self.width() / 2.0 + self.pan_offset.x()
        cy = self.height() / 2.0 + self.pan_offset.y()
        sx = cx + (east * self.scale_px_per_m)
        sy = cy - (north * self.scale_px_per_m)   # North is up (screen -Y)
        return QPointF(sx, sy)

    def _screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        cx = self.width() / 2.0 + self.pan_offset.x()
        cy = self.height() / 2.0 + self.pan_offset.y()
        east = (sx - cx) / self.scale_px_per_m
        north = -(sy - cy) / self.scale_px_per_m
        return east, north

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # 1. Bathymetric Background
        painter.fillRect(0, 0, w, h, QColor(CHART_WATER_DEEP))

        # Navigable Fairway / Deep Water Channel (diagonal corridor)
        fairway_poly = QPolygonF([
            self._world_to_screen(-140, -400),
            self._world_to_screen(140, -400),
            self._world_to_screen(180, 500),
            self._world_to_screen(-100, 500)
        ])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(CHART_WATER_FAIRWAY)))
        painter.drawPolygon(fairway_poly)

        # 2. Distance Range Rings (50m, 100m, 200m, 400m from vessel)
        cx, cy = self._world_to_screen(self.true_pos[0], self.true_pos[1]).x(), self._world_to_screen(self.true_pos[0], self.true_pos[1]).y()
        painter.setPen(QPen(QColor(CHART_GRID), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setFont(QFont("Inter", 8))

        for r_m in [50, 100, 200, 400]:
            r_px = r_m * self.scale_px_per_m
            painter.drawEllipse(QPointF(cx, cy), r_px, r_px)
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawText(int(cx + r_px + 4), int(cy), f"{r_m}m")
            painter.setPen(QPen(QColor(CHART_GRID), 1, Qt.PenStyle.DashLine))

        # 3. Nautical Buoys (Lateral Marks)
        for be, bn, btype in self.buoys:
            pt = self._world_to_screen(be, bn)
            if btype == "port":
                col = QColor(CHART_BUOY_PORT)
                painter.setBrush(QBrush(col))
                painter.setPen(QPen(QColor("#FFFFFF"), 1))
                painter.drawRect(int(pt.x() - 4), int(pt.y() - 4), 8, 8)  # Can mark
            elif btype == "stbd":
                col = QColor(CHART_BUOY_STBD)
                painter.setBrush(QBrush(col))
                painter.setPen(QPen(QColor("#FFFFFF"), 1))
                poly = QPolygonF([QPointF(pt.x(), pt.y() - 6), QPointF(pt.x() - 5, pt.y() + 4), QPointF(pt.x() + 5, pt.y() + 4)])
                painter.drawPolygon(poly) # Conical mark
            else:
                col = QColor(CHART_WAYPOINT)
                painter.setBrush(QBrush(col))
                painter.setPen(QPen(QColor("#FFFFFF"), 1))
                painter.drawEllipse(pt, 3, 3)

        # 4. Historical Track Trail
        if len(self.trail) > 1:
            painter.setPen(QPen(QColor(CHART_TRUE_VESSEL).lighter(120), 1.5, Qt.PenStyle.DotLine))
            path = QPainterPath()
            pt0 = self._world_to_screen(self.trail[0][0], self.trail[0][1])
            path.moveTo(pt0)
            for e, n in self.trail[1:]:
                path.lineTo(self._world_to_screen(e, n))
            painter.drawPath(path)

        # 5. Destination Waypoint Marker & Planned Corridor
        if self.waypoint:
            wpt_pt = self._world_to_screen(self.waypoint[0], self.waypoint[1])
            v_pt = self._world_to_screen(self.true_pos[0], self.true_pos[1])

            # Planned track line
            painter.setPen(QPen(QColor(CHART_WAYPOINT), 1.5, Qt.PenStyle.DashLine))
            painter.drawLine(v_pt, wpt_pt)

            # Waypoint beacon marker
            painter.setPen(QPen(QColor(CHART_WAYPOINT), 2))
            painter.setBrush(QBrush(QColor(52, 211, 153, 60)))
            painter.drawEllipse(wpt_pt, 12, 12)
            painter.drawEllipse(wpt_pt, 4, 4)
            painter.setFont(QFont("JetBrains Mono", 9, QFont.Weight.Bold))
            dist_m = math.hypot(self.waypoint[0] - self.true_pos[0], self.waypoint[1] - self.true_pos[1])
            painter.drawText(int(wpt_pt.x() + 14), int(wpt_pt.y() + 4), f"WAYPOINT ({dist_m:.1f}m)")

        # 6. Own-Ship True Ground Truth Vessel (Solid Cyan)
        v_sc = self._world_to_screen(self.true_pos[0], self.true_pos[1])
        painter.save()
        painter.translate(v_sc)
        painter.rotate(self.true_hdg)

        # Scaled vessel hull silhouette (30m length representation)
        L = 30.0 * self.scale_px_per_m
        B = 9.0 * self.scale_px_per_m
        hull = QPolygonF([
            QPointF(0, -L * 0.5),           # Bow tip
            QPointF(B * 0.5, -L * 0.25),    # Stbd shoulder
            QPointF(B * 0.5, L * 0.5),      # Stbd quarter
            QPointF(-B * 0.5, L * 0.5),     # Port quarter
            QPointF(-B * 0.5, -L * 0.25)    # Port shoulder
        ])
        painter.setBrush(QBrush(QColor(CHART_TRUE_VESSEL)))
        painter.setPen(QPen(QColor("#FFFFFF"), 1.5))
        painter.drawPolygon(hull)

        # Velocity Lead-line (Heading + speed vector)
        speed_len = max(15.0, self.speed * 8.0 * self.scale_px_per_m)
        painter.setPen(QPen(QColor(CHART_TRUE_VESSEL), 2))
        painter.drawLine(0, int(-L * 0.5), 0, int(-L * 0.5 - speed_len))
        painter.restore()

        # 7. Autopilot Spoofed Ghost Vessel (Divergence during attack)
        if self.spoofed_pos:
            g_sc = self._world_to_screen(self.spoofed_pos[0], self.spoofed_pos[1])

            # Divergence Vector Line connecting True to Ghost
            painter.setPen(QPen(QColor(COLOR_ALARM), 2, Qt.PenStyle.DashLine))
            painter.drawLine(v_sc, g_sc)

            divergence_m = math.hypot(self.spoofed_pos[0] - self.true_pos[0], self.spoofed_pos[1] - self.true_pos[1])
            painter.setFont(QFont("JetBrains Mono", 9, QFont.Weight.Bold))
            painter.setPen(QColor(COLOR_ALARM))
            mid_pt = QPointF((v_sc.x() + g_sc.x()) / 2.0, (v_sc.y() + g_sc.y()) / 2.0)
            painter.drawText(int(mid_pt.x() + 8), int(mid_pt.y()), f"ΔPOS: {divergence_m:.1f}m (SPOOFED)")

            # Ghost vessel contour
            painter.save()
            painter.translate(g_sc)
            painter.rotate(self.true_hdg + 8.0)
            painter.setBrush(QBrush(QColor(239, 68, 68, 80)))
            painter.setPen(QPen(QColor(COLOR_ALARM), 1.5, Qt.PenStyle.DashLine))
            painter.drawPolygon(hull)
            painter.restore()

        # 8. Chart HUD Overlays (Scale, Mode, Click instructions)
        painter.setPen(QPen(QColor(PANEL_BORDER), 1))
        painter.setBrush(QBrush(QColor(15, 20, 29, 210)))
        painter.drawRect(12, 12, 230, 48)

        painter.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        painter.setPen(QColor(TEXT_MUTED))
        painter.drawText(20, 28, "TACTICAL 2D ECDIS (S-57)")
        painter.setPen(QColor(CHART_WAYPOINT))
        painter.drawText(20, 46, "LEFT-CLICK: SET GUIDED WAYPOINT")

    # Mouse navigation & interaction
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            # Set Waypoint
            east, north = self._screen_to_world(ev.position().x(), ev.position().y())
            self.waypoint = (east, north)
            dlat = north / DEG_TO_M
            dlon = east / (DEG_TO_M * math.cos(math.radians(self.center_lat)))
            tgt_lat = self.center_lat + dlat
            tgt_lon = self.center_lon + dlon
            self.waypoint_latlon = (tgt_lat, tgt_lon)
            self.waypoint_selected.emit(tgt_lat, tgt_lon)
            self.update()
        elif ev.button() == Qt.MouseButton.RightButton:
            self.dragging = True
            self.drag_start = ev.position()

    def mouseMoveEvent(self, ev):
        if self.dragging:
            delta = ev.position() - self.drag_start
            self.pan_offset += delta
            self.drag_start = ev.position()
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.RightButton:
            self.dragging = False

    def wheelEvent(self, ev):
        factor = 1.15 if ev.angleDelta().y() > 0 else 0.85
        self.scale_px_per_m = max(0.2, min(5.0, self.scale_px_per_m * factor))
        self.update()


class ECDISPanel(QWidget):
    """Container wrapping the ECDIS canvas with tactical zoom & center tools."""
    waypoint_commanded = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Canvas
        self.canvas = TacticalECDISWidget(self)
        self.canvas.waypoint_selected.connect(self.waypoint_commanded.emit)
        layout.addWidget(self.canvas)

        # Bottom Quick Controls Bar
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setContentsMargins(6, 0, 6, 4)

        btn_recenter = QPushButton("CENTER VESSEL")
        btn_recenter.setFixedHeight(24)
        btn_recenter.clicked.connect(self._recenter_vessel)
        ctrl_bar.addWidget(btn_recenter)

        btn_clear_wpt = QPushButton("CLEAR WAYPOINT")
        btn_clear_wpt.setFixedHeight(24)
        btn_clear_wpt.clicked.connect(self._clear_waypoint)
        ctrl_bar.addWidget(btn_clear_wpt)

        ctrl_bar.addStretch()

        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedSize(24, 24)
        btn_zoom_in.clicked.connect(lambda: self._zoom(1.2))
        ctrl_bar.addWidget(btn_zoom_in)

        btn_zoom_out = QPushButton("-")
        btn_zoom_out.setFixedSize(24, 24)
        btn_zoom_out.clicked.connect(lambda: self._zoom(0.8))
        ctrl_bar.addWidget(btn_zoom_out)

        layout.addLayout(ctrl_bar)

    def _recenter_vessel(self):
        self.canvas.pan_offset = QPointF(
            -self.canvas.true_pos[0] * self.canvas.scale_px_per_m,
            self.canvas.true_pos[1] * self.canvas.scale_px_per_m
        )
        self.canvas.update()

    def _clear_waypoint(self):
        self.canvas.waypoint = None
        self.canvas.waypoint_latlon = None
        self.canvas.update()

    def _zoom(self, factor):
        self.canvas.scale_px_per_m = max(0.2, min(5.0, self.canvas.scale_px_per_m * factor))
        self.canvas.update()

    def update_telemetry(self, state: dict):
        self.canvas.update_telemetry(state)

    def set_origin(self, lat: float, lon: float):
        self.canvas.set_origin(lat, lon)
