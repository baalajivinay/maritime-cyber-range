#!/usr/bin/env python3
"""
Unified physics backend for the Godot front-end -- "all the physics in one app".

The operator picks any vehicle in the Godot console and this router runs the
BEST physics engine for it automatically, feeding the one Godot renderer:

  * underwater AUVs that have a tuned Stonefish scenario  -> Stonefish
    (high-fidelity 6-DOF hydrodynamics; runs HEADLESS so Godot is the only
    window). This is the ArduSub+Stonefish stack from tools/stonefish_bridge.sh.
  * everything else (surface USVs, AUVs without a .scn)   -> the Gazebo backend
    (nodes/app/mcr_app.Backend), which carries the real-data models: site
    sea-state, acoustics, DVL/GNSS/IMU error, tides, bathymetry.

It exposes the exact attribute/method surface tools/godot_relay.py reads from a
Backend, delegating to whichever engine is active, and switches engines when the
operator switches to a vehicle that belongs to the other one.
"""
import os
import subprocess
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "nodes", "app"))
import mcr_app as M                       # Gazebo backend
from stonefish_source import StonefishSource

# Twins that have a tuned Stonefish scenario (stonefish/<twin>.scn) + bridge.
STONEFISH_TWINS = {"auv150"}


class UnifiedBackend:
    def __init__(self):
        self._lock = threading.Lock()
        self._default_state = dict(lat=None, lon=None, hdg=0.0, depth=0.0,
                                   speed=0.0, armed=False, mode="--", hb=0)
        self._events = []
        self.engine = None            # the active Backend / StonefishSource
        self.engine_kind = None       # "gazebo" | "stonefish"
        self._bridge_started = False

    # ---- read surface the relay uses (delegate to the active engine) --------
    @property
    def lock(self):
        return self.engine.lock if self.engine else self._lock

    @property
    def state(self):
        return self.engine.state if self.engine else self._default_state

    @property
    def events(self):
        return self.engine.events if self.engine else self._events

    @property
    def connected(self):
        return self.engine.connected if self.engine else False

    @property
    def booting(self):
        return self.engine.booting if self.engine else False

    @property
    def domain(self):
        return self.engine.domain if self.engine else "surface"

    @property
    def twin(self):
        return self.engine.twin if self.engine else None

    @property
    def home(self):
        return self.engine.home if self.engine else (9.9, 76.2)

    @property
    def active_attack(self):
        return self.engine.active_attack if self.engine else None

    def _log(self, m):
        self._events.append((time.strftime("%H:%M:%S"), m))
        self._events[:] = self._events[-40:]

    # ---- Stonefish bridge lifecycle ----------------------------------------
    def _mcr_running(self):
        return subprocess.call(["pgrep", "-x", "MCR"],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL) == 0

    def _ensure_stonefish_bridge(self, site):
        if self._mcr_running():
            return True
        env = dict(os.environ, MCR_HEADLESS="1")
        lat_lon = {"kochi": ("9.9", "76.2"), "mumbai": ("18.95", "72.8"),
                   "visakhapatnam": ("17.7", "83.3")}.get(site, ("9.9", "76.2"))
        env["MCR_LAT"], env["MCR_LON"] = lat_lon
        self._log("starting Stonefish physics (headless) ...")
        r = subprocess.run(["bash", os.path.join(REPO, "tools", "stonefish_bridge.sh"), "up"],
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._bridge_started = (r.returncode == 0)
        time.sleep(2)
        return self._bridge_started

    def _stop_stonefish_bridge(self):
        if self._bridge_started:
            subprocess.run(["bash", os.path.join(REPO, "tools", "stonefish_bridge.sh"), "down"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._bridge_started = False

    # ---- lifecycle ----------------------------------------------------------
    def boot(self, site, twin, domain):
        kind = "stonefish" if twin in STONEFISH_TWINS else "gazebo"
        # switching engines -> tear the old one (and its bridge) down first
        if self.engine is not None and self.engine_kind != kind:
            try:
                self.engine.teardown()
            except Exception:
                pass
            if self.engine_kind == "stonefish":
                self._stop_stonefish_bridge()
            self.engine = None

        if kind == "stonefish":
            if not self._ensure_stonefish_bridge(site):
                self._log("Stonefish bridge failed -- falling back to Gazebo")
                return self._boot_gazebo(site, twin, domain)
            if self.engine is None:
                self.engine = StonefishSource()
            self.engine_kind = "stonefish"
            self.engine.boot(site, twin, domain)
        else:
            self._boot_gazebo(site, twin, domain)

    def _boot_gazebo(self, site, twin, domain):
        # a fresh Gazebo Backend per boot (its own teardown is per-twin)
        if self.engine is not None and self.engine_kind == "gazebo":
            try:
                self.engine.teardown()
            except Exception:
                pass
        self.engine = M.Backend()
        self.engine_kind = "gazebo"
        self.engine.boot(site, twin, domain)

    # ---- control (delegate) -------------------------------------------------
    def goto(self, lat, lon):
        if self.engine:
            self.engine.goto(lat, lon)

    def arm(self):
        if self.engine:
            self.engine.arm()

    def disarm(self):
        if self.engine:
            self.engine.disarm()

    def attack(self, name):
        if self.engine:
            self.engine.attack(name)

    def stop_attack(self):
        if self.engine:
            self.engine.stop_attack()

    def teardown(self):
        if self.engine:
            try:
                self.engine.teardown()
            except Exception:
                pass
        self._stop_stonefish_bridge()
        self.engine = None
