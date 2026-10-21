#!/usr/bin/env python3
"""
Maritime Cyber Range -- first-person operator console (pygame + OpenGL).

ONE window, no Gazebo window, no browser. Pick a SITE and VEHICLE; the app boots
the real physics backend (ArduPilot SITL + Gazebo hydrodynamics) HEADLESS, then
renders a 3D FIRST-PERSON ocean from live MAVLink telemetry: real waves
(from the site sea state), the vehicle in the water, a destination you aim by
clicking the sea, and attack controls -- no Gazebo window, no browser.

Run:  tools/app.sh      (needs $DISPLAY + pygame). Authorized lab/range use only.
"""
import math
import os
import subprocess
import sys
import threading
import time

import pygame

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "attacks"))
from pymavlink import mavutil
try:
    from scaleup.sites import load_site, list_sites
    SITE_IDS = [s.id for s in list_sites()]
    SITE_OBJ = {s.id: s for s in list_sites()}
except Exception:
    SITE_IDS = ["kochi", "mumbai", "visakhapatnam"]
    SITE_OBJ = {}
    load_site = None

TWINS = [
    ("interceptor_usv", "surface",    "Fast Interceptor USV", "A2NCS · ~16 m · ArduRover"),
    ("survey_usv",      "surface",    "Coastal Survey USV",   "catamaran · ArduRover"),
    ("maya_auv",        "underwater", "Maya AUV",             "CSIR-NIO · 1.7 m · ArduSub"),
    ("auv150",          "underwater", "AUV-150",              "CSIR-CMERI · 4.8 m · ArduSub"),
]
ATTACKS = [("GPS spoof", "spoof the GNSS/FDM position"),
           ("C2 mode", "forge an unauthenticated SET_MODE"),
           ("C2 override", "seize throttle (RC_CHANNELS_OVERRIDE)"),
           ("AIS ghost", "inject a phantom AIS contact")]

# ---- professional console palette -----------------------------------------
BG   = (13, 17, 23)
BG2  = (22, 27, 34)
BG3  = (31, 38, 48)
HOVER= (42, 52, 64)
LINE = (44, 54, 66)
INK  = (205, 215, 226)
MUTE = (120, 134, 150)
ACC  = (86, 170, 205)      # cyan accent
OKC  = (92, 196, 140)
WARN = (223, 165, 70)
BAD  = (214, 96, 96)
# site water (muted, realistic): (deep, shallow)
WATER = {
    "kochi":         ((10, 42, 54), (18, 70, 80)),
    "mumbai":        ((14, 46, 48), (26, 74, 70)),
    "visakhapatnam": ((10, 48, 58), (20, 78, 86)),
}
W, H = 1280, 800
TOP = 48
STAT = 26
CHART = pygame.Rect(0, TOP, 912, H - TOP - STAT)
PANEL = pygame.Rect(912, TOP, W - 912, H - TOP - STAT)
DEG_M = 111320.0


