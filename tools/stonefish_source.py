#!/usr/bin/env python3
"""
Stonefish telemetry source for the Godot front-end.

This is the "both softwares combined" path: Stonefish owns the high-fidelity
physics (it is the JSON FDM backing ArduSub; see tools/stonefish_bridge.sh), and
Godot renders that same vehicle state with game-quality visuals. This adapter
exposes the exact attribute/method surface that tools/godot_relay.py reads from
nodes/app/mcr_app.Backend, but instead of booting a Gazebo world it attaches to
the already-running Stonefish-bridged ArduSub over MAVLink and drives the
acoustic (USBL/ExternalNav) spoof through the extnav injector.

Pre-req: `tools/stonefish_bridge.sh up` is already running.
"""
import math
import os
import socket
import threading
import time

from pymavlink import mavutil

# ArduSub in the Stonefish stack: SERIAL2 TCP (free; 5760=mav_bridge, 5762=extnav)
MAVLINK = os.environ.get("MCR_STONEFISH_MAVLINK", "tcp:127.0.0.1:5763")
EXTNAV_CTRL = ("127.0.0.1", 10120)   # stonefish_extnav.py spoof toggle
POSE_PORT = 9005                     # MCR true-pose broadcast (shared w/ extnav)


class StonefishSource:
    def __init__(self):
        self.site = "kochi"
        self.twin = "auv150"
        self.domain = "underwater"          # the Stonefish twin is a submerged AUV
        self.home = (9.9, 76.2)
        self.lock = threading.Lock()
        self.state = dict(lat=None, lon=None, hdg=0.0, roll=0.0, pitch=0.0, depth=0.0,
                          speed=0.0, mode="--", armed=False, hb=0, sim_backend="stonefish")
        self.track = []
        self.events = []
        self.booting = False
        self.connected = False
        self.active_attack = None
        self.conn = None
        self._stop = False
        self._goto_target = None
        self._override_stop = threading.Event()
        self._spoof = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # ---- helpers -------------------------------------------------------
    def log(self, m):
        self.events.append((time.strftime("%H:%M:%S"), m))
        self.events[:] = self.events[-40:]

    def _spoof_cmd(self, cmd):
        try:
            self._spoof.sendto(cmd.encode(), EXTNAV_CTRL)
        except OSError:
            pass

    # ---- lifecycle -----------------------------------------------------
    def boot(self, site, twin, domain):
        """Attach to the running Stonefish stack (does NOT boot Gazebo)."""
        self.site = site or "kochi"
        self.twin = twin or "auv150"
        self.domain = "underwater"
        self.booting = True
        self.log(f"attaching to Stonefish stack ({MAVLINK}) ...")
        self.conn = mavutil.mavlink_connection(MAVLINK, source_system=255)
        if self.conn.wait_heartbeat(timeout=20) is None:
            self.booting = False
            self.log("no ArduSub heartbeat -- is tools/stonefish_bridge.sh up?")
            return False
        self.conn.mav.request_data_stream_send(
            self.conn.target_system, self.conn.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
        self.booting = False
        self.connected = True
        self.log("connected -- Godot now rendering Stonefish physics")
        threading.Thread(target=self._rx_loop, daemon=True).start()
        return True

    def _rx_loop(self):
        mm = self.conn.mode_mapping() or {}
        inv = {v: k for k, v in mm.items()}
        while not self._stop and self.conn:
            try:
                msg = self.conn.recv_match(
                    type=["GLOBAL_POSITION_INT", "VFR_HUD", "ATTITUDE", "HEARTBEAT"],
                    blocking=True, timeout=1.0)
            except OSError:
                # teardown() closed the socket while recv() was blocked on it
                # (a normal shutdown race, not a real fault) -- exit quietly.
                break
            if msg is None:
                continue
            t = msg.get_type()
            with self.lock:
                if t == "GLOBAL_POSITION_INT" and not (msg.lat == 0 and msg.lon == 0):
                    self.state["lat"] = msg.lat / 1e7
                    self.state["lon"] = msg.lon / 1e7
                    if msg.hdg != 65535:
                        self.state["hdg"] = msg.hdg / 100.0
                    self.state["depth"] = max(0.0, -msg.relative_alt / 1000.0)
                    self.track.append((self.state["lat"], self.state["lon"]))
                    self.track[:] = self.track[-500:]
                elif t == "VFR_HUD":
                    self.state["speed"] = msg.groundspeed
                    self.state["depth"] = max(0.0, -msg.alt)
                elif t == "ATTITUDE":
                    self.state["roll"] = math.degrees(msg.roll)
                    self.state["pitch"] = math.degrees(msg.pitch)
                elif t == "HEARTBEAT":
                    self.state["armed"] = bool(
                        msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    self.state["mode"] = inv.get(msg.custom_mode, str(msg.custom_mode))
                    self.state["hb"] += 1

    # ---- control -------------------------------------------------------
    def _set_mode(self, name):
        if self.conn is None:
            # teardown() nulled the connection while a background thread
            # (goto's _drive loop, an attack) was still mid-call -- a normal
            # shutdown race, not a real fault.
            return
        mm = self.conn.mode_mapping() or {}
        if name in mm:
            self.conn.mav.set_mode_send(
                self.conn.target_system,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mm[name])

    def arm(self):
        if not self.conn:
            return
        self._set_mode("ALT_HOLD")
        time.sleep(0.3)
        self.conn.mav.command_long_send(
            self.conn.target_system, self.conn.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
        self.log("arm (ALT_HOLD)")

    def disarm(self):
        if not self.conn:
            return
        self.conn.mav.command_long_send(
            self.conn.target_system, self.conn.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 0, 0, 0, 0, 0, 0)
        self.log("disarm")

    def goto(self, lat, lon):
        """GUIDED waypoint. ArduSub holds depth; horizontal nav to the target.
        Runs in a thread, re-sending the target (GUIDED needs it sustained) and
        re-arming if the hull idle-disarms, until it arrives or is superseded."""
        if not self.conn:
            return
        self.log("destination set -- %.5f, %.5f" % (lat, lon))
        self._goto_target = (lat, lon)
        threading.Thread(target=self._drive, args=(lat, lon), daemon=True).start()

    def _drive(self, lat, lon):
        import math
        c = self.conn
        hold_depth = max(2.0, self.state.get("depth", 0.0))  # keep it submerged
        self._set_mode("GUIDED")
        end = time.time() + 900
        while not self._stop and c and self._goto_target == (lat, lon) and time.time() < end:
            # Yield to active attacks -- do not fight or override attacker commands
            if self.active_attack:
                time.sleep(0.5)
                continue
            try:
                if not self.state.get("armed"):
                    c.mav.command_long_send(c.target_system, c.target_component,
                                            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                                            0, 1, 0, 0, 0, 0, 0, 0)
                    self._set_mode("GUIDED")
                c.mav.set_position_target_global_int_send(
                    0, c.target_system, c.target_component,
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                    0b0000111111111000, int(lat * 1e7), int(lon * 1e7), int(-hold_depth),
                    0, 0, 0, 0, 0, 0, 0, 0)
                c.mav.command_int_send(
                    c.target_system, c.target_component,
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                    mavutil.mavlink.MAV_CMD_DO_REPOSITION,
                    0, 0, -1, 1, 0, 0,
                    int(lat * 1e7), int(lon * 1e7), float(-hold_depth))
            except (OSError, AttributeError):
                # teardown() closed/nulled the connection mid-call (a normal
                # shutdown race, not a real fault) -- exit quietly.
                break
            clat, clon = self.state.get("lat"), self.state.get("lon")
            if clat:
                if 111320.0 * math.hypot(clat - lat, (clon - lon) * math.cos(math.radians(lat))) < 3.0:
                    self.log("arrived at destination")
                    break
            time.sleep(1.0)

    def attack(self, name):
        """Attack surface of the submerged Stonefish AUV. Accepts both the
        Godot HUD labels ("Acoustic spoof", "C2 mode", "C2 override") and the
        snake_case ids."""
        self.active_attack = name
        n = name.lower().replace(" ", "_")
        c = self.conn
        if n in ("acoustic_spoof", "usbl_spoof", "acoustic", "gps_spoof"):
            # Submerged: inject USBL acoustic position spoof (50m step walk-off)
            self._spoof_cmd("step")
            self.log("ATTACK: acoustic/USBL ExternalNav spoof (50m step walk-off) ON")
        elif n == "c2_mode" and c:
            mm = c.mode_mapping() or {}
            tgt = next((m for m in ("MANUAL", "HOLD", "ALT_HOLD") if m in mm), None)
            if tgt:
                c.mav.set_mode_send(c.target_system,
                                    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mm[tgt])
                self.log(f"ATTACK: forged SET_MODE -> {tgt} (autopilot guidance halted)")
        elif n == "c2_override" and c:
            # Force MANUAL first so ArduSub's guidance yields to raw channel override
            mm = c.mode_mapping() or {}
            if "MANUAL" in mm:
                c.mav.set_mode_send(c.target_system,
                                    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mm["MANUAL"])
                time.sleep(0.3)
            self._override_stop.clear()
            self.log("ATTACK: RC_CHANNELS_OVERRIDE -- hard right rudder & full forward surge seized")
            while not self._override_stop.is_set():
                # Channel 3: Heave (1500=neutral), Channel 4: Yaw (1850=hard right), Channel 5: Surge (1850=full surge)
                c.mav.rc_channels_override_send(c.target_system, c.target_component,
                                                1500, 1500, 1500, 1850, 1850, 1500, 0, 0)
                time.sleep(0.1)
        else:
            self.log(f"ATTACK: {name} not applicable to a submerged AUV")

    def stop_attack(self):
        name = self.active_attack
        n = (name or "").lower().replace(" ", "_")
        c = self.conn
        if n in ("acoustic_spoof", "usbl_spoof", "acoustic", "gps_spoof"):
            self._spoof_cmd("off")
        elif n == "c2_override" and c:
            self._override_stop.set()
            c.mav.rc_channels_override_send(c.target_system, c.target_component,
                                            0, 0, 0, 0, 0, 0, 0, 0)
            mm = c.mode_mapping() or {}
            if "GUIDED" in mm:
                c.mav.set_mode_send(c.target_system,
                                    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mm["GUIDED"])
        elif n == "c2_mode" and c:
            mm = c.mode_mapping() or {}
            if "GUIDED" in mm:
                c.mav.set_mode_send(c.target_system,
                                    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mm["GUIDED"])
        if name:
            self.log(f"STOP: {name} (resuming guided navigation)")
        self.active_attack = None

    def teardown(self):
        self._stop = True
        self._override_stop.set()
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        self.conn = None
        self.connected = False
