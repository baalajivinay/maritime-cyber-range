"""
Testbed Map & Navigation Display.
Clean 2D interactive nautical chart showing true position, navigation track,
GPS spoofing divergence, and AIS ghost vessels.
"""
import math
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QFont, QPainterPath
from PyQt6.QtCore import Qt, QPointF, QRectF

from application.console.theme import (
    MAP_WATER, MAP_FAIRWAY, MAP_LAND, MAP_GRID,
    MAP_OWN_SHIP, MAP_GHOST_SHIP, MAP_PATH, MAP_SPOOF_LINE,
    MAP_WAYPOINT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    COLOR_RED, COLOR_GREEN, BG_PANEL, BORDER_COLOR
)

DEG_TO_M = 111320.0


class ChartCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 420)
        self.setMouseTracking(True)

        # Coordinate Frame (Meters relative to site origin)
        self.center_lat = 9.9000
        self.center_lon = 76.2000
        self.scale_m_to_px = 0.85  # Pixels per meter
        self.pan_x = 0.0
        self.pan_y = 0.0

        # Vessel State
        self.true_pos = (0.0, 0.0)      # (East m, North m)
        self.true_hdg = 45.0            # Degrees
        self.speed_mps = 0.0
        self.trail = []

        # Target Waypoint
        self.target_wp = None           # (East m, North m)

        # Attack Overlays
        self.spoofed_pos = None         # (East m, North m)
        self.ghost_vessel = None        # dict(pos=(e, n), hdg=deg, name=str)
        self.active_attack = None

        # Dragging / Panning State
        self._dragging = False
        self._drag_start = QPointF()

    def set_site(self, lat: float, lon: float):
        self.center_lat = lat
        self.center_lon = lon
        self.true_pos = (0.0, 0.0)
        self.trail.clear()
        self.target_wp = None
        self.spoofed_pos = None
        self.ghost_vessel = None
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

    def update_telemetry(self, state: dict):
        lat = state.get("lat")
        lon = state.get("lon")
        self.true_hdg = float(state.get("hdg") or 0.0)
        self.speed_mps = float(state.get("speed") or 0.0)
        self.active_attack = state.get("active_attack")

        if lat is not None and lon is not None:
            dn = (float(lat) - self.center_lat) * DEG_TO_M
            de = (float(lon) - self.center_lon) * DEG_TO_M * math.cos(math.radians(self.center_lat))
            self.true_pos = (de, dn)

            # Record navigation trail
            if not self.trail or math.hypot(de - self.trail[-1][0], dn - self.trail[-1][1]) > 2.0:
                self.trail.append((de, dn))
                if len(self.trail) > 200:
                    self.trail.pop(0)

        # GPS Spoofing Offset
        spoof_offset = state.get("spoof_offset_m")
        if spoof_offset and self.active_attack == "gps_spoof":
            self.spoofed_pos = (self.true_pos[0] + spoof_offset[0], self.true_pos[1] + spoof_offset[1])
        else:
            self.spoofed_pos = None

        # AIS Ghost Target
        if self.active_attack == "ais_spoof":
            ghost_info = state.get("ghost_vessel")
            if ghost_info:
                g_lat = ghost_info.get("lat", self.center_lat + 0.0015)
                g_lon = ghost_info.get("lon", self.center_lon + 0.001)
                g_dn = (g_lat - self.center_lat) * DEG_TO_M
                g_de = (g_lon - self.center_lon) * DEG_TO_M * math.cos(math.radians(self.center_lat))
                self.ghost_vessel = {
                    "pos": (g_de, g_dn),
                    "hdg": ghost_info.get("hdg", 180.0),
                    "mmsi": ghost_info.get("mmsi", "419000123")
                }
        else:
            self.ghost_vessel = None

        self.update()

    def m_to_screen(self, east: float, north: float):
        cx = self.width() / 2.0 + self.pan_x
        cy = self.height() / 2.0 + self.pan_y
        sx = cx + east * self.scale_m_to_px
        sy = cy - north * self.scale_m_to_px
        return sx, sy

    def screen_to_m(self, sx: float, sy: float):
        cx = self.width() / 2.0 + self.pan_x
        cy = self.height() / 2.0 + self.pan_y
        east = (sx - cx) / self.scale_m_to_px
        north = -(sy - cy) / self.scale_m_to_px
        return east, north

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Sea Water Background
        p.fillRect(self.rect(), QColor(MAP_WATER))

        # 2. Channel / Fairway
        self._draw_fairway(p)

        # 3. Coordinate Grid
        self._draw_grid(p)

        # 4. Navigation Trail
        self._draw_trail(p)

        # 5. Commanded Waypoint & Target Path
        if self.target_wp:
            self._draw_waypoint(p)

        # 6. AIS Ghost Vessel (if spoof active)
        if self.ghost_vessel:
            self._draw_ghost(p)

        # 7. GPS Spoofed Position & Divergence Line
        if self.spoofed_pos:
            self._draw_spoofed_ghost(p)

        # 8. True Own-Ship Vessel
        self._draw_own_ship(p)

        # 9. Top-Left HUD Card (Scale & Quick Info)
        self._draw_hud(p)

    def _draw_fairway(self, p: QPainter):
        # Draw a curved navigable fairway channel
        path = QPainterPath()
        p1 = self.m_to_screen(-300, -350)
        p2 = self.m_to_screen(-100, -100)
        p3 = self.m_to_screen(150, 150)
        p4 = self.m_to_screen(350, 400)

        path.moveTo(p1[0], p1[1])
        path.cubicTo(p2[0], p2[1], p3[0], p3[1], p4[0], p4[1])

        fairway_pen = QPen(QColor(MAP_FAIRWAY), 120 * self.scale_m_to_px, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(fairway_pen)
        p.drawPath(path)

        # Fairway edge lines
        edge_pen = QPen(QColor("#2d4157"), 1, Qt.PenStyle.DashLine)
        p.setPen(edge_pen)
        p.drawPath(path)

    def _draw_grid(self, p: QPainter):
        pen = QPen(QColor(MAP_GRID), 1, Qt.PenStyle.DotLine)
        p.setPen(pen)

        step_m = 100.0  # 100 meter grid intervals
        step_px = step_m * self.scale_m_to_px

        cx = self.width() / 2.0 + self.pan_x
        cy = self.height() / 2.0 + self.pan_y

        start_x = int(cx % step_px)
        while start_x < self.width():
            p.drawLine(start_x, 0, start_x, self.height())
            start_x += int(step_px)

        start_y = int(cy % step_px)
        while start_y < self.height():
            p.drawLine(0, start_y, self.width(), start_y)
            start_y += int(step_px)

    def _draw_trail(self, p: QPainter):
        if len(self.trail) < 2:
            return
        pen = QPen(QColor(MAP_PATH), 2, Qt.PenStyle.SolidLine)
        p.setPen(pen)
        for i in range(len(self.trail) - 1):
            sx1, sy1 = self.m_to_screen(*self.trail[i])
            sx2, sy2 = self.m_to_screen(*self.trail[i + 1])
            p.drawLine(int(sx1), int(sy1), int(sx2), int(sy2))

    def _draw_waypoint(self, p: QPainter):
        wx, wy = self.m_to_screen(*self.target_wp)
        vx, vy = self.m_to_screen(*self.true_pos)

        # Line from vessel to waypoint
        pen_line = QPen(QColor(MAP_WAYPOINT), 1, Qt.PenStyle.DashLine)
        p.setPen(pen_line)
        p.drawLine(int(vx), int(vy), int(wx), int(wy))

        # Waypoint marker (Bullseye)
        p.setPen(QPen(QColor(MAP_WAYPOINT), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(wx, wy), 9, 9)
        p.setBrush(QBrush(QColor(MAP_WAYPOINT)))
        p.drawEllipse(QPointF(wx, wy), 3, 3)

        # Label
        p.setFont(QFont("-apple-system, sans-serif", 9))
        p.setPen(QColor(MAP_WAYPOINT))
        p.drawText(int(wx + 12), int(wy + 4), "Target Waypoint")

    def _draw_ghost(self, p: QPainter):
        ge, gn = self.ghost_vessel["pos"]
        gx, gy = self.m_to_screen(ge, gn)
        ghdg = self.ghost_vessel["hdg"]

        p.save()
        p.translate(gx, gy)
        p.rotate(ghdg)

        # Safety perimeter circle
        p.setPen(QPen(QColor(COLOR_RED), 1, Qt.PenStyle.DashLine))
        p.setBrush(QBrush(QColor(235, 87, 87, 25)))
        r = 60 * self.scale_m_to_px
        p.drawEllipse(QPointF(0, 0), r, r)

        # Vessel Hull Shape
        hull = QPolygonF([
            QPointF(0, -18),
            QPointF(8, 6),
            QPointF(6, 16),
            QPointF(-6, 16),
            QPointF(-8, 6),
        ])
        p.setPen(QPen(QColor(COLOR_RED), 2))
        p.setBrush(QBrush(QColor(COLOR_RED)))
        p.drawPolygon(hull)
        p.restore()

        # Ghost Ship Label
        p.setFont(QFont("-apple-system, sans-serif", 9, QFont.Weight.Bold))
        p.setPen(QColor(COLOR_RED))
        mmsi = self.ghost_vessel.get("mmsi", "AIS-GHOST")
        p.drawText(int(gx + 15), int(gy - 5), f"AIS Ghost ({mmsi})")

    def _draw_spoofed_ghost(self, p: QPainter):
        tx, ty = self.m_to_screen(*self.true_pos)
        sx, sy = self.m_to_screen(*self.spoofed_pos)

        # Red Divergence Vector Line
        pen_div = QPen(QColor(MAP_SPOOF_LINE), 2, Qt.PenStyle.DashLine)
        p.setPen(pen_div)
        p.drawLine(int(tx), int(ty), int(sx), int(sy))

        # Divergence distance calculation
        dx_m = self.spoofed_pos[0] - self.true_pos[0]
        dy_m = self.spoofed_pos[1] - self.true_pos[1]
        dist_m = math.hypot(dx_m, dy_m)

        # Midpoint label for distance
        mx = (tx + sx) / 2.0
        my = (ty + sy) / 2.0
        p.setFont(QFont("-apple-system, sans-serif", 9, QFont.Weight.Bold))
        p.setPen(QColor(MAP_SPOOF_LINE))
        p.drawText(int(mx + 8), int(my - 5), f"Drift: {dist_m:.1f} m")

        # Believed (Spoofed) Position Marker
        p.save()
        p.translate(sx, sy)
        p.rotate(self.true_hdg)

        p.setPen(QPen(QColor(MAP_SPOOF_LINE), 2))
        p.setBrush(QBrush(QColor(235, 87, 87, 80)))
        hull = QPolygonF([
            QPointF(0, -14),
            QPointF(6, 4),
            QPointF(4, 12),
            QPointF(-4, 12),
            QPointF(-6, 4),
        ])
        p.drawPolygon(hull)
        p.restore()

        p.drawText(int(sx + 14), int(sy + 4), "Believed GPS Fix")

    def _draw_own_ship(self, p: QPainter):
        vx, vy = self.m_to_screen(*self.true_pos)

        p.save()
        p.translate(vx, vy)
        p.rotate(self.true_hdg)

        # Heading velocity vector line
        vec_len = max(25.0, self.speed_mps * 8.0 * self.scale_m_to_px)
        p.setPen(QPen(QColor(MAP_OWN_SHIP), 2))
        p.drawLine(0, 0, 0, int(-vec_len))

        # Modern Crisp Vessel Hull
        hull = QPolygonF([
            QPointF(0, -16),
            QPointF(7, 5),
            QPointF(5, 14),
            QPointF(-5, 14),
            QPointF(-7, 5),
        ])

        p.setPen(QPen(QColor("#0284c7"), 1.5))
        p.setBrush(QBrush(QColor(MAP_OWN_SHIP)))
        p.drawPolygon(hull)
        p.restore()

        # Own-ship Label
        p.setFont(QFont("-apple-system, sans-serif", 9, QFont.Weight.Bold))
        p.setPen(QColor(TEXT_PRIMARY))
        p.drawText(int(vx + 14), int(vy - 6), "Own-Ship (True Position)")

    def _draw_hud(self, p: QPainter):
        # Scale indicator card in bottom-left
        hud_w, hud_h = 130, 44
        margin = 12
        rx = margin
        ry = self.height() - hud_h - margin

        p.setPen(QPen(QColor(BORDER_COLOR), 1))
        p.setBrush(QBrush(QColor(30, 30, 38, 220)))
        p.drawRoundedRect(QRectF(rx, ry, hud_w, hud_h), 5, 5)

        # Scale bar (50 meters)
        scale_50m_px = 50.0 * self.scale_m_to_px
        p.setPen(QPen(QColor(TEXT_PRIMARY), 2))
        p.drawLine(int(rx + 12), int(ry + 28), int(rx + 12 + scale_50m_px), int(ry + 28))
        p.drawLine(int(rx + 12), int(ry + 24), int(rx + 12), int(ry + 32))
        p.drawLine(int(rx + 12 + scale_50m_px), int(ry + 24), int(rx + 12 + scale_50m_px), int(ry + 32))

        p.setFont(QFont("-apple-system, sans-serif", 8))
        p.setPen(QColor(TEXT_SECONDARY))
        p.drawText(int(rx + 12), int(ry + 18), "50 meters")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Set target navigation waypoint
            east, north = self.screen_to_m(event.position().x(), event.position().y())
            self.target_wp = (east, north)
            self.update()
        elif event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._dragging = True
            self._drag_start = event.position()

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.position() - self._drag_start
            self._drag_start = event.position()
            self.pan_x += delta.x()
            self.pan_y += delta.y()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._dragging = False

    def wheelEvent(self, event):
        angle = event.angleDelta().y()
        factor = 1.15 if angle > 0 else 0.87
        self.scale_m_to_px = max(0.2, min(5.0, self.scale_m_to_px * factor))
        self.update()


class ECDISPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header bar above chart
        header = QHBoxLayout()
        header.setContentsMargins(8, 4, 8, 0)

        lbl = QLabel("Navigation Map")
        lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY};")
        header.addWidget(lbl)

        hint = QLabel("Left-click to steer waypoint  •  Scroll to zoom  •  Right-drag to pan")
        hint.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        header.addWidget(hint)

        header.addStretch()

        btn_recenter = QPushButton("Recenter")
        btn_recenter.setFixedHeight(26)
        btn_recenter.clicked.connect(self._recenter)
        header.addWidget(btn_recenter)

        layout.addLayout(header)

        # Chart Canvas
        self.canvas = ChartCanvas(self)
        layout.addWidget(self.canvas, 1)

    def _recenter(self):
        self.canvas.pan_x = 0.0
        self.canvas.pan_y = 0.0
        self.canvas.scale_m_to_px = 0.85
        self.canvas.update()

    def set_site(self, lat: float, lon: float):
        self.canvas.set_site(lat, lon)

    def update_telemetry(self, state: dict):
        self.canvas.update_telemetry(state)
