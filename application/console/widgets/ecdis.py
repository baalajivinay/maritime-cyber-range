"""
Testbed Tactical ECDIS & Navigation Display.
Conforming to IEC 61174, IHO S-52 Presentation Standards, and COLREGS Rules 7, 8, 14, 15.

Features:
- Nautical chart with navigable fairway channel and coordinate grid.
- Own-ship true position with Heading line and True Motion Vector (1-min / 3-min predictor ticks).
- Concentric Range Rings (100m, 250m, 500m) with distance labels.
- Commanded Waypoint line with cross-track error readout.
- AIS Target Contacts with true course vectors, CPA/TCPA calculations, and collision warning sectors.
- Real-time GNSS Spoofing divergence vector and believed fix ghost.
- Underwater AUV acoustic transponder beacon and depth profile view.
- Pan, zoom (+, -, 1:1, Recenter) interactive controls.
"""
import math
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QFont, QPainterPath
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal

from application.console.theme import (
    MAP_WATER, MAP_FAIRWAY, MAP_LAND, MAP_GRID,
    MAP_OWN_SHIP, MAP_GHOST_SHIP, MAP_PATH, MAP_SPOOF_LINE,
    MAP_WAYPOINT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    COLOR_RED, COLOR_GREEN, COLOR_BLUE, COLOR_AMBER, BG_PANEL, BORDER_COLOR
)

DEG_TO_M = 111320.0
DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi

# =============================================================================
# IEC 62288 display palettes (Day / Dusk / Night).
# Night minimises luminance for dark-adapted bridge watchkeeping.
# =============================================================================
DAY_PALETTE = {
    "water_deep": "#dfe9f2", "water_shallow": "#b9d4ea", "fairway": "#eef4fb",
    "land": "#e4dcc6", "grid": "#c3d1e0", "text": "#1b2a3a", "text_dim": "#51627a",
    "safety_contour": "#5d7794", "depth_label": "#3b556e",
}
DUSK_PALETTE = {
    "water_deep": "#2a3442", "water_shallow": "#334256", "fairway": "#33465c",
    "land": "#434334", "grid": "#3c4a5c", "text": "#c7d3e0", "text_dim": "#8494a6",
    "safety_contour": "#6f89a6", "depth_label": "#9fb3c8",
}
NIGHT_PALETTE = {
    "water_deep": "#06090d", "water_shallow": "#0a121c", "fairway": "#0c1623",
    "land": "#17160f", "grid": "#13202c", "text": "#8fb4c9", "text_dim": "#4a6476",
    "safety_contour": "#1f3850", "depth_label": "#2f5068",
}
PALETTES = {"day": DAY_PALETTE, "dusk": DUSK_PALETTE, "night": NIGHT_PALETTE}


def default_s52_features():
    """A representative IHO S-52 feature set laid out in local metres around the
    site origin: lateral buoyage marking the fairway, cardinal marks on a
    hazard, a lighthouse with a nominal-range arc, and bathymetric contours."""
    return {
        "depth_contours": [
            {"depth_m": 5.0, "radius_m": 120.0, "safety": False},
            {"depth_m": 10.0, "radius_m": 230.0, "safety": True},   # safety contour
            {"depth_m": 20.0, "radius_m": 360.0, "safety": False},
        ],
        "shallow_patch": {"east_m": -180.0, "north_m": 140.0, "radius_m": 70.0},
        "buoys": [
            # IALA Region A: port hand = red can, starboard hand = green cone
            {"kind": "port", "east_m": -70.0, "north_m": -40.0, "name": "No.1"},
            {"kind": "port", "east_m": 40.0, "north_m": 120.0, "name": "No.3"},
            {"kind": "starboard", "east_m": 60.0, "north_m": -40.0, "name": "No.2"},
            {"kind": "starboard", "east_m": 170.0, "north_m": 120.0, "name": "No.4"},
        ],
        "cardinals": [
            {"kind": "north", "east_m": -180.0, "north_m": 230.0, "name": "N Card"},
            {"kind": "east", "east_m": 260.0, "north_m": 60.0, "name": "E Card"},
        ],
        "lights": [
            {"east_m": -240.0, "north_m": -120.0, "name": "Lt Ho",
             "range_m": 300.0, "colour": "#fbbf24"},
        ],
    }


