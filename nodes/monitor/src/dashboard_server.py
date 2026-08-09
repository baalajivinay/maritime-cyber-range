"""
Maritime Cyber Range -- interactive operator console (dashboard + control).

Passive viz (true vs believed position, AIS, blind detector alerts, telemetry)
PLUS operator controls driven from the browser:
  - set a DESTINATION (click the map) -> the vehicle navigates there (GUIDED),
  - LAUNCH an attack (GPS spoof / AIS spoof / C2 inject / acoustic spoof),
  - STOP attacks,
  - GENERATE a REPORT on command (scores the blind detectors vs ground truth).

Feeds: true position from the CLEAN Gazebo ground-truth pose (not the noisy GPS
sensor -- that was the "jittery marker"); believed from MAVLink; AIS from UDP;
detectors from a spare MAVLink port. Commands go out on another spare port.
No ROS dependency (portable / containerizable).
"""
import os
import sys
import json
import time
import hmac
import html as html_lib
import socket
import statistics
import resource
import tempfile
import threading
import subprocess
from collections import deque
from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO, emit
from pymavlink import mavutil
from pyais.stream import UDPReceiver

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "detection"))
sys.path.insert(0, os.path.join(_REPO, "attacks"))
sys.path.insert(0, os.path.join(_REPO, "tools"))
import constants
from detectors import DetectorSuite
from score_detectors import score as score_alerts
from generate_report import render_family_table, render_overhead_panel

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- optional control-endpoint auth (OFF unless MCR_DASHBOARD_TOKEN is set) ----
# The /cmd/* endpoints change state: launch attacks, move the vehicle, reboot the
# whole sim. With no token they are OPEN -- fine on localhost, but a real loophole
# once the dashboard is reachable on a LAN or a public tunnel (anyone with the URL
# could drive it). Set MCR_DASHBOARD_TOKEN to require a shared secret on every
# control call; read-only views ('/', '/whoami', live telemetry) stay open. The
# browser forwards it from the page URL's ?token=... as an X-MCR-Token header.
CONTROL_TOKEN = os.environ.get("MCR_DASHBOARD_TOKEN", "").strip()


@app.before_request
def _gate_control_endpoints():
    if not CONTROL_TOKEN:
        return                                   # auth disabled -> open (default)
    if not request.path.startswith("/cmd/"):
        return                                   # only guard state-changing calls
    supplied = request.headers.get("X-MCR-Token") or request.args.get("token", "")
    if not hmac.compare_digest(supplied, CONTROL_TOKEN):
        return jsonify(ok=False, msg="unauthorized: a valid control token is required"), 401

PROFILE = constants.PROFILE_NAME
DOMAIN = constants.DOMAIN
VEHICLE_LABEL = f"{DOMAIN.title()} — {PROFILE} ({constants.ARDUPILOT_VEHICLE_TYPE})"
_last_warning = None   # set by detector_thread if a profile/sim domain mismatch is seen
RUN_DIR = os.environ.get("MCR_RUN_DIR", f"/tmp/mcr_run/{PROFILE}")
RELAY_FIFO = os.path.join(RUN_DIR, "relay.fifo")
SESSION_START = time.time()
ALERT_LOG = os.path.join(_REPO, "evidence", "live_session_alerts.jsonl")
open(ALERT_LOG, "w").close()  # fresh per session

# world name (for the ground-truth pose topic) from the profile
try:
    _w = json.load(open(os.path.join(_REPO, "profiles", PROFILE + ".json"))).get("world", {})
    WORLD_NAME = _w.get("world_name", "sydney_regatta" if DOMAIN == "surface" else "underwater_harbor")
    MODEL_NAME = _w.get("model_name", PROFILE)
except Exception:
    WORLD_NAME, MODEL_NAME = ("sydney_regatta" if DOMAIN == "surface" else "underwater_harbor"), PROFILE

M_PER_DEG_LAT = constants.M_PER_DEG_LAT
M_PER_DEG_LON = constants.m_per_deg_lon(constants.HOME_LAT)

_det_suite = DetectorSuite(DOMAIN, cfg={"known_mmsi": constants.VESSEL_MMSI})
_alert_lock = threading.Lock()

# --- live system-overhead + detection-latency instrumentation ----------------
# Mirrors detection/run_detectors.py's overhead sampling, but for THIS
# in-process live detector loop, so the dashboard can show the same
# CPU/memory/throughput picture in real time instead of only after the fact.
_overhead_lock = threading.Lock()
_event_durations = deque(maxlen=2000)   # perf_counter seconds per suite.update() call, rolling window
_events_processed = 0
_alerts_emitted = 0
_attack_launch_t = {}      # attack_type -> wall time it was last launched from the UI
_latency_reported = set()  # attack_types whose first-alert-since-launch has already been reported


def tap(event):
    """Feed one live event through the detector suite, timing the call for the
    live overhead readout (see /cmd/report and the periodic overhead_update)."""
    global _events_processed
    t0 = time.perf_counter()
    alerts = _det_suite.update(event)
    dt = time.perf_counter() - t0
    with _overhead_lock:
        _event_durations.append(dt)
        _events_processed += 1
    _push_alerts(alerts)
    return alerts


