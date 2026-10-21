#!/usr/bin/env python3
"""
3D ocean renderer (PyOpenGL) for the Maritime Cyber Range app.

The water is a Gerstner-wave field whose amplitude/wavelength come from the
SITE's real sea state (significant wave height Hs, peak period Tp from
scaleup.physics.seastate) and whose direction follows the site current -- the
sea is driven by the site's measured physics. Camera is supplied by the app
(third-person wide for picking a destination, first-person once under way, with
a smooth transition between them). Vehicles are modelled per type (boat hulls /
torpedo AUVs). Legacy GL (compatibility profile) so it runs on Mesa.
"""
import math
import os
import sys

from OpenGL.GL import *
from OpenGL.GLU import *

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
_G = 9.81


# ---------------------------------------------------------------- wave model
def gerstner_components(hs, tp, bearing_deg):
    """Directional Gerstner components approximating the site sea state.
    amplitude from Hs, wavelength from Tp via deep-water dispersion."""
    comps = []
    base = math.radians(bearing_deg)
    specs = [(1.0, tp, 0.0), (0.45, tp*0.7, 0.5), (0.28, tp*0.45, -0.7), (0.16, tp*0.3, 1.1)]
    amp_scale = max(0.15, hs) * 0.5
    for frac, T, dang in specs:
        T = max(T, 1.4); w = 2*math.pi/T
        L = _G*T*T/(2*math.pi); k = 2*math.pi/L
        ang = base + dang
        comps.append((amp_scale*frac, k*math.cos(ang), k*math.sin(ang), w, frac*1.7, 0.55*frac))
    return comps


def wave_point(x, y, t, comps):
    dx = dy = h = nx = ny = 0.0
    for a, kx, ky, w, ph, s in comps:
        kmag = (kx*kx+ky*ky)**0.5 + 1e-6
        ph_ = kx*x + ky*y - w*t + ph
        c = math.cos(ph_); si = math.sin(ph_)
        q = s/(a*kmag)
        dx += q*a*(kx/kmag)*c; dy += q*a*(ky/kmag)*c; h += a*si
        nx -= kx*a*c; ny -= ky*a*c
    return (x+dx, y+dy, h, nx, ny, 1.0)


# ---------------------------------------------------------------- geometry
def _cyl(r, y0, y1, seg=20, rings=1):
    for s in range(seg):
        a0 = 2*math.pi*s/seg; a1 = 2*math.pi*(s+1)/seg
        glBegin(GL_QUADS)
        for (a, b) in ((a0, a1),):
            glNormal3f(math.cos(a0), 0, math.sin(a0)); glVertex3f(r*math.cos(a0), y0, r*math.sin(a0))
            glNormal3f(math.cos(a1), 0, math.sin(a1)); glVertex3f(r*math.cos(a1), y0, r*math.sin(a1))
            glNormal3f(math.cos(a1), 0, math.sin(a1)); glVertex3f(r*math.cos(a1), y1, r*math.sin(a1))
            glNormal3f(math.cos(a0), 0, math.sin(a0)); glVertex3f(r*math.cos(a0), y1, r*math.sin(a0))
        glEnd()


def _cone(r, y0, y1, seg=20):
    glBegin(GL_TRIANGLES)
    for s in range(seg):
        a0 = 2*math.pi*s/seg; a1 = 2*math.pi*(s+1)/seg
        glNormal3f(math.cos(a0), 0.4, math.sin(a0)); glVertex3f(r*math.cos(a0), y0, r*math.sin(a0))
        glNormal3f(math.cos(a1), 0.4, math.sin(a1)); glVertex3f(r*math.cos(a1), y0, r*math.sin(a1))
        glNormal3f(0, 1, 0); glVertex3f(0, y1, 0)
    glEnd()


def _box(x, y, z, cx=0, cy=0, cz=0):
    X, Y, Z = x/2, y/2, z/2
    f = [([0,0,1],[(-X,-Y,Z),(X,-Y,Z),(X,Y,Z),(-X,Y,Z)]), ([0,0,-1],[(-X,-Y,-Z),(-X,Y,-Z),(X,Y,-Z),(X,-Y,-Z)]),
         ([0,1,0],[(-X,Y,-Z),(-X,Y,Z),(X,Y,Z),(X,Y,-Z)]), ([0,-1,0],[(-X,-Y,-Z),(X,-Y,-Z),(X,-Y,Z),(-X,-Y,Z)]),
         ([1,0,0],[(X,-Y,-Z),(X,Y,-Z),(X,Y,Z),(X,-Y,Z)]), ([-1,0,0],[(-X,-Y,-Z),(-X,-Y,Z),(-X,Y,Z),(-X,Y,-Z)])]
    glBegin(GL_QUADS)
    for n, vs in f:
        glNormal3fv(n)
        for v in vs:
            glVertex3f(v[0]+cx, v[1]+cy, v[2]+cz)
    glEnd()