class Backend:
    def __init__(self):
        self.site = "kochi"; self.twin = None; self.domain = "surface"
        self.conn = None; self.lock = threading.Lock()
        self.state = dict(lat=None, lon=None, hdg=0.0, depth=0.0, speed=0.0,
                          mode="--", armed=False, hb=0)
        self.home = (9.9, 76.2); self.cur_ne = (0.0, 0.0); self.cur_spd = 0.0
        self.track = []; self.events = []
        self.booting = False; self.connected = False; self._stop = False
        self.active_attack = None; self._ac = None

    def log(self, m):
        self.events.append((time.strftime('%H:%M:%S'), m)); self.events[:] = self.events[-40:]

    def site_env(self):
        s = SITE_OBJ.get(self.site) or (load_site(self.site) if load_site else None)
        if s:
            self.home = tuple(s.position); self.cur_ne = s.current_ne()
            self.cur_spd = s.current.get("speed_mps", 0.0)

    def boot(self, site, twin, domain):
        self.site, self.twin, self.domain = site, twin, domain
        self.site_env(); self.booting = True
        self.log(f"booting {twin} @ {site} — starting headless physics")
        env = dict(os.environ, MCR_SITE=site)
        subprocess.Popen(["bash", f"{REPO}/tools/run_vehicle.sh", f"vehicle_twins/{twin}", "up"],
                         cwd=REPO, env=env, stdout=open(f"/tmp/mcr_app_{twin}.log", "w"),
                         stderr=subprocess.STDOUT)
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self._stop and self.conn is None:
            try:
                c = mavutil.mavlink_connection("udpin:127.0.0.1:14554", source_system=250)
                if c.wait_heartbeat(timeout=5) is not None:
                    self.conn = c; break
            except Exception:
                pass
            time.sleep(2)
        if self.conn is None:
            return
        self.booting = False; self.connected = True; self.log("connected — live telemetry")
        if self.domain == "underwater":
            threading.Thread(target=self._start_extnav, daemon=True).start()
        self.conn.mav.request_data_stream_send(self.conn.target_system, self.conn.target_component,
                                               mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
        mm = {v: k for k, v in (self.conn.mode_mapping() or {}).items()}
        while not self._stop:
            msg = self.conn.recv_match(blocking=True, timeout=1)
            if msg is None:
                continue
            t = msg.get_type()
            with self.lock:
                if t == "GLOBAL_POSITION_INT" and not (msg.lat == 0 and msg.lon == 0):
                    self.state["lat"], self.state["lon"] = msg.lat/1e7, msg.lon/1e7
                    if msg.hdg != 65535:
                        self.state["hdg"] = msg.hdg/100.0
                    self.state["depth"] = max(0.0, -msg.relative_alt/1000.0)
                    self.track.append((self.state["lat"], self.state["lon"])); self.track[:] = self.track[-500:]
                elif t == "VFR_HUD":
                    self.state["speed"] = msg.groundspeed
                elif t == "HEARTBEAT" and msg.type != mavutil.mavlink.MAV_TYPE_GCS:
                    self.state["armed"] = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    self.state["mode"] = mm.get(msg.custom_mode, str(msg.custom_mode)); self.state["hb"] += 1

    def _start_extnav(self):
        """Submerged AUVs fix horizontal position from ExternalNav (USBL/DVL),
        not GPS -- feed the TRUE Gazebo position as VISION_POSITION_ESTIMATE so
        the AUV has a position to navigate on and to display (USBL aiding)."""
        model = {"maya_auv": "remus100", "auv150": "bluerov2"}.get(self.twin, self.twin)
        try:
            import acoustic_spoof as AC
        except Exception as e:
            self.log(f"ExternalNav feed unavailable: {e}"); return
        AC.ODOM_TOPIC = f"/model/{model}/odometry"
        AC.ATTACK_LOG_PATH = f"/tmp/mcr_app_extnav_{self.twin}.csv"
        try:
            fc = mavutil.mavlink_connection("tcp:127.0.0.1:5762", source_system=1, source_component=197)
            if fc.wait_heartbeat(timeout=25) is None:
                self.log("ExternalNav: no heartbeat on 5762"); return
        except Exception as e:
            self.log(f"ExternalNav feed failed: {e}"); return
        AC.state.active = False      # transparent: feed TRUE position (USBL aiding)
        self._ac = AC
        threading.Thread(target=AC.run_feed, args=(fc,), daemon=True).start()
        self.log("ExternalNav (USBL) online — AUV positioning up")

    def _arm_once(self):
        self.conn.mav.command_long_send(self.conn.target_system, self.conn.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)

    def arm(self):
        if not self.conn:
            return
        self.log("ARM — retrying until confirmed")
        threading.Thread(target=self._arm_hold, args=(8.0,), daemon=True).start()

    def _arm_hold(self, secs):
        t0 = time.time()
        while time.time()-t0 < secs and not self.state.get("armed"):
            self._arm_once(); time.sleep(1.0)

    def disarm(self):
        if not self.conn:
            return
        self.conn.mav.command_long_send(self.conn.target_system, self.conn.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 0, 0, 0, 0, 0, 0)
        self.log("DISARM sent")

    def goto(self, lat, lon):
        if not self.conn:
            return
        self.log(f"destination set — {lat:.5f}, {lon:.5f}")
        threading.Thread(target=self._drive, args=(lat, lon), daemon=True).start()

    def _drive(self, lat, lon):
        c = self.conn; mm = c.mode_mapping() or {}
        if "GUIDED" in mm:
            c.set_mode(mm["GUIDED"])
        end = time.time()+120
        while not self._stop and time.time() < end:
            if not self.state.get("armed"):
                self._arm_once()
                if "GUIDED" in mm:
                    c.set_mode(mm["GUIDED"])
            c.mav.set_position_target_global_int_send(
                0, c.target_system, c.target_component,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                0b0000111111111000, int(lat*1e7), int(lon*1e7), 0, 0, 0, 0, 0, 0, 0, 0, 0)
            with self.lock:
                clat, clon = self.state.get("lat"), self.state.get("lon")
            if clat is not None and DEG_M*math.hypot(clat-lat, (clon-lon)*math.cos(math.radians(lat))) < 3.0:
                self.log("arrived at destination"); break
            time.sleep(1.0)

    def attack(self, name):
        if not self.conn:
            return
        self.active_attack = name; c = self.conn
        if name in ("GPS spoof", "Acoustic spoof"):
            if self.domain == "underwater" and getattr(self, "_ac", None):
                # submerged: the position channel is acoustic/ExternalNav, not GPS
                with self._ac._lock:
                    self._ac.state.mode = "step"; self._ac.state.start_time = time.time(); self._ac.state.active = True
                self.log("ATTACK · acoustic/ExternalNav position spoof (step)")
            else:
                try:
                    open(f"/tmp/mcr_run/{self.twin}/relay.fifo", "w").write("step\n")
                    self.log("ATTACK · GPS spoof injected (FDM relay step)")
                except OSError:
                    self.log("GPS spoof needs the FDM relay (surface twins)")
        elif name == "C2 mode":
            mm = c.mode_mapping() or {}
            tgt = next((m for m in ("MANUAL", "HOLD", "ALT_HOLD") if m in mm), None)
            if tgt:
                c.mav.set_mode_send(c.target_system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mm[tgt])
                self.log(f"ATTACK · forged SET_MODE → {tgt}")
        elif name == "C2 override":
            for _ in range(12):
                c.mav.rc_channels_override_send(c.target_system, c.target_component, 1500, 0, 1850, 0, 0, 0, 0, 0)
                time.sleep(0.04)
            self.log("ATTACK · RC_CHANNELS_OVERRIDE — throttle seized")
        elif name == "AIS ghost":
            self.log("ATTACK · AIS ghost contact (operator-layer)")

    def stop_attack(self):
        name = self.active_attack
        if not name:
            return
        c = self.conn
        if name in ("GPS spoof", "Acoustic spoof"):
            if self.domain == "underwater" and self._ac:
                with self._ac._lock:
                    self._ac.state.active = False
            else:
                try:
                    open(f"/tmp/mcr_run/{self.twin}/relay.fifo", "w").write("off\n")
                except OSError:
                    pass
        elif name == "C2 override":
            if c:
                c.mav.rc_channels_override_send(c.target_system, c.target_component, 0, 0, 0, 0, 0, 0, 0, 0)
        elif name == "C2 mode":
            if c:
                mm = c.mode_mapping() or {}
                if "GUIDED" in mm:
                    c.set_mode(mm["GUIDED"])
        self.active_attack = None
        self.log(f"attack stopped — {name}")

    def teardown(self):
        self._stop = True
        if self.twin:
            subprocess.Popen(["bash", f"{REPO}/tools/run_vehicle.sh", f"vehicle_twins/{self.twin}", "down"],
                             cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def geo_px(lat, lon, home, scale):
    dn = (lat-home[0])*DEG_M
    de = (lon-home[1])*DEG_M*math.cos(math.radians(home[0]))
    return (CHART.centerx + de*scale, CHART.centery - dn*scale)


def px_geo(px, py, home, scale):
    de = (px-CHART.centerx)/scale; dn = -(py-CHART.centery)/scale
    return (home[0]+dn/DEG_M, home[1]+de/(DEG_M*math.cos(math.radians(home[0]))))


import ocean3d
from OpenGL.GL import *
from OpenGL.GLU import gluUnProject

# ---- professional console palette (overlay HUD) ---------------------------
BG   = (13, 17, 23); BG2 = (22, 27, 34, 232); BG3 = (31, 38, 48)
HOVER= (46, 56, 70); LINE = (60, 72, 86); INK  = (210, 220, 230); MUTE = (140, 154, 170)
ACC  = (86, 180, 215); OKC = (92, 206, 150); WARN = (233, 175, 80); BAD = (224, 106, 106)
SITE_WATER_GL = {
    "kochi":         (0.03, 0.20, 0.28),
    "mumbai":        (0.04, 0.20, 0.24),
    "visakhapatnam": (0.03, 0.22, 0.30),
}


class App:
    def __init__(self):
        pygame.init()
        self.W, self.H = 1280, 800
        pygame.display.set_mode((self.W, self.H), pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE)
        pygame.display.set_caption("Maritime Cyber Range — Operator Console")
        self.clock = pygame.time.Clock()
        self.f  = pygame.font.SysFont("dejavusans", 14)
        self.fs = pygame.font.SysFont("dejavusans", 11)
        self.fb = pygame.font.SysFont("dejavusans", 15, bold=True)
        self.fh = pygame.font.SysFont("dejavusans", 22, bold=True)
        self.fm = pygame.font.SysFont("dejavusansmono", 14)
        self.fms = pygame.font.SysFont("dejavusansmono", 11)
        self.ocean = ocean3d.Ocean3D(self.W, self.H)
        self.ocean.setup_gl()
        self._init_gl_resources()
        self.be = Backend()
        self.mode = "MENU"; self.sel_site = 0; self.sel_twin = 0
        self.t = 0.0; self.comps = None; self.site_gl = (0.03, 0.20, 0.28)
        self.dest = None; self.setting_dest = False
        self.cam_f = 0.0; self.cam_target = 0.0      # 0 = third-person, 1 = first-person
        self.buttons = {}; self.mouse = (0, 0)
        self._mv = self._pr = self._vp = None

    def _init_gl_resources(self):
        self.tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        self.ov = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        self.PANEL = pygame.Rect(self.W-300, 48, 300, self.H-48-26)

    def _resize(self, w, h):
        self.W, self.H = max(1000, w), max(640, h)
        pygame.display.set_mode((self.W, self.H), pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE)
        glViewport(0, 0, self.W, self.H)
        self.ocean.resize(self.W, self.H); self.ocean.setup_gl()
        self._init_gl_resources()

    def _camera(self):
        st = self.be.state; hd = math.radians(st["hdg"])
        fwd = (math.sin(hd), math.cos(hd)); under = self.be.domain == "underwater"
        if under:
            fpv   = ((-fwd[0]*6.5, -fwd[1]*6.5, 2.2), (fwd[0]*9, fwd[1]*9, -1.5))
            third = ((-fwd[0]*11, -fwd[1]*11, 5.5),   (fwd[0]*2, fwd[1]*2, -2.5))
        else:
            fpv   = ((-fwd[0]*8, -fwd[1]*8, 3.0), (fwd[0]*14, fwd[1]*14, 0))
            third = ((-fwd[0]*26, -fwd[1]*26, 17), (fwd[0]*6, fwd[1]*6, -1))
        f = self.cam_f
        eye = tuple(third[0][i] + (fpv[0][i]-third[0][i])*f for i in range(3))
        ctr = tuple(third[1][i] + (fpv[1][i]-third[1][i])*f for i in range(3))
        return (eye, ctr, (0, 0, 1)), 64 - 6*f

    # ---------- overlay 2D helpers (draw onto self.ov) ----------
    def txt(self, s, x, y, font=None, col=INK):
        self.ov.blit((font or self.f).render(s, True, col), (x, y))
    def txtr(self, s, x, y, font=None, col=INK):
        im = (font or self.f).render(s, True, col); self.ov.blit(im, (x-im.get_width(), y))
    def txtc(self, s, cx, y, font=None, col=INK):
        im = (font or self.f).render(s, True, col); self.ov.blit(im, (cx-im.get_width()//2, y))
    def rect(self, col, r, width=0, rad=0):
        pygame.draw.rect(self.ov, col, r, width, border_radius=rad)

    def button(self, key, r, label, *, active=False, danger=False, sub=None, enabled=True):
        self.buttons[key] = r if enabled else None
        hover = enabled and r.collidepoint(self.mouse)
        fill = BG3
        if active: fill = (40, 78, 92)
        elif hover: fill = HOVER
        elif not enabled: fill = (26, 30, 36)
        self.rect(fill, r);
        edge = ACC if (active or hover) else LINE
        if danger and (hover or active): edge = BAD
        self.rect(edge, r, 1)
        if active: self.rect(ACC if not danger else BAD, (r.x, r.y, 3, r.h))
        col = INK if enabled else MUTE
        self.ov.blit(self.f.render(label, True, col), (r.x+12, r.centery - 7 - (6 if sub else 0)))
        if sub: self.ov.blit(self.fs.render(sub, True, MUTE), (r.x+12, r.centery+2))

    def section(self, label, x, y, w=268):
        self.txt(label.upper(), x, y, self.fs, MUTE)
        pygame.draw.line(self.ov, LINE, (x, y+16), (x+w, y+16), 1)
        return y+26

    # ---------- 3D scene ----------
    def scene(self):
        st = self.be.state
        hdg = st["hdg"]; depth = st.get("depth", 0.0)
        under = self.be.domain == "underwater"
        if self.comps is None:
            self._rebuild_waves()
        cam, fov = self._camera()
        self.ocean.render(self.t, self.comps, hdg, st["speed"], self.site_gl,
                          under, cam, self.be.twin, depth=depth, fov=fov)
        # destination beacon in 3D (relative to vehicle)
        if self.dest and st["lat"] is not None:
            de = (self.dest[1]-st["lon"])*DEG_M*math.cos(math.radians(st["lat"]))
            dn = (self.dest[0]-st["lat"])*DEG_M
            self._beacon(de, dn)
        # cache matrices for unproject (destination picking)
        self._mv = glGetDoublev(GL_MODELVIEW_MATRIX)
        self._pr = glGetDoublev(GL_PROJECTION_MATRIX)
        self._vp = glGetIntegerv(GL_VIEWPORT)

    def _rebuild_waves(self):
        s = SITE_OBJ.get(self.be.site)
        hs = s.sea_state["sig_wave_height_m"] if s else 1.2
        tp = s.sea_state["period_s"] if s else 7.0
        brg = s.current.get("bearing_deg", 160) if s else 160
        self.comps = ocean3d.gerstner_components(hs, tp, brg)
        self.site_gl = SITE_WATER_GL.get(self.be.site, (0.03, 0.20, 0.28))

    def _beacon(self, east, north):
        d = math.hypot(east, north)
        if d > 260: east, north = east*260/d, north*260/d
        glDisable(GL_LIGHTING); glDisable(GL_FOG)
        glLineWidth(3)
        glColor4f(0.5, 1.0, 0.65, 1.0)
        glBegin(GL_LINES)
        glVertex3f(east, north, 0.0); glVertex3f(east, north, 8.0)
        glEnd()
        glLineWidth(1)
        glEnable(GL_LIGHTING); glEnable(GL_FOG)

    # ---------- overlay compositing ----------
    def present(self):
        data = pygame.image.tostring(self.ov, "RGBA", False)
        glBindTexture(GL_TEXTURE_2D, self.tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.W, self.H, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        glDisable(GL_DEPTH_TEST); glDisable(GL_LIGHTING); glDisable(GL_FOG); glEnable(GL_TEXTURE_2D)
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, self.W, 0, self.H, -1, 1)
        glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
        glColor4f(1, 1, 1, 1)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 1); glVertex2f(0, 0); glTexCoord2f(1, 1); glVertex2f(self.W, 0)
        glTexCoord2f(1, 0); glVertex2f(self.W, self.H); glTexCoord2f(0, 0); glVertex2f(0, self.H)
        glEnd()
        glDisable(GL_TEXTURE_2D)
        glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW); glPopMatrix()
        glEnable(GL_DEPTH_TEST); glEnable(GL_LIGHTING)

    # ---------- HUD overlay ----------
    def draw_hud(self):
        self.ov.fill((0, 0, 0, 0))
        self.buttons = {}
        st = self.be.state; P = self.PANEL
        # top bar (translucent)
        tb = pygame.Surface((self.W, 48), pygame.SRCALPHA); tb.fill((13, 17, 23, 210)); self.ov.blit(tb, (0, 0))
        pygame.draw.line(self.ov, LINE, (0, 48), (self.W, 48), 1)
        pygame.draw.rect(self.ov, ACC, (0, 0, 4, 48))
        self.txt("MARITIME CYBER RANGE", 18, 14, self.fb)
        self.txt(f"{self.be.twin or '—'}", 300, 15, self.fm)
        self.txt(f"site {self.be.site}", 470, 16, self.f, MUTE)
        state = ("LIVE", OKC) if self.be.connected else (("BOOTING", WARN) if self.be.booting else ("IDLE", MUTE))
        pr = pygame.Rect(self.W-310-16, 12, 92, 24); self.rect(BG3, pr); self.rect(state[1], pr, 1)
        pygame.draw.circle(self.ov, state[1], (pr.x+14, pr.centery), 4); self.txt(state[0], pr.x+26, pr.y+4, self.fs, state[1])
        # right panel (translucent)
        pan = pygame.Surface((P.w, P.h), pygame.SRCALPHA); pan.fill(BG2); self.ov.blit(pan, (P.x, P.y))
        pygame.draw.line(self.ov, LINE, (P.x, P.y), (P.x, P.bottom), 1)
        x = P.x+16; y = self.section("Telemetry", x, P.y+14)
        rows = [("LAT", f"{st['lat']:.5f}" if st['lat'] else "—"), ("LON", f"{st['lon']:.5f}" if st['lon'] else "—"),
                ("HDG", f"{st['hdg']:05.1f}°"), ("SOG", f"{st['speed']:4.2f} m/s"),
                ("DEPTH", f"{st['depth']:4.1f} m" if self.be.domain == "underwater" else "surface"), ("MODE", st['mode'])]
        for k, v in rows:
            self.txt(k, x, y, self.fs, MUTE); self.txt(v, x+72, y-1, self.fm); y += 21
        self.txt("ARMED", x, y, self.fs, MUTE); self.txt("ARMED" if st['armed'] else "SAFE", x+72, y-1, self.fm, BAD if st['armed'] else OKC); y += 26
        if self.dest and st['lat']:
            d = DEG_M*math.hypot(self.dest[0]-st['lat'], (self.dest[1]-st['lon'])*math.cos(math.radians(st['lat'])))
            self.txt("DEST", x, y, self.fs, MUTE); self.txt(f"{d:5.0f} m ahead", x+72, y-1, self.fm, (120, 230, 170)); y += 24
        y = self.section("Navigation", x, y+4)
        self.button("arm", pygame.Rect(x, y, 84, 32), "ARM", active=st['armed'], enabled=self.be.connected)
        self.button("disarm", pygame.Rect(x+92, y, 84, 32), "DISARM", enabled=self.be.connected)
        self.button("switch", pygame.Rect(x+184, y, 84, 32), "SWITCH"); y += 40
        self.button("dest", pygame.Rect(x, y, 268, 32), "AIM — click the water" if self.setting_dest else "SET DESTINATION",
                    active=self.setting_dest, enabled=self.be.connected); y += 42
        y = self.section("Attacks", x, y)
        if self.be.domain == "underwater":
            atk_list = [("Acoustic spoof", "spoof the USBL/ExternalNav position"),
                        ("C2 mode", "forge an unauthenticated SET_MODE"),
                        ("C2 override", "seize throttle (RC_CHANNELS_OVERRIDE)")]
        else:
            atk_list = [("GPS spoof", "spoof the GNSS/FDM position"),
                        ("C2 mode", "forge an unauthenticated SET_MODE"),
                        ("C2 override", "seize throttle (RC_CHANNELS_OVERRIDE)"),
                        ("AIS ghost", "inject a phantom AIS contact")]
        for a, desc in atk_list:
            self.button(f"atk:{a}", pygame.Rect(x, y, 268, 34), a, sub=desc, active=self.be.active_attack == a, danger=True, enabled=self.be.connected); y += 38
        self.button("stopatk", pygame.Rect(x, y, 268, 30), "STOP ATTACK", danger=True, enabled=bool(self.be.active_attack)); y += 38
        y = self.section("Event log", x, y+2)
        logh = max(60, P.bottom-44-y)
        self.rect((10, 13, 18, 220), (x, y, 268, logh)); self.rect(LINE, (x, y, 268, logh), 1)
        maxrows = (logh-10)//16
        for i, (ts, m) in enumerate(self.be.events[-maxrows:]):
            yy = y+6+i*16
            self.txt(ts, x+8, yy, self.fms, MUTE)
            self.txt(m[:29], x+72, yy, self.fms, INK)
        self.button("quit", pygame.Rect(x, P.bottom-36, 268, 28), "STOP & QUIT", danger=True)
        # bottom status strip
        bs = pygame.Surface((self.W-P.w, 26), pygame.SRCALPHA); bs.fill((13, 17, 23, 210)); self.ov.blit(bs, (0, self.H-26))
        view = "third-person" if self.cam_f < 0.5 else "first-person"
        self.txt(f"{view} view · drag window edge / maximize to resize · physics: headless SITL + Gazebo hydro",
                 14, self.H-20, self.fms, MUTE)
        self.txtr(f"{int(self.clock.get_fps())} fps", self.W-P.w-14, self.H-20, self.fms, MUTE)
        # aiming reticle
        if self.setting_dest and self.mouse[0] < P.x:
            mx, my = self.mouse
            pygame.draw.circle(self.ov, (120, 230, 170), (mx, my), 10, 1)
            pygame.draw.line(self.ov, (120, 230, 170), (mx-15, my), (mx+15, my), 1)
            pygame.draw.line(self.ov, (120, 230, 170), (mx, my-15), (mx, my+15), 1)
        # booting overlay
        if self.be.booting:
            bo = pygame.Surface((P.x, self.H-48-26), pygame.SRCALPHA); bo.fill((13, 17, 23, 180)); self.ov.blit(bo, (0, 48))
            cx, cy = P.x//2, self.H//2
            self.txtc("STARTING PHYSICS ENGINE", cx, cy-24, self.fh)
            self.txtc(f"booting {self.be.twin} at {self.be.site} — headless (≈60–90 s)", cx, cy+8, self.f, MUTE)
            n = int(self.t*3) % 4; self.txtc("●"*n + "○"*(3-n), cx, cy+34, self.f, ACC)

    # ---------- menu ----------
    def draw_menu(self):
        self.ov.fill(BG); self.buttons = {}
        card = pygame.Rect(self.W//2-430, 90, 860, 600)
        self.rect((22, 27, 34), card); self.rect(LINE, card, 1); self.rect(ACC, (card.x, card.y, 4, card.h))
        self.txt("MARITIME CYBER RANGE", card.x+34, card.y+28, self.fh)
        self.txt("First-person operator console — select a test site and a vehicle.", card.x+34, card.y+62, self.f, MUTE)
        x = card.x+34; y = self.section("Test site", x, card.y+104, 790)
        for i, s in enumerate(SITE_IDS):
            so = SITE_OBJ.get(s); name = so.name.split(" —")[0].split(" (")[0] if so else s.title()
            self.button(f"site:{i}", pygame.Rect(x+i*262, y, 250, 44), name, active=i == self.sel_site, sub=(so.region[:32] if so else None))
        y = self.section("Vehicle", x, y+66, 790)
        for i, (tw, dom, nm, sub) in enumerate(TWINS):
            self.button(f"twin:{i}", pygame.Rect(x+(i % 2)*406, y+(i//2)*54, 394, 46), nm, active=i == self.sel_twin, sub=f"{sub} · {dom}")
        self.button("start", pygame.Rect(x, card.bottom-70, 240, 42), "START RUN", active=True)
        self.txt("Physics runs headless (real ArduPilot + Gazebo hydrodynamics).", x+256, card.bottom-58, self.fs, MUTE)

    # ---------- events ----------
    def unproject_dest(self, mx, my):
        if self._mv is None or self.be.state["lat"] is None:
            return
        wy = self.H - my
        p0 = gluUnProject(mx, wy, 0.0, self._mv, self._pr, self._vp)
        p1 = gluUnProject(mx, wy, 1.0, self._mv, self._pr, self._vp)
        dz = p1[2]-p0[2]
        if abs(dz) < 1e-6:
            return
        tt = -p0[2]/dz
        if tt < 0:
            return
        east = p0[0]+tt*(p1[0]-p0[0]); north = p0[1]+tt*(p1[1]-p0[1])
        d = math.hypot(east, north)
        if d > 300:
            east, north = east*300/d, north*300/d
        vlat, vlon = self.be.state["lat"], self.be.state["lon"]
        lat = vlat + north/DEG_M; lon = vlon + east/(DEG_M*math.cos(math.radians(vlat)))
        self.dest = (lat, lon); self.be.goto(lat, lon); self.setting_dest = False
        self.cam_target = 1.0      # smooth transition to first-person once under way

    def on_click(self, pos):
        for key, r in self.buttons.items():
            if r and r.collidepoint(pos):
                return self.on_button(key)
        if self.mode == "LIVE" and self.setting_dest and pos[0] < self.PANEL.x and pos[1] > 48:
            self.unproject_dest(*pos)

    def on_button(self, key):
        if key.startswith("site:"): self.sel_site = int(key[5:])
        elif key.startswith("twin:"): self.sel_twin = int(key[5:])
        elif key == "start":
            tw, dom, _, _ = TWINS[self.sel_twin]
            self.be.boot(SITE_IDS[self.sel_site], tw, dom); self.comps = None; self.mode = "LIVE"
        elif key == "arm": self.be.arm()
        elif key == "disarm": self.be.disarm()
        elif key == "dest": self.setting_dest = not self.setting_dest
        elif key.startswith("atk:"): threading.Thread(target=self.be.attack, args=(key[4:],), daemon=True).start()
        elif key == "stopatk": threading.Thread(target=self.be.stop_attack, daemon=True).start()
        elif key == "switch":
            self.be.teardown(); self.be = Backend()
            self.mode = "MENU"; self.dest = None; self.comps = None
            self.cam_f = 0.0; self.cam_target = 0.0; self.setting_dest = False
        elif key == "quit": self.running = False

    def run(self):
        self.running = True
        while self.running:
            self.t += self.clock.get_time()/1000.0
            self.mouse = pygame.mouse.get_pos()
            clicks = [e.pos for e in pygame.event.get(pygame.MOUSEBUTTONDOWN) if e.button == 1]
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                elif e.type == pygame.VIDEORESIZE:
                    self._resize(e.w, e.h)
            for pos in clicks:
                self.on_click(pos)
            if self.be.connected and self.comps is None:
                self._rebuild_waves()
            # ease the camera between third-person (0) and first-person (1)
            dt = self.clock.get_time()/1000.0
            if self.cam_f < self.cam_target:
                self.cam_f = min(self.cam_target, self.cam_f + dt/1.6)
            elif self.cam_f > self.cam_target:
                self.cam_f = max(self.cam_target, self.cam_f - dt/1.0)
            if self.mode == "MENU":
                glClearColor(0.05, 0.07, 0.09, 1); glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                self.draw_menu()
            else:
                if self.be.connected:
                    self.scene()
                else:
                    glClearColor(0.05, 0.09, 0.12, 1); glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                self.draw_hud()
            self.present()
            pygame.display.flip()
            self.clock.tick(45)
        self.be.teardown(); pygame.quit()


if __name__ == "__main__":
    App().run()