def _pctile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _live_overhead_snapshot():
    """Same shape as detection/run_detectors.py's overhead JSON, computed live
    from this process's own resource usage + the rolling event-duration window."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    cpu_s = usage.ru_utime + usage.ru_stime
    wall_s = time.time() - SESSION_START
    with _overhead_lock:
        proc_us = sorted(d * 1e6 for d in _event_durations)
        n = _events_processed
        emitted = _alerts_emitted
    return {
        "profile": PROFILE, "domain": DOMAIN,
        "wall_s": round(wall_s, 3),
        "cpu_s": round(cpu_s, 3),
        "cpu_pct_of_wall": round(100.0 * cpu_s / wall_s, 3) if wall_s > 0 else None,
        "peak_rss_mb": round(usage.ru_maxrss / 1024.0, 2),
        "events_processed": n,
        "alerts_emitted": emitted,
        "events_per_sec": round(n / wall_s, 2) if wall_s > 0 else None,
        "event_proc_time_us": {
            "mean": round(statistics.mean(proc_us), 2) if proc_us else None,
            "median": round(statistics.median(proc_us), 2) if proc_us else None,
            "p95": round(_pctile(proc_us, 0.95), 2) if proc_us else None,
            "max": round(max(proc_us), 2) if proc_us else None,
        },
    }


def overhead_emitter():
    while True:
        time.sleep(5)
        try:
            socketio.emit('overhead_update', _live_overhead_snapshot())
        except Exception:
            pass


def _push_alerts(alerts):
    global _alerts_emitted
    for a in alerts:
        d = a.as_dict()
        socketio.emit('attack_alert', d)
        with _overhead_lock:
            _alerts_emitted += 1
        launch_t = _attack_launch_t.get(a.attack_type)
        if launch_t is not None and a.attack_type not in _latency_reported:
            _latency_reported.add(a.attack_type)
            socketio.emit('attack_latency', {
                'attack_type': a.attack_type,
                'latency_s': round(max(0.0, a.t - launch_t), 2),
            })
        with _alert_lock:
            with open(ALERT_LOG, "a") as f:
                f.write(json.dumps(d) + "\n")


# --- shared command connection (send arm/mode/goto/override) -----------------
_cmd_conn = None
_cmd_lock = threading.Lock()


def cmd_conn():
    global _cmd_conn
    with _cmd_lock:
        if _cmd_conn is None:
            # source_system is DELIBERATELY the plain ArduPilot default (255),
            # NOT constants.GCS_SOURCE_SYSTEM -- this connection is used only
            # to launch C2 attacks (RC-override/disarm/mode-change), i.e. it
            # simulates an attacker who does not know a hardened vehicle's
            # real trusted GCS id. Confirmed empirically (2026-08-07):
            # source_system=250 made the RC-override attack a silent no-op
            # against a vehicle with NO hardening at all -- that earlier
            # finding was really about ArduPilot's MAV_GCS_SYSID default
            # (255), not the now-deprecated SYSID_MYGCS this comment used to
            # cite. A properly hardened vehicle (MAV_GCS_SYSID set +
            # MAV_OPTIONS=1 / GCS_SYSID_ENFORCE, see vehicle_twins/*_resilient_*/)
            # will correctly reject this connection's commands -- that
            # rejection IS the security property being demonstrated, so do
            # NOT "fix" this to use constants.GCS_SOURCE_SYSTEM.
            c = mavutil.mavlink_connection("tcp:127.0.0.1:5762", source_system=255)
            c.wait_heartbeat(timeout=15)
            _cmd_conn = c
        return _cmd_conn


# --- feed threads ------------------------------------------------------------
_last_true_pos = None  # (lat, lon), kept fresh by gz_pose_thread -- lets
                        # AIS impersonation anchor on where the vehicle
                        # actually is instead of the world's fixed origin


_TRUE_POS_EMIT_INTERVAL_S = 0.1  # cap the browser-facing feed to ~10Hz -- matches
# the believed-position feed's natural MAVLink rate. /pose/info itself
# publishes at Gazebo's physics-step rate (100+Hz, confirmed live
# 2026-08-09: 2239 gps_true_update emits in 20s, vs 178 believed updates in
# the same window) -- emitting every single one to the browser was firing
# the map's trail/connector redraw over 100x/sec, which is what produced the
# "many dots appear randomly while moving" symptom: at that update rate the
# 80-point trail buffer represents under a second of travel, so consecutive
# points sit only millimeters apart on a meters-scale map and render as a
# scattered cluster rather than a line. _last_true_pos itself still updates
# every message (goto()'s frame alignment and the acoustic-spoof feed read
# it and need the freshest value) -- only the socket EMIT is throttled.
_last_true_emit_t = 0.0


def gz_pose_thread():
    """CLEAN true position from Gazebo ground truth (no GPS noise)."""
    global _last_true_pos, _last_true_emit_t
    topic = f"/world/{WORLD_NAME}/pose/info"
    while True:
        try:
            proc = subprocess.Popen(["gz", "topic", "-e", "-t", topic],
                                    stdout=subprocess.PIPE, text=True)
            block, in_model = "", False
            import re
            for line in proc.stdout:
                if f'name: "{MODEL_NAME}"' in line:
                    in_model, block = True, line
                    continue
                if in_model:
                    block += line
                    if line.strip() == "}" and "position" in block and "orientation" in block:
                        # Gazebo's protobuf text format omits any field that
                        # equals its default (0.0) -- a vehicle sitting
                        # exactly on the world-frame y=0 line (true for
                        # CUSV, confirmed live 2026-08-09) has its position
                        # y field silently absent from the text, not a rare
                        # edge case. Default a missing field to 0.0 (its
                        # real protobuf value) instead of requiring both x
                        # and y to literally appear, which previously froze
                        # _last_true_pos/the true-position map for any
                        # vehicle whose x or y ever landed on exactly 0.
                        mx = re.search(r"position\s*\{\s*x:\s*([-+\d.e]+)", block)
                        my = re.search(r"position\s*\{[^}]*y:\s*([-+\d.e]+)", block, re.S)
                        x = float(mx.group(1)) if mx else 0.0
                        y = float(my.group(1)) if my else 0.0
                        lat = constants.HOME_LAT + y / M_PER_DEG_LAT
                        lon = constants.HOME_LON + x / M_PER_DEG_LON
                        _last_true_pos = (lat, lon)
                        now = time.time()
                        if now - _last_true_emit_t >= _TRUE_POS_EMIT_INTERVAL_S:
                            _last_true_emit_t = now
                            socketio.emit('gps_true_update', {'lat': lat, 'lon': lon})
                        in_model = False
        except Exception as e:
            print(f"gz pose thread error: {e}; retry 3s"); time.sleep(3)


def legit_gps_feeder():
    """Continuously feeds the vehicle's own TRUE position as a legitimate
    GPS_INPUT stream. Only matters for a hardened twin's GPS1_TYPE=14
    param (external AP_GPS_MAV driver) -- confirmed live 2026-08-09 that
    without this, a resilient twin has NO ambient GPS source at all
    (GPS_RAW_INT.fix_type stuck at 1/no-fix, 0 satellites), so it can never
    pass ArduPilot's arming checks: goto() would set AUTO + upload a
    mission successfully, but the arm loop silently failed every time --
    "mode shows AUTO, armed stays DISARMED, destination never gets closer"
    is exactly what that looks like on the dashboard. A twin using the
    default embedded/JSON-FDM GPS (GPS1_TYPE != 14) simply has no driver
    listening for GPS_INPUT, so sending it here is a harmless no-op --
    safe to run unconditionally for every surface twin rather than needing
    to know which ones are hardened.
    Uses its own dedicated port (MAVLINK_GPS_FEEDER_PORT), not one of the
    transient per-click connections (goto()'s auto_mission port) -- sharing
    would hit the same SO_REUSEADDR silent-port-stealing issue already
    fixed once for concurrent goto() calls this session."""
    if DOMAIN != "surface":
        return  # underwater vehicles get position via acoustic feed, not GPS
    import gps_input_inject
    while True:
        try:
            c = mavutil.mavlink_connection(f'udpin:127.0.0.1:{constants.MAVLINK_GPS_FEEDER_PORT}',
                                            source_system=constants.GCS_SOURCE_SYSTEM)
            # MUST receive at least one message before sending -- a fresh
            # udpin: listener doesn't know mav_bridge's ephemeral reply
            # address until it has received something from it, so anything
            # sent before this silently goes nowhere (confirmed live
            # 2026-08-09: an identical send loop without this wait produced
            # zero effect at the vehicle despite no errors on either side).
            c.wait_heartbeat(timeout=15)
            while True:
                if _last_true_pos is not None:
                    lat, lon = _last_true_pos
                    gps_input_inject.send_gps_input(c, lat, lon, 0.0)
                time.sleep(0.2)  # 5Hz -- plenty for a stable arming/EKF fix
        except Exception as e:
            print(f"legit GPS feeder error: {e}; retry 3s"); time.sleep(3)


def legit_vision_feeder():
    """Underwater analog of legit_gps_feeder -- both REMUS-100 twins
    (vulnerable AND hardened, confirmed by reading both parm files) set
    EK3_SRC1_POSXY=6 (ExternalNav), meaning they have NO horizontal position
    source at all unless something feeds VISION_POSITION_ESTIMATE
    continuously. That previously only happened inside
    attacks/acoustic_spoof.py's run_feed(), started ONLY when the dashboard's
    "Acoustic Spoof" button was clicked -- confirmed live 2026-08-09 that
    without it, GLOBAL_POSITION_INT never leaves HOME and a goto() click
    arms the vehicle but ArduSub silently refuses to enter AUTO (no visible
    error -- it just stays in whatever mode it was already in), which reads
    on the dashboard as "it armed but never moved."
    Deliberately reuses attacks/acoustic_spoof.py's read_true_ned() (the
    already-fixed Gazebo pose parser, same zero-omission bug class this
    project has hit and fixed 3 times elsewhere) rather than re-deriving
    pose parsing a 4th time -- but does NOT touch that module's shared
    `state`/`_lock` (the attack's forged-offset toggle). This feeder always
    sends the untouched true position; when the Acoustic Spoof attack is
    later launched, ITS OWN separate run_feed() call (via cmd_conn(), a
    different connection/port) starts sending true+offset concurrently --
    the forged signal has to compete with this legitimate one still
    running, exactly the more-credible test setup already used for GPS
    (see legit_gps_feeder's docstring) rather than the attacker being the
    only signal the vehicle ever sees."""
    if DOMAIN != "underwater":
        return
    import acoustic_spoof
    while True:
        try:
            c = mavutil.mavlink_connection(f'udpin:127.0.0.1:{constants.MAVLINK_VISION_FEEDER_PORT}',
                                            source_system=constants.GCS_SOURCE_SYSTEM)
            c.wait_heartbeat(timeout=15)  # see legit_gps_feeder -- same requirement
            c.mav.set_gps_global_origin_send(
                c.target_system, int(constants.HOME_LAT * 1e7), int(constants.HOME_LON * 1e7), 0)
            holder = {}
            for (n, e, d) in acoustic_spoof.read_true_ned(holder):
                us = int(time.time() * 1e6)
                c.mav.vision_position_estimate_send(us, n, e, d, 0.0, 0.0, 0.0)
        except Exception as ex:
            print(f"legit vision feeder error: {ex}; retry 3s"); time.sleep(3)


def believed_thread():
    while True:
        try:
            m = mavutil.mavlink_connection(f'udpin:127.0.0.1:{constants.MAVLINK_DASHBOARD_PORT}')
            while True:
                msg = m.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=2)
                if msg and not (msg.lat == 0 and msg.lon == 0):
                    socketio.emit('gps_believed_update', {'lat': msg.lat / 1e7, 'lon': msg.lon / 1e7})
        except Exception as e:
            print(f"believed thread error: {e}; retry 3s"); time.sleep(3)


def ais_thread():
    # AIS is a surface-only feed; underwater profiles set AIS_UDP_ADDR = None
    # (no AIS propagates underwater), so there is nothing to listen to.
    if not constants.AIS_UDP_ADDR:
        return
    try:
        ip, port = constants.AIS_UDP_ADDR
        for msg in UDPReceiver(ip, port):
            try:
                d = msg.decode()
                if hasattr(d, 'lat') and hasattr(d, 'lon') and d.lat and d.lon:
                    socketio.emit('ais_update', {'mmsi': d.mmsi, 'lat': float(d.lat), 'lon': float(d.lon)})
                    tap({"type": "ais", "t": time.time(),
                         "mmsi": d.mmsi, "lat": float(d.lat), "lon": float(d.lon)})
            except Exception:
                pass
    except Exception as e:
        print(f"AIS thread error: {e}")


def _domain_matches_vehicle(mav_type):
    """The whole 'acoustic alert never fires' class of bug came from running this
    dashboard on one profile (e.g. bluerov2/underwater) while the booted sim was
    actually a different vehicle (e.g. a WAM-V rover). The rover silently ignores
    the underwater VISION_POSITION_ESTIMATE, so nothing ever drifts and no alert
    fires -- with no error anywhere. Guard it: an underwater profile must be a
    SUBMARINE; a surface profile must be a boat/rover."""
    T = mavutil.mavlink
    surface = {T.MAV_TYPE_GROUND_ROVER, T.MAV_TYPE_SURFACE_BOAT}
    underwater = {T.MAV_TYPE_SUBMARINE}
    expected = underwater if DOMAIN == "underwater" else surface
    return mav_type in expected


def detector_thread():
    global _last_warning
    warned_mismatch = False
    while True:
        try:
            m = mavutil.mavlink_connection("tcp:127.0.0.1:5763", source_system=constants.GCS_SOURCE_SYSTEM)
            hb = m.wait_heartbeat(timeout=15)
            m.mav.request_data_stream_send(m.target_system, m.target_component,
                                           mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
            mode_map = {v: k for k, v in m.mode_mapping().items()} if m.mode_mapping() else {}
            socketio.emit('status_update', {'vehicle': VEHICLE_LABEL, 'attacks': list(constants.ATTACKS)})
            if hb is not None and not warned_mismatch and not _domain_matches_vehicle(hb.type):
                warned_mismatch = True
                warn = (f"PROFILE/SIM MISMATCH: dashboard profile '{PROFILE}' is {DOMAIN}, but the "
                        f"running autopilot reports MAV_TYPE={hb.type}. Attacks/alerts for this "
                        f"domain will NOT behave correctly. Reboot with tools/run_demo.sh {PROFILE} up.")
                print("!! " + warn, flush=True)
                _last_warning = warn
                socketio.emit('status_update', {'warning': warn})
            while True:
                msg = m.recv_match(blocking=True, timeout=1)
                if msg is None:
                    continue
                t, mt = time.time(), msg.get_type()
                if mt == "GLOBAL_POSITION_INT":
                    tap({"type": "believed_pos", "t": t, "lat": msg.lat / 1e7, "lon": msg.lon / 1e7})
                    socketio.emit('status_update', {'depth': msg.relative_alt / 1000.0})
                elif mt == "LOCAL_POSITION_NED":
                    tap({"type": "local_pos", "t": t, "n": msg.x, "e": msg.y, "d": msg.z, "vx": msg.vx, "vy": msg.vy})
                elif mt == "VFR_HUD":
                    socketio.emit('status_update', {'speed': msg.groundspeed})
                elif mt == "HEARTBEAT" and msg.type != mavutil.mavlink.MAV_TYPE_GCS:
                    armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    tap({"type": "armed", "t": t, "armed": armed})
                    socketio.emit('status_update', {'armed': armed, 'mode': mode_map.get(msg.custom_mode, str(msg.custom_mode))})
                elif mt == "RC_CHANNELS":
                    driven = [getattr(msg, f"chan{i}_raw", 0) for i in (1, 3)]
                    if any(900 < v < 2100 and abs(v - 1500) > 100 for v in driven):
                        tap({"type": "rc_override", "t": t, "domain": DOMAIN})
        except Exception as e:
            print(f"detector thread error: {e}; retry 3s"); time.sleep(3)


def _gz_xy():
    """Synchronous read of the vehicle's TRUE Gazebo pose (x=East, y=North)."""
    import re
    try:
        p = subprocess.run(["gz", "topic", "-e", "-t", f"/world/{WORLD_NAME}/pose/info", "-n", "2"],
                           stdout=subprocess.PIPE, text=True, timeout=8)
    except Exception:
        return None
    out = None
    for b in p.stdout.split("pose {"):
        if f'name: "{MODEL_NAME}"' in b:
            # See gz_pose_thread()'s comment: a missing x/y means that field
            # is exactly 0.0 (protobuf omits defaults), not "no data".
            mx = re.search(r"position\s*\{\s*x:\s*([-+\d.e]+)", b)
            my = re.search(r"position\s*\{[^}]*y:\s*([-+\d.e]+)", b, re.S)
            out = (float(mx.group(1)) if mx else 0.0, float(my.group(1)) if my else 0.0)
    return out


# --- attack + command execution ---------------------------------------------
_attacks = {}     # type -> stop_event
_last_goal = None  # (lat, lon) of the last destination, to resume after an attack
# goto() opens a brand-new udpin: MAVLink connection every call (not a shared
# singleton like cmd_conn()), and pymavlink sets SO_REUSEADDR on that socket
# (confirmed live 2026-08-09) -- a second bind to the same port from a second
# concurrent goto() call succeeds instead of raising, and the kernel can then
# start delivering that port's incoming traffic to the NEW socket, silently
# stealing replies (MISSION_REQUEST/HEARTBEAT/etc.) out from under the FIRST
# call's still-in-flight mission upload. Redirecting to a new destination
# before the previous goto() finishes (~8-10s, an entirely normal thing to
# do) could therefore corrupt or orphan the earlier navigation command --
# this lock serializes all goto() calls (including stop_attacks()'s own
# resume-course call) so a second click waits its turn instead of racing.
_goto_lock = threading.Lock()


def _relay(cmd):
    try:
        with open(RELAY_FIFO, "w") as f:
            f.write(cmd + "\n")
    except Exception as e:
        print(f"relay write failed: {e}")


def _stop_kind(kind):
    """Stop a single previously-launched ais_spoof/acoustic_spoof instance,
    if one is running -- same logic stop_attacks() uses for these two kinds,
    factored out so launch_attack() can call it before starting a new one.
    Without this, re-launching either attack while one is already active
    orphans the old instance: a new threading.Event()/module reference
    overwrites the old one in _attacks, so the OLD ghost/impersonation
    threads (ais_spoof) or the OLD redundant run_feed thread+subprocess
    (acoustic_spoof) keep running forever, unreachable by any future
    Stop Attacks click (confirmed live 2026-08-09 while auditing the
    dashboard for a reported navigation bug -- a related, real leak found
    along the way, not the bug itself)."""
    if kind == "ais_spoof" and "ais_spoof" in _attacks:
        _attacks.pop("ais_spoof").set()
    elif kind == "acoustic_spoof" and "acoustic_spoof" in _attacks:
        A = _attacks.pop("acoustic_spoof")
        with A._lock:
            A.state.active = False


def launch_attack(kind, opts=None):
    opts = opts or {}
    _attack_launch_t[kind] = time.time()
    _latency_reported.discard(kind)
    if kind == "gps_spoof":
        _relay("step"); return "GPS spoof engaged (+50 m offset injected)"
    if kind == "ais_spoof":
        _stop_kind("ais_spoof")
        import ais_spoof
        stop = threading.Event(); _attacks["ais_spoof"] = stop
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        threading.Thread(target=ais_spoof.run_ghost_vessel, args=(s, stop, 999999001, 2.0), daemon=True).start()
        threading.Thread(target=ais_spoof.run_impersonation,
                         args=(s, stop, lambda: _last_true_pos or (constants.HOME_LAT, constants.HOME_LON)),
                         kwargs={"interval_s": 2.0, "offset_m": 300.0}, daemon=True).start()
        return "AIS spoof engaged (ghost + impersonation broadcasting)"
    if kind == "c2_replay":
        # operator chooses WHICH forged command to inject
        command = opts.get("command", "rc_override")
        import c2_replay
        labels = {
            "rc_override": "forged RC override — attacker seizing the throttle (full ahead)",
            "rc_stop":     "forged RC override — attacker cutting the throttle (stop)",
            "disarm":      "forged DISARM — attacker killing the motors mid-mission",
            "mode_hold":   "forged mode change -> HOLD — attacker halting the mission",
            "mode_manual": "forged mode change -> MANUAL — attacker dropping autonomy",
        }

        def _c2():
            c = cmd_conn()
            if command == "disarm":
                c.mav.command_long_send(c.target_system, c.target_component,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 0, 0, 0, 0, 0, 0)
                c2_replay.log_attack_event(time.time(), "inject_disarm", "forged disarm")
            elif command == "mode_hold":
                c2_replay.inject_forged_mode_change(c, "HOLD")
            elif command == "mode_manual":
                c2_replay.inject_forged_mode_change(c, "MANUAL")
            else:  # rc_override variants -- seize the actuators directly
                c.set_mode(c.mode_mapping().get("MANUAL", 0)); time.sleep(1.5)
                for _ in range(5):
                    c.mav.command_long_send(c.target_system, c.target_component,
                        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0); time.sleep(1)
                # "stop" must be exact RC3_TRIM (1500), NOT some PWM below trim.
                # Confirmed live 2026-08-09 against the CUSV skid-steer twin: this
                # hull's throttle-vs-PWM curve is symmetric around trim (deviation
                # in EITHER direction from 1500 drives throttle UP, not down --
                # 1100 and 1900 both measured as 100% throttle, only 1500 measured
                # as 0%). The previous rc_stop value of 1300 sat inside that
                # "wrong half" and produced ~45% throttle instead of a stop, which
                # is what made a live "Cut throttle" demo look like it silently
                # failed. 1500 is a safe universal choice regardless of a given
                # twin's specific curve, since it's what RC3_TRIM always means by
                # definition.
                thr = 1500 if command == "rc_stop" else 1900
                c2_replay.inject_forged_rc_override(c, throttle_pwm=thr, steering_pwm=1500, duration_s=8.0)
        threading.Thread(target=_c2, daemon=True).start()
        return "C2 injection: " + labels.get(command, command)
    if kind == "acoustic_spoof":
        _stop_kind("acoustic_spoof")
        import acoustic_spoof as A
        _attacks["acoustic_spoof"] = A
        def _ac():
            c = cmd_conn()
            threading.Thread(target=A.run_feed, args=(c,), daemon=True).start()
            time.sleep(8)   # let ExternalNav ESTABLISH before walking it off,
                            # else the belief never drifts and the detector sees nothing
            with A._lock:
                A.state.mode = "ramp"; A.state.start_time = time.time(); A.state.active = True
        threading.Thread(target=_ac, daemon=True).start()
        return "Acoustic-positioning spoof engaged (establishing nav ~8 s, then walking the AUV's belief off)"
    return "unknown attack"


def stop_attacks():
    _relay("off")
    _stop_kind("ais_spoof")
    _stop_kind("acoustic_spoof")
    # An attack may have left the boat in MANUAL (C2) or an EKF failsafe (GPS
    # spoof), so it stops. If a destination is set, put it back on course.
    if _last_goal is not None:
        def _resume():
            time.sleep(4)          # let the EKF re-settle after a GPS spoof
            goto(*_last_goal)
        threading.Thread(target=_resume, daemon=True).start()
        return "attacks stopped — resuming course to destination"
    return "all attacks stopped"


def goto(lat, lon):
    """Serializes all navigation commands through _goto_lock -- see that
    lock's own comment for why (concurrent goto() calls can corrupt each
    other's in-flight mission upload via a shared, SO_REUSEADDR'd port)."""
    with _goto_lock:
        return _goto_locked(lat, lon)


def _goto_locked(lat, lon):
    """Sail to a point via the proven AUTO-mission recipe -- verified to
    physically move the vehicle across the Gazebo water. Uses a fresh connection
    on the auto_mission port (the shared cmd conn / GUIDED target did not
    reliably drive it), uploads a 2-waypoint mission (current -> target),
    switches to AUTO, and arms with confirmation. Only ever called while
    holding _goto_lock (via goto() above) -- do not call directly."""
    global _last_goal
    _last_goal = (lat, lon)
    c = mavutil.mavlink_connection(f'udpin:127.0.0.1:{constants.MAVLINK_AUTO_MISSION_PORT}',
                                   source_system=constants.GCS_SOURCE_SYSTEM)
    if c.wait_heartbeat(timeout=10) is None:
        return "no autopilot heartbeat"
    # reset to a clean fresh state -- arming from MANUAL/disarmed is what reliably
    # (re)starts AUTO navigation; re-arming an already-armed AUTO vehicle does not.
    c.set_mode(c.mode_mapping().get('MANUAL', 0)); time.sleep(0.5)
    c.mav.command_long_send(c.target_system, c.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 0, 0, 0, 0, 0, 0)
    time.sleep(1.5)
    cur = None
    end = time.time() + 3
    while time.time() < end:
        m = c.recv_match(type="GLOBAL_POSITION_INT", blocking=False)
        if m and m.lat:
            cur = (m.lat / 1e7, m.lon / 1e7)
        time.sleep(0.02)
    if cur is None:
        c.close(); return "no position fix yet"
    # --- frame alignment ---------------------------------------------------
    # The clicked point is in the map/true-marker frame (Gazebo pose + HOME).
    # ArduPilot navigates in ITS OWN lat/lon frame, which is offset from the
    # Gazebo frame. So convert: find the boat's current Gazebo pose and its
    # current believed lat/lon, then command a target whose Gazebo offset from
    # NOW equals the clicked point's Gazebo offset from NOW -- i.e. drive the
    # boat's TRUE (Gazebo) position onto the pin, not the raw lat/lon.
    gz = _gz_xy()
    if gz is not None:
        gx, gy = gz
        gxt = (lon - constants.HOME_LON) * M_PER_DEG_LON   # clicked point in Gazebo x (East)
        gyt = (lat - constants.HOME_LAT) * M_PER_DEG_LAT   # clicked point in Gazebo y (North)
        tgt_lat = cur[0] + (gyt - gy) / M_PER_DEG_LAT
        tgt_lon = cur[1] + (gxt - gx) / M_PER_DEG_LON
    else:
        tgt_lat, tgt_lon = lat, lon
    wps = [cur, (tgt_lat, tgt_lon)]
    c.mav.mission_count_send(c.target_system, c.target_component, len(wps))
    for _ in range(len(wps) + 2):
        req = c.recv_match(type=['MISSION_REQUEST', 'MISSION_REQUEST_INT'], blocking=True, timeout=5)
        if not req:
            break
        s = req.seq
        la, lo = wps[s]
        c.mav.mission_item_int_send(
            c.target_system, c.target_component, s,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
            0, 1, 0, 0, 0, 0, int(la * 1e7), int(lo * 1e7), 0)
        if s == len(wps) - 1:
            break
    c.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
    c.set_mode(c.mode_mapping().get('AUTO', 10)); time.sleep(1)
    armed = False
    # 90 attempts @ 1s, not 6 -- a resilient twin's freshly-appeared GPS/
    # ExternalNav fix (legit_gps_feeder / legit_vision_feeder) needs time for
    # ArduPilot's EKF to trust it enough to pass the arming health check
    # (confirmed live 2026-08-09: needs anywhere from ~10s to several
    # minutes depending on how soon after boot the click lands). The old
    # 6-attempt/~6s window meant a click too soon after boot failed
    # PERMANENTLY -- goto() doesn't self-retry, so the vehicle was stuck in
    # AUTO/DISARMED until the user knew to click "Set Destination" again.
    # A single click should just work regardless of timing; retrying for
    # up to 90s (a fresh click loop bails out immediately once armed, so
    # this costs nothing extra on an already-converged vehicle) removes
    # that fragility instead of documenting around it.
    for _ in range(90):
        c.mav.command_long_send(c.target_system, c.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
        time.sleep(1)
        hb = c.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
        if hb and (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            armed = True; break
    # force the mission to (re)start at the target waypoint -- uploading a new
    # mission while already in AUTO does NOT auto-jump to it, so the boat would
    # otherwise keep holding at the previous waypoint.
    c.mav.mission_set_current_send(c.target_system, c.target_component, 1)
    print(f"[goto] AUTO to {lat:.5f},{lon:.5f} armed={armed}", flush=True)
    c.close()
    return f"sailing to {lat:.5f}, {lon:.5f} (AUTO){'' if armed else ' — arm not confirmed'}"


_connected_clients = 0
_connected_lock = threading.Lock()


@socketio.on('connect')
def _on_client_connect():
    """The vehicle label + which attack buttons apply is static (derivable from
    constants at any time), but detector_thread only ever broadcasts it ONCE,
    right after its first heartbeat during boot -- any browser that connects
    later (i.e. the normal case: sim boots, then an operator opens the page)
    silently never gets it, showing a generic header and every attack button
    regardless of domain. Send it directly to each newly-connecting client
    instead of relying on that one-shot broadcast."""
    global _connected_clients
    with _connected_lock:
        _connected_clients += 1
    emit('status_update', {'vehicle': VEHICLE_LABEL, 'attacks': list(constants.ATTACKS)})
    if _last_warning:
        emit('status_update', {'warning': _last_warning})


@socketio.on('disconnect')
def _on_client_disconnect():
    """No attack should keep running unattended once the operator closes the
    dashboard. Only stop when the LAST connected browser goes away (not on
    every disconnect) so a second tab, or a brief network drop with an
    automatic reconnect, doesn't cut off an attack someone is still
    watching from elsewhere."""
    global _connected_clients
    with _connected_lock:
        _connected_clients = max(0, _connected_clients - 1)
        remaining = _connected_clients
    if remaining == 0:
        print("[dashboard] last client disconnected -- stopping any active attacks", flush=True)
        stop_attacks()


# --- routes ------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/cmd/attack', methods=['POST'])
def cmd_attack():
    kind = request.json.get('type')
    try:
        return jsonify(ok=True, msg=launch_attack(kind, request.json))
    except Exception as e:
        return jsonify(ok=False, msg=str(e)), 500


@app.route('/cmd/stop', methods=['POST'])
def cmd_stop():
    return jsonify(ok=True, msg=stop_attacks())


@app.route('/cmd/goto', methods=['POST'])
def cmd_goto():
    d = request.json
    lat, lon = float(d['lat']), float(d['lon'])
    # run async so the mission upload/arm never blocks the HTTP response
    threading.Thread(target=lambda: goto(lat, lon), daemon=True).start()
    return jsonify(ok=True, msg=f"destination set: {lat:.5f}, {lon:.5f} — commanding AUTO nav")


def _report_table_html():
    """Score the blind detectors (this session's alerts) vs ground truth and
    render the same precision/recall/FP-rate/latency + overhead tables as
    tools/generate_report.py, scoped to this live session. Shared by the
    in-page report overlay and the downloadable PDF so they can never drift
    out of sync with each other."""
    result = score_alerts(ALERT_LOG, min_ts=SESSION_START)
    overhead = _live_overhead_snapshot()
    rows = render_family_table(result["families"])
    return f"""
    <div class="tblwrap"><table class="detail">
      <thead>
        <tr>
          <th>Attack</th><th>TP</th><th>FP</th><th>FP rate</th><th>Windows detected</th>
          <th>Precision</th><th>Recall</th><th>Mean latency</th><th>p95 latency</th><th>Max latency</th>
        </tr>
      </thead>
      <tbody>{rows or '<tr><td colspan="10" class="muted">no attacks scored yet this session</td></tr>'}</tbody>
    </table></div>
    <h4 style="margin:16px 0 8px;">System performance overhead (this session)</h4>
    <div class="tblwrap">{render_overhead_panel(overhead)}</div>
    """


@app.route('/cmd/report', methods=['POST'])
def cmd_report():
    try:
        return jsonify(ok=True, html=_report_table_html())
    except Exception as e:
        return jsonify(ok=False, html=f"<p class='missing'>error building report: {e}</p>"), 500


_REPORT_PDF_CSS = """
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; color: #1a1a1a; margin: 0; padding: 24px; }
  h1 { font-size: 1.3rem; margin: 0 0 4px; }
  .meta { color: #666; font-size: 0.85rem; margin-bottom: 1.2rem; }
  table { border-collapse: collapse; width: 100%; margin: 0.6rem 0 1.2rem; font-size: 0.82rem; }
  th, td { border: 1px solid #ccc; padding: 4px 7px; text-align: right; }
  th { background: #f2f2f2; }
  td:first-child, th:first-child { text-align: left; }
  table.kv th { text-align: left; width: 45%; }
  table.kv td { text-align: left; }
  h4 { text-transform: uppercase; font-size: 0.75rem; letter-spacing: .04em; color: #555; }
  .missing { color: #a05a00; font-style: italic; }
"""


@app.route('/cmd/report/pdf')
def cmd_report_pdf():
    """Same report as /cmd/report, rendered to a downloadable PDF via a
    headless Chromium (Playwright, already a project dependency) instead of
    an in-page overlay -- for taking the report off the screen and into a
    presentation/handoff document."""
    try:
        body = _report_table_html()
    except Exception as e:
        return jsonify(ok=False, msg=f"error building report: {e}"), 500

    generated = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    html = f"""<!doctype html><html><head><meta charset="utf-8">
    <title>{html_lib.escape(VEHICLE_LABEL)} — resilience report</title>
    <style>{_REPORT_PDF_CSS}</style></head><body>
    <h1>Maritime Cyber Range — Live Session Report</h1>
    <div class="meta">{html_lib.escape(VEHICLE_LABEL)} &middot; generated {generated}</div>
    {body}
    </body></html>"""

    try:
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as td:
            pdf_path = os.path.join(td, "report.pdf")
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                page.pdf(path=pdf_path, format="A4", margin={"top": "14mm", "bottom": "14mm",
                                                              "left": "12mm", "right": "12mm"})
                browser.close()
            data = open(pdf_path, "rb").read()
    except Exception as e:
        return jsonify(ok=False, msg=f"PDF rendering unavailable ({e}) -- see /cmd/report for the HTML version"), 500

    fname = f"resilience_report_{PROFILE}_{time.strftime('%Y%m%dT%H%M%S')}.pdf"
    return Response(data, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.route('/live/overhead')
def live_overhead():
    return jsonify(_live_overhead_snapshot())


@app.route('/whoami')
def whoami():
    return jsonify(profile=PROFILE, domain=DOMAIN)


if __name__ == '__main__':
    for fn in (gz_pose_thread, legit_gps_feeder, legit_vision_feeder, believed_thread, ais_thread, detector_thread, overhead_emitter):
        threading.Thread(target=fn, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=8080, allow_unsafe_werkzeug=True)