class Ocean3D:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.grid = 60; self.span = 220.0

    def resize(self, w, h):
        self.w, self.h = w, h

    def setup_gl(self):
        glEnable(GL_DEPTH_TEST); glEnable(GL_NORMALIZE); glShadeModel(GL_SMOOTH)
        glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_LIGHTING); glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL); glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glLightfv(GL_LIGHT0, GL_POSITION, [0.35, 0.9, 0.5, 0.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE,  [1.0, 0.97, 0.88, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 0.95, 1.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT,  [0.24, 0.28, 0.32, 1.0])
        glEnable(GL_FOG); glFogi(GL_FOG_MODE, GL_LINEAR)

    def _project(self, fov):
        glMatrixMode(GL_PROJECTION); glLoadIdentity()
        gluPerspective(fov, self.w/float(self.h), 0.3, 2400.0)
        glMatrixMode(GL_MODELVIEW)

    def _sky(self, top, bot):
        glDisable(GL_DEPTH_TEST); glDisable(GL_LIGHTING); glDisable(GL_FOG)
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, 1, 0, 1, -1, 1)
        glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
        glBegin(GL_QUADS)
        glColor3fv(bot); glVertex2f(0, 0); glVertex2f(1, 0); glColor3fv(top); glVertex2f(1, 1); glVertex2f(0, 1)
        glEnd()
        glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW); glPopMatrix()
        glEnable(GL_DEPTH_TEST); glEnable(GL_LIGHTING); glEnable(GL_FOG)

    def render(self, t, comps, hdg, speed, site_color, underwater, cam, kind, depth=0.0, fov=58.0):
        eye, ctr, up = cam
        if underwater:
            fog_c = (site_color[0]*0.55, site_color[1]*0.7, site_color[2]*0.85)
            glClearColor(*fog_c, 1.0); glFogf(GL_FOG_START, 3.0); glFogf(GL_FOG_END, 70.0)
        else:
            fog_c = (0.66, 0.76, 0.83); sky_top, sky_bot = (0.20, 0.42, 0.66), (0.74, 0.84, 0.90)
            glClearColor(*sky_bot, 1.0); glFogf(GL_FOG_START, 90.0); glFogf(GL_FOG_END, 700.0)
        glFogfv(GL_FOG_COLOR, [*fog_c, 1.0])
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self._project(fov); glLoadIdentity()
        if not underwater:
            self._sky(sky_top, sky_bot)
        gluLookAt(*eye, *ctr, *up)

        if underwater:
            self._ocean(t, comps, site_color, True, surf_z=max(5.0, depth*0.0+6.0))
            self._seabed(t, site_color)
            self._shafts(t); self._particles(t)
        else:
            self._ocean(t, comps, site_color, False)
        # vehicle rides the wave at origin (surface) / sits level (underwater)
        glPushMatrix()
        if not underwater:
            _, _, cz, nx, ny, _ = wave_point(0, 0, t, comps)
            glTranslatef(0, 0, cz)
            glRotatef(math.degrees(math.atan2(ny, 8.0)), 1, 0, 0)
            glRotatef(math.degrees(math.atan2(-nx, 8.0)), 0, 1, 0)
        glRotatef(hdg, 0, 0, -1)
        self._vehicle(kind, underwater)
        glPopMatrix()

    def _ocean(self, t, comps, site_color, underwater, surf_z=0.0):
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [1.0, 1.0, 0.98, 1.0])
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 80.0 if not underwater else 18.0)
        g = self.grid; span = self.span; step = span/g; base = -span/2
        pts = [[wave_point(base+i*step, base+j*step, t, comps) for j in range(g+1)] for i in range(g+1)]
        deep = site_color
        shal = (min(1.0, deep[0]+0.12), min(1.0, deep[1]+0.33), min(1.0, deep[2]+0.34))
        for i in range(g):
            glBegin(GL_TRIANGLE_STRIP)
            for j in range(g+1):
                for ii in (i, i+1):
                    px, py, pz, nx, ny, nz = pts[ii][j]
                    k = max(0.0, min(1.0, (pz+1.1)/2.3))
                    col = [deep[c]+(shal[c]-deep[c])*k for c in range(3)]
                    if pz > 0.75 and not underwater:
                        fo = min(0.85, (pz-0.75)*1.1); col = [col[c]+(0.95-col[c])*fo for c in range(3)]
                    nl = (nx*nx+ny*ny+nz*nz)**0.5 or 1.0
                    glNormal3f(nx/nl, ny/nl, nz/nl)
                    glColor4f(col[0], col[1], col[2], 0.5 if underwater else 1.0)
                    glVertex3f(px, py, pz+surf_z)
            glEnd()

    def _seabed(self, t, site_color):
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 4.0)
        g = 34; span = 150.0; step = span/g; base = -span/2; d0 = -16.0
        def bed(x, y):
            return d0 + 1.6*math.sin(x*0.07) + 1.3*math.cos(y*0.06+1.0) + 0.7*math.sin((x+y)*0.11)
        sand = (0.34, 0.31, 0.22)
        for i in range(g):
            glBegin(GL_TRIANGLE_STRIP)
            for j in range(g+1):
                for ii in (i, i+1):
                    x = base+ii*step; y = base+j*step; z = bed(x, y)
                    zx = bed(x+0.5, y)-z; zy = bed(x, y+0.5)-z
                    shade = 0.8 + 0.2*max(0.0, -zx-zy)
                    glNormal3f(-zx, -zy, 1.0)
                    glColor3f(sand[0]*shade, sand[1]*shade, sand[2]*shade)
                    glVertex3f(x, y, z)
            glEnd()

    def _shafts(self, t):
        glDisable(GL_LIGHTING); glDepthMask(GL_FALSE)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        for i in range(6):
            x = -24 + i*9 + 2*math.sin(t*0.2+i); y = 8 + i*6
            glBegin(GL_QUADS)
            glColor4f(0.5, 0.7, 0.75, 0.0); glVertex3f(x-2, y, -14); glVertex3f(x+2, y, -14)
            glColor4f(0.6, 0.8, 0.85, 0.10); glVertex3f(x+5, y, 6); glVertex3f(x-5, y, 6)
            glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_TRUE); glEnable(GL_LIGHTING)

    def _particles(self, t):
        glDisable(GL_LIGHTING); glDisable(GL_FOG); glPointSize(2.0)
        glColor4f(0.78, 0.84, 0.82, 0.5); glBegin(GL_POINTS)
        for i in range(300):
            px = ((i*53) % 70)-35; pz = ((i*17) % 90)/10.0 - 7.0 + 0.5*math.sin(t*0.5+i)
            py = (((i*31) % 55) + t*0.4) % 60 - 8
            glVertex3f(px, py, pz)
        glEnd(); glEnable(GL_LIGHTING); glEnable(GL_FOG)

    # ---- vehicles ----
    def _vehicle(self, kind, under):
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.3, 0.3, 0.3, 1]); glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 25)
        if under:
            self._torpedo(kind)
        else:
            self._boat(kind)

    def _boat(self, kind):
        long = kind == "interceptor_usv"
        L = 7.0 if long else 5.0; Wd = 1.7 if long else 2.2; D = 1.1
        # hull: pointed bow, tapered stern, sloped sides down to a keel
        hull = (0.86, 0.88, 0.91)
        secs = [(-L/2, Wd*0.7, 0.0), (-L*0.2, Wd, 0.2), (L*0.15, Wd, 0.3), (L*0.38, Wd*0.7, 0.3), (L*0.5, 0.0, 0.35)]
        glColor3f(*hull)
        for a, b in zip(secs, secs[1:]):
            y0, w0, dk0 = a; y1, w1, dk1 = b
            glBegin(GL_QUADS)
            for side in (1, -1):
                # topside
                glNormal3f(side*0.5, 0, 0.3)
                glVertex3f(side*w0/2, y0, dk0); glVertex3f(side*w1/2, y1, dk1)
                glVertex3f(side*w1*0.25, y1, dk1-D); glVertex3f(side*w0*0.25, y0, dk0-D)
            glEnd()
        # keel bottom
        glColor3f(0.2, 0.24, 0.3)
        glBegin(GL_TRIANGLE_STRIP)
        for y, w, dk in secs:
            glNormal3f(0, 0, -1); glVertex3f(w*0.25/1, y, dk-D); glVertex3f(-w*0.25, y, dk-D)
        glEnd()
        # deck
        glColor3f(0.72, 0.75, 0.78)
        glBegin(GL_POLYGON)
        glNormal3f(0, 0, 1)
        for y, w, dk in secs:
            glVertex3f(w/2, y, dk)
        for y, w, dk in reversed(secs):
            glVertex3f(-w/2, y, dk)
        glEnd()
        # waterline stripe
        glColor3f(0.15, 0.3, 0.45); glLineWidth(2)
        glBegin(GL_LINE_STRIP)
        for y, w, dk in secs:
            glVertex3f(w/2+0.02, y, 0.02)
        glEnd(); glLineWidth(1)
        # superstructure / cabin
        glColor3f(0.80, 0.82, 0.85); _box(Wd*0.7, L*0.3, 0.7, 0, -L*0.02, 0.65)
        if long:
            glColor3f(0.3, 0.45, 0.6); _box(Wd*0.5, 0.1, 0.5, 0, L*0.12, 0.8)   # windshield
        # mast
        glColor3f(0.5, 0.52, 0.55); _box(0.12, 0.12, 1.4, 0, -L*0.05, 1.7)

    def _torpedo(self, kind):
        big = kind == "auv150"
        r = 0.42 if big else 0.28; L = 2.6 if big else 2.0
        body = (0.93, 0.66, 0.16)
        glColor3f(*body)
        glPushMatrix()
        _cyl(r, -L*0.42, L*0.42, seg=22)       # main body (along Y)
        glColor3f(0.2, 0.22, 0.25); _cone(r, L*0.42, L*0.42+r*2.0, seg=22)   # nose
        glColor3f(*body)
        glBegin(GL_TRIANGLE_FAN); glNormal3f(0, -1, 0); glVertex3f(0, -L*0.42, 0)   # tail cap
        for s in range(23):
            a = 2*math.pi*s/22; glVertex3f(r*math.cos(a), -L*0.42, r*math.sin(a))
        glEnd()
        # tail fins (X) + propeller
        glColor3f(0.75, 0.52, 0.12)
        for k in range(4):
            glPushMatrix(); glRotatef(45+90*k, 0, 1, 0)
            _box(0.05, L*0.2, r*2.1, 0, -L*0.33, 0)
            glPopMatrix()
        glColor3f(0.3, 0.3, 0.33); _cyl(r*0.35, -L*0.5, -L*0.42, seg=12)   # prop hub
        if big:    # AUV-150: external thruster nacelles (it has 5 thrusters)
            glColor3f(0.78, 0.55, 0.14)
            for k in range(4):
                glPushMatrix(); glRotatef(90*k, 0, 1, 0); glTranslatef(r*1.2, L*0.1, 0)
                _cyl(0.1, -0.3, 0.3, seg=10); glPopMatrix()
        glPopMatrix()


