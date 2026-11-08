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
import socket
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

# Ports the Gazebo-routed underwater twins (ArduSub SITL via run_sim.sh) and
# the Stonefish bridge's ArduSub BOTH bind by default (ArduPilot SITL always
# uses 5760/5762/5763 for its GCS/SERIAL links regardless of vehicle, and this
# project's own FDM relay for Gazebo underwater twins defaults to UDP 9002 --
# see vehicle_twins/maya_auv/profile.json "fdm_relay_bind"). Switching from one
# engine to the other without waiting for these to actually free lets the new
# stack silently fail to bind them (the old process is still shutting down),
# which previously showed up as "boot: connected + position fix" timing out
# with no error anywhere (mav_bridge/ArduSub looked alive; they just couldn't
# reach each other on the ports they expected).
_SHARED_TCP_PORTS = (5760, 5762, 5763)
_SHARED_UDP_PORTS = (9002,)


def _port_free(port, kind):
    fam = socket.SOCK_STREAM if kind == "tcp" else socket.SOCK_DGRAM
    s = socket.socket(socket.AF_INET, fam)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _wait_ports_free(timeout=20.0, log=None):
    """Poll until the ports the NEXT engine needs are actually free (or give
    up after `timeout` and proceed anyway -- best effort, logged)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        busy = [p for p in _SHARED_TCP_PORTS if not _port_free(p, "tcp")]
        busy += [p for p in _SHARED_UDP_PORTS if not _port_free(p, "udp")]
        if not busy:
            return True
        time.sleep(0.5)
    if log:
        log(f"WARNING: ports still busy after {timeout:.0f}s ({busy}) -- "
            f"booting anyway, the new stack may fail to bind them")
    return False


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
    def _teardown_current(self):
        """Tear down whatever engine/twin is currently running and BLOCK until
        the ports (and processes) the next stack needs are actually free.

        Both engines' own teardown is fire-and-forget: Backend.teardown()
        (Gazebo) launches `run_vehicle.sh down` via subprocess.Popen and
        returns immediately, without waiting for the `gz sim` WORLD SERVER
        process (not just the SITL binary) to actually exit -- and two
        different Gazebo twins can share the identical world SDF/world_name
        (e.g. interceptor_usv and survey_usv both use cusv_world.sdf /
        "surface_harbor"), so a still-dying old world can block the new one
        from starting at all. Observed live: interceptor_usv -> survey_usv
        consistently failed to boot (150s timeout, empty gz world.log) right
        after interceptor_usv tore down, even though its own ArduSub ports
        were confirmed free -- the stale `gz sim` process was the blocker,
        not the ports tools/run_sim.sh's own SITL serial links use.
        tools/teardown_all.sh is this project's already-proven comprehensive
        reaper (kills gz sim, ardusub/ardurover, mav_bridge.py and the rest,
        explicitly including the world-server process); run it SYNCHRONOUSLY
        here instead of relying on the async per-engine teardown alone."""
        if self.engine is None:
            return
        try:
            self.engine.teardown()
        except Exception:
            pass
        subprocess.run(["bash", os.path.join(REPO, "tools", "teardown_all.sh")],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if self.engine_kind == "stonefish":
            self._stop_stonefish_bridge()
        self.engine = None
        _wait_ports_free(timeout=20.0, log=self._log)
        # gz-transport's pub/sub discovery (what `gz topic -l` reads to decide
        # a Gazebo world has booted) takes a beat to flush a SIGKILLed world's
        # stale registration -- raw ports being free (checked above) doesn't
        # guarantee discovery has caught up yet. A short settle here is much
        # cheaper than occasionally eating tools/run_sim.sh's full model-wait
        # timeout on the next boot (see its wait_gz_model call).
        time.sleep(3.0)

    def boot(self, site, twin, domain):
        kind = "stonefish" if twin in STONEFISH_TWINS else "gazebo"
        if self.engine is not None:
            self._teardown_current()

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
        # _teardown_current() (called from boot() above) already tore down and
        # port-waited for any previous engine; this only still fires for the
        # Stonefish-bridge-failed fallback path, where nothing is up yet.
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