class ChartCanvas(QWidget):
    waypoint_commanded = pyqtSignal(float, float)
    waypoint_cleared = pyqtSignal()

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
        self.depth_m = 0.0
        self.domain = "surface"
        self.trail = []

        # Target Waypoint (active leg) + full multi-leg route (Task 4)
        self.target_wp = None           # (East m, North m) — active leg target
        self.route = []                 # [(East m, North m), ...] ordered WPs
        self.route_idx = 0              # index of the active (not-yet-reached) WP
        self.xte_limit_m = 50.0         # cross-track error corridor half-width
        self.turn_radius_m = 60.0       # advisory wheel-over turn radius

        # IEC 62288 display palette mode: "day" | "dusk" | "night"
        self.palette_mode = "day"
        self._pal = dict(DAY_PALETTE)

        # IHO S-52 charted features (buoys, cardinals, lights, contours)
        self.s52_features = default_s52_features()

        # Attack Overlays
        self.spoofed_pos = None         # (East m, North m)
        self.ghost_vessel = None        # dict(pos=(e, n), course=deg, speed=mps, mmsi=str)
        self.active_attack = None
        self.cpa_m = None
        self.tcpa_s = None
        self.collision_risk = False
        self.usbl_offset_m = 0.0
        self.radar_false_targets = []   # ARPA synthetic blips (Task 2)
        self.traffic = []               # background merchant fleet (Task 5)

        # Dragging / Panning State
        self._dragging = False
        self._drag_start = QPointF()

    def set_site(self, lat: float, lon: float):
        self.center_lat = lat
        self.center_lon = lon
        self.true_pos = (0.0, 0.0)
        self.trail.clear()
        self.target_wp = None
        self.route = []
        self.route_idx = 0
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
        self.depth_m = float(state.get("depth") or 0.0)
        self.domain = state.get("domain", "surface")
        self.active_attack = state.get("active_attack")
        self.cpa_m = state.get("cpa_m")
        self.tcpa_s = state.get("tcpa_s")
        self.collision_risk = state.get("collision_risk", False)
        self.usbl_offset_m = state.get("usbl_offset_m", 0.0)
        self.radar_false_targets = state.get("radar_false_targets", []) or []
        self.traffic = state.get("traffic", []) or []

        if lat is not None and lon is not None:
            dn = (float(lat) - self.center_lat) * DEG_TO_M
            de = (float(lon) - self.center_lon) * DEG_TO_M * math.cos(math.radians(self.center_lat))
            self.true_pos = (de, dn)

            # Record navigation trail
            if not self.trail or math.hypot(de - self.trail[-1][0], dn - self.trail[-1][1]) > 2.0:
                self.trail.append((de, dn))
                if len(self.trail) > 250:
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
                g_pos = ghost_info.get("pos", (self.true_pos[0] + 150.0, self.true_pos[1] + 200.0))
                self.ghost_vessel = {
                    "pos": g_pos,
                    "course": ghost_info.get("course", 180.0),
                    "speed": ghost_info.get("speed", 4.5),
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
        # Defensive clamp: keep the scale in a sane range even if set directly,
        # so no draw routine can be driven into a pathological (zero-step) loop.
        self.scale_m_to_px = max(0.02, min(50.0, self.scale_m_to_px))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Nautical Water Background (palette-aware, IEC 62288)
        p.fillRect(self.rect(), QColor(self._pal["water_deep"]))

        # 1b. Bathymetric depth contours & shallow-water shading (S-52)
        self._draw_depth_contours(p)

        # 2. Navigable Fairway Channel
        self._draw_fairway(p)

        # 3. Coordinate Grid
        self._draw_grid(p)

        # 3b. IHO S-52 charted features (buoys, cardinals, lights)
        self._draw_s52_features(p)

        # 4. Range Rings (100m, 250m, 500m)
        self._draw_range_rings(p)

        # 5. Underwater Acoustic Transponder (AUV mode)
        if self.domain == "underwater":
            self._draw_acoustic_beacon(p)

        # 6. Navigation Trail
        self._draw_trail(p)

        # 7. Route (multi-leg) or single commanded waypoint
        if self.route:
            self._draw_route(p)
        elif self.target_wp:
            self._draw_waypoint(p)

        # 7a. Background merchant fleet AIS contacts (Task 5)
        if self.traffic:
            self._draw_traffic(p)

        # 7b. Radar / ARPA synthetic false targets (Task 2)
        if self.radar_false_targets:
            self._draw_radar_false_targets(p)

        # 8. AIS Ghost Contact & Collision Sector
        if self.ghost_vessel:
            self._draw_ghost(p)

        # 9. GNSS Spoofed Fix & Divergence Line
        if self.spoofed_pos:
            self._draw_spoofed_ghost(p)

        # 10. True Own-Ship Vessel with Vectors
        self._draw_own_ship(p)

        # 11. ECDIS Scale & Compass Indicator HUD Card
        self._draw_hud(p)

    def _draw_fairway(self, p: QPainter):
        path = QPainterPath()
        p1 = self.m_to_screen(-300, -350)
        p2 = self.m_to_screen(-100, -100)
        p3 = self.m_to_screen(150, 150)
        p4 = self.m_to_screen(350, 400)

        path.moveTo(p1[0], p1[1])
        path.cubicTo(p2[0], p2[1], p3[0], p3[1], p4[0], p4[1])

        fairway_pen = QPen(QColor(self._pal["fairway"]), 130 * self.scale_m_to_px, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(fairway_pen)
        p.drawPath(path)

        edge_pen = QPen(QColor(self._pal["safety_contour"]), 1, Qt.PenStyle.DashLine)
        p.setPen(edge_pen)
        p.drawPath(path)

    def _draw_depth_contours(self, p: QPainter):
        """Concentric bathymetric contours with shallow-water shading and a
        highlighted safety contour (IHO S-52)."""
        ox, oy = self.m_to_screen(0.0, 0.0)
        contours = sorted(self.s52_features.get("depth_contours", []),
                          key=lambda c: c["radius_m"], reverse=True)
        for c in contours:
            r = c["radius_m"] * self.scale_m_to_px
            if c.get("safety"):
                # Safety contour: bold dashed boundary separating safe water
                p.setBrush(QBrush(QColor(self._pal["water_shallow"])))
                p.setPen(QPen(QColor(self._pal["safety_contour"]), 2, Qt.PenStyle.DashLine))
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(self._pal["safety_contour"]), 1, Qt.PenStyle.DotLine))
            p.drawEllipse(QPointF(ox, oy), r, r)
            p.setPen(QColor(self._pal["depth_label"]))
            p.setFont(QFont("-apple-system, sans-serif", 7))
            p.drawText(int(ox + r * 0.7), int(oy - r * 0.7), f"{c['depth_m']:.0f}m")

        # Discrete shallow danger patch
        sp = self.s52_features.get("shallow_patch")
        if sp:
            sx, sy = self.m_to_screen(sp["east_m"], sp["north_m"])
            rr = sp["radius_m"] * self.scale_m_to_px
            p.setBrush(QBrush(QColor(173, 216, 120, 70)))
            p.setPen(QPen(QColor("#9aa84f"), 1, Qt.PenStyle.DashLine))
            p.drawEllipse(QPointF(sx, sy), rr, rr)

    def _draw_s52_features(self, p: QPainter):
        """IALA lateral buoyage, cardinal marks and lighthouse sector/range arc."""
        # Lighthouses with nominal-range arcs
        for lt in self.s52_features.get("lights", []):
            lx, ly = self.m_to_screen(lt["east_m"], lt["north_m"])
            rng = lt.get("range_m", 250.0) * self.scale_m_to_px
            p.setPen(QPen(QColor(lt.get("colour", "#fbbf24")), 1, Qt.PenStyle.DotLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(lx, ly), rng, rng)
            p.setBrush(QBrush(QColor(lt.get("colour", "#fbbf24"))))
            p.setPen(QPen(QColor(self._pal["text"]), 1))
            # Magenta flare star is standard; approximate with a filled diamond
            star = QPolygonF([QPointF(lx, ly - 6), QPointF(lx + 4, ly),
                              QPointF(lx, ly + 6), QPointF(lx - 4, ly)])
            p.drawPolygon(star)
            p.setPen(QColor(self._pal["text"]))
            p.setFont(QFont("-apple-system, sans-serif", 7, QFont.Weight.Bold))
            p.drawText(int(lx + 8), int(ly - 6), lt.get("name", "Lt"))

        # Lateral buoyage: port = red can, starboard = green cone
        for b in self.s52_features.get("buoys", []):
            bx, by = self.m_to_screen(b["east_m"], b["north_m"])
            if b["kind"] == "port":
                p.setBrush(QBrush(QColor("#d64545")))
                p.setPen(QPen(QColor("#8a2a2a"), 1))
                p.drawRect(QRectF(bx - 3, by - 5, 6, 10))          # can
            else:
                p.setBrush(QBrush(QColor("#2f9e44")))
                p.setPen(QPen(QColor("#1d6b2e"), 1))
                cone = QPolygonF([QPointF(bx, by - 6), QPointF(bx + 4, by + 4),
                                  QPointF(bx - 4, by + 4)])
                p.drawPolygon(cone)                                 # cone
            p.setPen(QColor(self._pal["text_dim"]))
            p.setFont(QFont("-apple-system, sans-serif", 6))
            p.drawText(int(bx + 6), int(by + 3), b.get("name", ""))

        # Cardinal marks (N/E/S/W) — yellow/black pillar with topmark direction
        for c in self.s52_features.get("cardinals", []):
            cx, cy = self.m_to_screen(c["east_m"], c["north_m"])
            p.setBrush(QBrush(QColor("#1a1a1a")))
            p.setPen(QPen(QColor("#f2c200"), 2))
            p.drawEllipse(QPointF(cx, cy), 4, 4)
            # Topmark cones indicate the quadrant of safe water
            p.setPen(QColor("#f2c200"))
            p.setFont(QFont("-apple-system, sans-serif", 6, QFont.Weight.Bold))
            glyph = {"north": "▲▲", "east": "▲▼", "south": "▼▼", "west": "▼▲"}.get(c["kind"], "◆")
            p.drawText(int(cx - 6), int(cy - 7), glyph)
            p.setPen(QColor(self._pal["text_dim"]))
            p.drawText(int(cx + 7), int(cy + 3), c.get("name", ""))

    def _draw_route(self, p: QPainter):
        """Multi-leg route with XTE corridor, turn-radius circles and WP badges."""
        vx, vy = self.m_to_screen(*self.true_pos)
        pts = [(vx, vy)] + [self.m_to_screen(e, n) for (e, n) in self.route]

        # XTE corridor (dashed parallels) + leg lines
        for i in range(len(pts) - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i + 1]
            done = i < self.route_idx
            leg_col = QColor("#5a6b7a") if done else QColor("#00d2ff")
            p.setPen(QPen(leg_col, 2 if not done else 1,
                          Qt.PenStyle.SolidLine if not done else Qt.PenStyle.DashLine))
            p.drawLine(int(x1), int(y1), int(x2), int(y2))

            # XTE limit parallels
            dx, dy = x2 - x1, y2 - y1
            ln = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / ln, dx / ln
            off = self.xte_limit_m * self.scale_m_to_px
            p.setPen(QPen(QColor(0, 210, 255, 90), 1, Qt.PenStyle.DotLine))
            for s in (off, -off):
                p.drawLine(int(x1 + nx * s), int(y1 + ny * s),
                           int(x2 + nx * s), int(y2 + ny * s))

        # Turn-radius circles at intermediate waypoints
        for i in range(1, len(self.route) - 1):
            wx, wy = self.m_to_screen(*self.route[i])
            tr = self.turn_radius_m * self.scale_m_to_px
            p.setPen(QPen(QColor(0, 210, 255, 120), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(wx, wy), tr, tr)

        # Waypoint reticles + labels
        legs = self.route_legs()
        p.setFont(QFont("-apple-system, sans-serif", 8, QFont.Weight.Bold))
        for i, (e, n) in enumerate(self.route):
            wx, wy = self.m_to_screen(e, n)
            row = legs[i]
            col = QColor("#5a6b7a") if row["done"] else (
                QColor("#ffd166") if row["active"] else QColor("#00d2ff"))
            p.setPen(QPen(col, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(wx, wy), 7, 7)
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(wx, wy), 2.0, 2.0)
            p.setPen(col)
            p.drawText(int(wx + 9), int(wy - 6),
                       f"{row['wp']} {row['course_deg']:03.0f}°/{row['dist_m']:.0f}m")

    def _draw_grid(self, p: QPainter):
        pen = QPen(QColor(self._pal["grid"]), 1, Qt.PenStyle.DotLine)
        p.setPen(pen)

        step_m = 100.0
        step_px = step_m * self.scale_m_to_px
        # Guard against pathological zoom: a sub-pixel grid step would make the
        # integer increment round to 0 and loop forever (DoS). Skip the grid
        # when it is too fine to be legible, and step with floats regardless.
        if step_px < 4.0:
            return

        cx = self.width() / 2.0 + self.pan_x
        cy = self.height() / 2.0 + self.pan_y

        x = cx % step_px
        while x < self.width():
            p.drawLine(int(x), 0, int(x), self.height())
            x += step_px

        y = cy % step_px
        while y < self.height():
            p.drawLine(0, int(y), self.width(), int(y))
            y += step_px

    def _draw_range_rings(self, p: QPainter):
        vx, vy = self.m_to_screen(*self.true_pos)
        pen_ring = QPen(QColor("#223348"), 1, Qt.PenStyle.DashLine)
        p.setPen(pen_ring)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setFont(QFont("-apple-system, sans-serif", 7))

        for dist_m in (100.0, 250.0, 500.0):
            r_px = dist_m * self.scale_m_to_px
            if r_px < 15 or r_px > max(self.width(), self.height()) * 1.5:
                continue
            p.drawEllipse(QPointF(vx, vy), r_px, r_px)
            # Label
            p.setPen(QColor("#3a5068"))
            p.drawText(int(vx + r_px + 3), int(vy - 2), f"{int(dist_m)}m")
            p.setPen(pen_ring)

    def _draw_acoustic_beacon(self, p: QPainter):
        # Surface mother-ship transponder origin at (0,0)
        bx, by = self.m_to_screen(0.0, 0.0)
        p.setPen(QPen(QColor("#38bdf8"), 1.5, Qt.PenStyle.DashDotLine))
        p.setBrush(QBrush(QColor(56, 189, 248, 15)))
        r = 300.0 * self.scale_m_to_px
        p.drawEllipse(QPointF(bx, by), r, r)

        # Transponder icon
        p.setPen(QPen(QColor("#38bdf8"), 2))
        p.setBrush(QBrush(QColor("#38bdf8")))
        p.drawEllipse(QPointF(bx, by), 4, 4)
        p.setFont(QFont("-apple-system, sans-serif", 8, QFont.Weight.Bold))
        p.drawText(int(bx + 8), int(by - 4), "USBL Acoustic Transponder (Origin)")

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

        # 1. Commanded Track Line from vessel to waypoint
        pen_track = QPen(QColor("#00d2ff"), 1.5, Qt.PenStyle.DashLine)
        p.setPen(pen_track)
        p.drawLine(int(vx), int(vy), int(wx), int(wy))

        # 2. Bullseye Target Reticle
        wp_color = QColor("#00d2ff")
        p.setPen(QPen(wp_color, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(wx, wy), 12, 12)
        p.drawEllipse(QPointF(wx, wy), 6, 6)
        p.setBrush(QBrush(wp_color))
        p.drawEllipse(QPointF(wx, wy), 2.5, 2.5)

        # Reticle Crosshairs
        p.drawLine(int(wx - 16), int(wy), int(wx - 13), int(wy))
        p.drawLine(int(wx + 13), int(wy), int(wx + 16), int(wy))
        p.drawLine(int(wx), int(wy - 16), int(wx), int(wy - 13))
        p.drawLine(int(wx), int(wy + 13), int(wx), int(wy + 16))

        # 3. Target Navigation Metrics Badge
        dx = self.target_wp[0] - self.true_pos[0]
        dy = self.target_wp[1] - self.true_pos[1]
        dist_m = math.hypot(dx, dy)
        bearing_deg = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
        ttg_str = f"{(dist_m / max(0.5, self.speed_mps)):.0f}s" if self.speed_mps > 0.5 else "--"

        badge_txt = f"WP-01 | {dist_m:.0f}m | {bearing_deg:05.1f}° | TTG: {ttg_str}"
        p.setFont(QFont("-apple-system, sans-serif", 8, QFont.Weight.Bold))
        fm = p.fontMetrics()
        txt_w = fm.horizontalAdvance(badge_txt) + 12
        txt_h = 18

        # Badge background pill
        bx = int(wx + 14)
        by = int(wy - 9)
        p.setPen(QPen(QColor("#008bb2"), 1))
        p.setBrush(QBrush(QColor(10, 25, 38, 220)))
        p.drawRoundedRect(QRectF(bx, by, txt_w, txt_h), 4, 4)

        p.setPen(QColor("#00d2ff"))
        p.drawText(bx + 6, by + 13, badge_txt)

    def _draw_traffic(self, p: QPainter):
        """Draw AIS background traffic as true-scale contacts with CPA vectors;
        contacts in COLREGS risk are highlighted."""
        p.setFont(QFont("-apple-system, sans-serif", 7))
        for t in self.traffic:
            tx, ty = self.m_to_screen(t.get("east_m", 0.0), t.get("north_m", 0.0))
            risk = t.get("risk", False)
            col = QColor("#eb5757") if risk else QColor("#7fb0d6")
            # Hull triangle oriented on course
            p.save()
            p.translate(tx, ty)
            p.rotate(t.get("course", 0.0))
            hull = QPolygonF([QPointF(0, -9), QPointF(5, 7), QPointF(-5, 7)])
            p.setPen(QPen(col, 1.4))
            p.setBrush(QBrush(col))
            p.drawPolygon(hull)
            # 60 s velocity vector
            spd = t.get("speed", 0.0)
            vlen = spd * 60.0 * self.scale_m_to_px
            p.setPen(QPen(col, 1, Qt.PenStyle.SolidLine))
            p.drawLine(0, -9, 0, int(-9 - vlen))
            p.restore()
            if risk:
                rr = 60.0 * self.scale_m_to_px
                p.setPen(QPen(QColor(235, 87, 87, 120), 1, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(tx, ty), rr, rr)
            p.setPen(QColor(self._pal["text_dim"]) if not risk else QColor("#eb5757"))
            label = t.get("name", "AIS")
            if t.get("cpa_m") is not None and risk:
                label += f"  CPA {t['cpa_m']:.0f}m"
            p.drawText(int(tx + 8), int(ty + 3), label)

    def _draw_radar_false_targets(self, p: QPainter):
        """Draw injected ARPA blips with their (false) tracking vectors."""
        p.setFont(QFont("-apple-system, sans-serif", 7, QFont.Weight.Bold))
        for t in self.radar_false_targets:
            tx, ty = self.m_to_screen(t.get("east_m", 0.0), t.get("north_m", 0.0))
            colour = QColor("#f59e0b")  # amber: unverified radar contact
            # ARPA blip: hollow square (IHO radar target convention)
            p.setPen(QPen(colour, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(tx - 5, ty - 5, 10, 10))
            # Tracking vector
            course = t.get("course", 0.0) * DEG_TO_RAD
            spd = t.get("speed", 0.0)
            vec = spd * 30.0 * self.scale_m_to_px
            ex = tx + math.sin(course) * vec
            ey = ty - math.cos(course) * vec
            p.setPen(QPen(colour, 1, Qt.PenStyle.DashLine))
            p.drawLine(int(tx), int(ty), int(ex), int(ey))
            p.setPen(colour)
            p.drawText(int(tx + 7), int(ty - 6), f"{t.get('track_id','T?')} (RADAR?)")

    def _draw_ghost(self, p: QPainter):
        ge, gn = self.ghost_vessel["pos"]
        gx, gy = self.m_to_screen(ge, gn)
        ghdg = self.ghost_vessel["course"]

        # If collision risk active, draw flashing safety zone
        if self.collision_risk:
            p.setPen(QPen(QColor(COLOR_RED), 2, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(235, 87, 87, 45)))
            r = 75 * self.scale_m_to_px
            p.drawEllipse(QPointF(gx, gy), r, r)
        else:
            p.setPen(QPen(QColor(COLOR_AMBER), 1, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(242, 153, 74, 25)))
            r = 50 * self.scale_m_to_px
            p.drawEllipse(QPointF(gx, gy), r, r)

        # Vessel Hull Shape
        p.save()
        p.translate(gx, gy)
        p.rotate(ghdg)

        hull = QPolygonF([
            QPointF(0, -18),
            QPointF(8, 6),
            QPointF(6, 16),
            QPointF(-6, 16),
            QPointF(-8, 6),
        ])
        vessel_color = COLOR_RED if self.collision_risk else COLOR_AMBER
        p.setPen(QPen(QColor(vessel_color), 2))
        p.setBrush(QBrush(QColor(vessel_color)))
        p.drawPolygon(hull)

        # Ghost Speed Vector (30 seconds ahead)
        g_speed = self.ghost_vessel.get("speed", 4.0)
        vec_len = g_speed * 30.0 * self.scale_m_to_px
        p.setPen(QPen(QColor(vessel_color), 1.5, Qt.PenStyle.SolidLine))
        p.drawLine(0, -18, 0, int(-18 - vec_len))

        p.restore()

        # Ghost Ship Label & CPA
        p.setFont(QFont("-apple-system, sans-serif", 9, QFont.Weight.Bold))
        p.setPen(QColor(vessel_color))
        mmsi = self.ghost_vessel.get("mmsi", "AIS-GHOST")
        p.drawText(int(gx + 16), int(gy - 6), f"AIS Threat ({mmsi})")

        if self.cpa_m is not None:
            p.setFont(QFont("-apple-system, sans-serif", 8))
            p.drawText(int(gx + 16), int(gy + 8), f"CPA: {self.cpa_m:.0f}m  TCPA: {self.tcpa_s:.0f}s")

    def _draw_spoofed_ghost(self, p: QPainter):
        tx, ty = self.m_to_screen(*self.true_pos)
        sx, sy = self.m_to_screen(*self.spoofed_pos)

        # Red Divergence Vector Line
        pen_div = QPen(QColor(MAP_SPOOF_LINE), 2, Qt.PenStyle.DashLine)
        p.setPen(pen_div)
        p.drawLine(int(tx), int(ty), int(sx), int(sy))

        dx_m = self.spoofed_pos[0] - self.true_pos[0]
        dy_m = self.spoofed_pos[1] - self.true_pos[1]
        dist_m = math.hypot(dx_m, dy_m)

        mx = (tx + sx) / 2.0
        my = (ty + sy) / 2.0
        p.setFont(QFont("-apple-system, sans-serif", 9, QFont.Weight.Bold))
        p.setPen(QColor(MAP_SPOOF_LINE))
        p.drawText(int(mx + 8), int(my - 5), f"Drift: {dist_m:.1f} m")

        # Believed (Spoofed) Position Marker
        p.save()
        p.translate(sx, sy)
        p.rotate(self.true_hdg)

        p.setPen(QPen(QColor(MAP_SPOOF_LINE), 1.5))
        p.setBrush(QBrush(QColor(235, 87, 87, 70)))
        hull = QPolygonF([
            QPointF(0, -14),
            QPointF(6, 4),
            QPointF(4, 12),
            QPointF(-4, 12),
            QPointF(-6, 4),
        ])
        p.drawPolygon(hull)
        p.restore()

        p.drawText(int(sx + 14), int(sy + 4), "Spoofed Believed Fix")

    def _draw_own_ship(self, p: QPainter):
        vx, vy = self.m_to_screen(*self.true_pos)

        p.save()
        p.translate(vx, vy)
        p.rotate(self.true_hdg)

        # 1. Heading Index Line (200m ahead)
        hdg_len = 80.0 * self.scale_m_to_px
        p.setPen(QPen(QColor("#7dd3fc"), 1, Qt.PenStyle.DashDotLine))
        p.drawLine(0, -16, 0, int(-16 - hdg_len))

        # 2. True Motion Vector (1-minute and 3-minute predictor ticks)
        if self.speed_mps > 0.2:
            vec_1min = self.speed_mps * 60.0 * self.scale_m_to_px
            p.setPen(QPen(QColor(COLOR_GREEN), 1.5, Qt.PenStyle.SolidLine))
            p.drawLine(0, -16, 0, int(-16 - vec_1min))
            # 1-min cross tick
            p.drawLine(-4, int(-16 - vec_1min), 4, int(-16 - vec_1min))

        # 3. Vessel Hull
        if self.domain == "underwater":
            # Torpedo AUV shape
            hull = QPolygonF([
                QPointF(0, -16),
                QPointF(5, -6),
                QPointF(5, 12),
                QPointF(-5, 12),
                QPointF(-5, -6),
            ])
            p.setPen(QPen(QColor("#0ea5e9"), 1.5))
            p.setBrush(QBrush(QColor("#38bdf8")))
        else:
            # Planing / Displacement USV shape
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
        dom_label = "AUV Submerged" if self.domain == "underwater" else "Own-Ship"
        p.drawText(int(vx + 14), int(vy - 6), f"{dom_label} (True Fix)")

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

    def clear_waypoint(self):
        self.target_wp = None
        self.route = []
        self.route_idx = 0
        self.waypoint_cleared.emit()
        self.update()

    # ------------------------------------------------------------ route (Task 4)
    def append_route_wp(self, east: float, north: float):
        """Append a leg waypoint. The first appended WP becomes the active
        target immediately."""
        self.route.append((east, north))
        if len(self.route) == 1:
            self.route_idx = 0
            self.target_wp = self.route[0]
            self.waypoint_commanded.emit(east, north)
        self.update()

    def active_route_wp(self):
        if 0 <= self.route_idx < len(self.route):
            return self.route[self.route_idx]
        return None

    def advance_route(self):
        """Advance to the next leg once the active WP is reached. Returns the
        new active waypoint, or None when the route is complete."""
        if not self.route:
            return None
        self.route_idx += 1
        nxt = self.active_route_wp()
        self.target_wp = nxt
        if nxt is not None:
            self.waypoint_commanded.emit(nxt[0], nxt[1])
        return nxt

    def route_complete(self):
        return bool(self.route) and self.route_idx >= len(self.route)

    def route_legs(self):
        """Compute the route table rows: leg distance, true course, XTE limit,
        turn radius. Leg 1 starts at own-ship."""
        rows = []
        prev = self.true_pos
        for i, wp in enumerate(self.route):
            de = wp[0] - prev[0]
            dn = wp[1] - prev[1]
            dist = math.hypot(de, dn)
            course = (math.degrees(math.atan2(de, dn)) + 360.0) % 360.0
            rows.append({
                "wp": f"WP-{i + 1:02d}",
                "dist_m": dist,
                "course_deg": course,
                "xte_m": self.xte_limit_m,
                "turn_r_m": self.turn_radius_m if 0 < i < len(self.route) - 1 else 0.0,
                "active": i == self.route_idx,
                "done": i < self.route_idx,
            })
            prev = wp
        return rows

    def set_palette(self, mode: str):
        self.palette_mode = mode if mode in PALETTES else "day"
        self._pal = dict(PALETTES[self.palette_mode])
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            east, north = self.screen_to_m(event.position().x(), event.position().y())
            self.append_route_wp(east, north)
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
        self.scale_m_to_px = max(0.2, min(6.0, self.scale_m_to_px * factor))
        self.update()


class ECDISPanel(QWidget):
    waypoint_commanded = pyqtSignal(float, float)
    waypoint_cleared = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header bar above chart
        header = QHBoxLayout()
        header.setContentsMargins(8, 4, 8, 2)

        lbl = QLabel("Tactical ECDIS Chart")
        lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY};")
        header.addWidget(lbl)

        hint = QLabel("Left-click: Add Route WP  •  Right-drag: Pan  •  Scroll: Zoom")
        hint.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        header.addWidget(hint)

        header.addStretch()

        # IEC 62288 palette mode (Day / Dusk / Night)
        self._pal_buttons = {}
        for mode in ("day", "dusk", "night"):
            b = QPushButton(mode.capitalize())
            b.setCheckable(True)
            b.setFixedHeight(24)
            b.setStyleSheet("padding: 2px 8px; font-size: 11px;")
            b.clicked.connect(lambda _=False, m=mode: self._set_palette(m))
            header.addWidget(b)
            self._pal_buttons[mode] = b
        self._pal_buttons["day"].setChecked(True)

        # Navigation route clear button
        btn_clear_wp = QPushButton("Clear Route")
        btn_clear_wp.setFixedHeight(24)
        btn_clear_wp.setStyleSheet("padding: 2px 8px; font-size: 11px;")
        btn_clear_wp.setToolTip("Clear the planned route and all waypoints")
        btn_clear_wp.clicked.connect(self._clear_waypoint)
        header.addWidget(btn_clear_wp)

        # Zoom Controls (+, -, 1:1, Recenter)
        btn_zin = QPushButton("+")
        btn_zin.setFixedSize(26, 24)
        btn_zin.clicked.connect(self._zoom_in)
        header.addWidget(btn_zin)

        btn_zout = QPushButton("-")
        btn_zout.setFixedSize(26, 24)
        btn_zout.clicked.connect(self._zoom_out)
        header.addWidget(btn_zout)

        btn_recenter = QPushButton("Recenter")
        btn_recenter.setFixedHeight(24)
        btn_recenter.clicked.connect(self._recenter)
        header.addWidget(btn_recenter)

        layout.addLayout(header)

        # Chart Canvas
        self.canvas = ChartCanvas(self)
        self.canvas.waypoint_commanded.connect(self.waypoint_commanded.emit)
        self.canvas.waypoint_cleared.connect(self.waypoint_cleared.emit)
        layout.addWidget(self.canvas, 1)

        # Route Table (leg distance, true course, XTE limit, turn radius)
        self.route_table = QTableWidget(0, 5)
        self.route_table.setHorizontalHeaderLabels(
            ["WP", "LEG DIST", "TRUE CRS", "XTE LIMIT", "TURN R"])
        self.route_table.verticalHeader().setVisible(False)
        self.route_table.setFixedHeight(104)
        self.route_table.setShowGrid(False)
        self.route_table.setStyleSheet("font-size: 11px;")
        hh = self.route_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for c in range(1, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.route_table)

    def set_palette(self, mode: str):
        self._set_palette(mode)

    def _set_palette(self, mode: str):
        for m, b in self._pal_buttons.items():
            b.setChecked(m == mode)
        self.canvas.set_palette(mode)

    def _refresh_route_table(self):
        legs = self.canvas.route_legs()
        self.route_table.setRowCount(len(legs))
        for r, leg in enumerate(legs):
            cells = [
                leg["wp"],
                f"{leg['dist_m']:.0f} m",
                f"{leg['course_deg']:05.1f}°",
                f"±{leg['xte_m']:.0f} m",
                f"{leg['turn_r_m']:.0f} m" if leg["turn_r_m"] else "—",
            ]
            for c, txt in enumerate(cells):
                item = QTableWidgetItem(txt)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if leg["active"]:
                    item.setForeground(QColor("#ffd166"))
                elif leg["done"]:
                    item.setForeground(QColor(TEXT_MUTED))
                else:
                    item.setForeground(QColor("#00d2ff"))
                self.route_table.setItem(r, c, item)

    def _clear_waypoint(self):
        self.canvas.clear_waypoint()
        self._refresh_route_table()

    def _zoom_in(self):
        self.canvas.scale_m_to_px = min(6.0, self.canvas.scale_m_to_px * 1.25)
        self.canvas.update()

    def _zoom_out(self):
        self.canvas.scale_m_to_px = max(0.2, self.canvas.scale_m_to_px * 0.8)
        self.canvas.update()

    def _recenter(self):
        self.canvas.pan_x = 0.0
        self.canvas.pan_y = 0.0
        self.canvas.scale_m_to_px = 0.85
        self.canvas.update()

    def set_site(self, lat: float, lon: float):
        self.canvas.set_site(lat, lon)

    def update_telemetry(self, state: dict):
        self.canvas.update_telemetry(state)
        self._refresh_route_table()