# ---------------- standalone screenshot ----------------
def _shot(path, under=False, hs=1.2, tp=7.0, brg=160, col=(0.03, 0.20, 0.28), kind="interceptor_usv", third=False, t=3.0):
    import pygame
    from pygame.locals import OPENGL, DOUBLEBUF
    pygame.init(); W, H = 960, 600
    pygame.display.set_mode((W, H), OPENGL | DOUBLEBUF)
    oc = Ocean3D(W, H); oc.setup_gl()
    comps = gerstner_components(hs, tp, brg); hd = 30.0; fwd = (math.sin(math.radians(hd)), math.cos(math.radians(hd)))
    if under:
        cam = ((-fwd[0]*6.5, -fwd[1]*6.5, 2.2), (fwd[0]*9, fwd[1]*9, -1.5), (0, 0, 1))
    elif third:
        cam = ((-fwd[0]*24, -fwd[1]*24, 16), (fwd[0]*6, fwd[1]*6, -1), (0, 0, 1))
    else:
        cam = ((-fwd[0]*8, -fwd[1]*8, 3.0), (fwd[0]*14, fwd[1]*14, 0), (0, 0, 1))
    for _ in range(3):
        oc.render(t, comps, hd, 1.0, col, under, cam, kind, depth=10.0); pygame.display.flip()
    glPixelStorei(GL_PACK_ALIGNMENT, 1)
    d = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    s = pygame.transform.flip(pygame.image.fromstring(d, (W, H), "RGB"), False, True)
    pygame.image.save(s, path); pygame.quit(); print("saved", path)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/o.png"
    k = {"i": "interceptor_usv", "s": "survey_usv", "m": "maya_auv", "a": "auv150"}.get(
        next((a[2] for a in sys.argv if a.startswith("--k")), "i"), "interceptor_usv")
    _shot(out, under=("--under" in sys.argv), third=("--third" in sys.argv), kind=k,
          col=((0.03, 0.20, 0.28)))
