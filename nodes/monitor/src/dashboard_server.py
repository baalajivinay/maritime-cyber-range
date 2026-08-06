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
import math
import hmac
import socket
import statistics
import resource
import threading
import subprocess
from collections import deque
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
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
            c = mavutil.mavlink_connection("tcp:127.0.0.1:5762", source_system=250)
            c.wait_heartbeat(timeout=15)
            _cmd_conn = c
        return _cmd_conn


# --- feed threads ------------------------------------------------------------
def gz_pose_thread():
    """CLEAN true position from Gazebo ground truth (no GPS noise)."""
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
                        mx = re.search(r"position\s*\{\s*x:\s*([-\d.e]+)", block)
                        my = re.search(r"position\s*\{[^}]*y:\s*([-\d.e]+)", block, re.S)
                        if mx and my:
                            x, y = float(mx.group(1)), float(my.group(1))
                            socketio.emit('gps_true_update', {
                                'lat': constants.HOME_LAT + y / M_PER_DEG_LAT,
                                'lon': constants.HOME_LON + x / M_PER_DEG_LON})
                        in_model = False
        except Exception as e:
            print(f"gz pose thread error: {e}; retry 3s"); time.sleep(3)


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
    label = f"{DOMAIN.title()} — {PROFILE} ({constants.ARDUPILOT_VEHICLE_TYPE})"
    warned_mismatch = False
    while True:
        try:
            m = mavutil.mavlink_connection("tcp:127.0.0.1:5763")
            hb = m.wait_heartbeat(timeout=15)
            m.mav.request_data_stream_send(m.target_system, m.target_component,
                                           mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
            mode_map = {v: k for k, v in m.mode_mapping().items()} if m.mode_mapping() else {}
            socketio.emit('status_update', {'vehicle': label, 'attacks': list(constants.ATTACKS)})
            if hb is not None and not warned_mismatch and not _domain_matches_vehicle(hb.type):
                warned_mismatch = True
                warn = (f"PROFILE/SIM MISMATCH: dashboard profile '{PROFILE}' is {DOMAIN}, but the "
                        f"running autopilot reports MAV_TYPE={hb.type}. Attacks/alerts for this "
                        f"domain will NOT behave correctly. Reboot with tools/run_demo.sh {PROFILE} up.")
                print("!! " + warn, flush=True)
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
            mx = re.search(r"position\s*\{\s*x:\s*([-\d.e]+)", b)
            my = re.search(r"position\s*\{[^}]*y:\s*([-\d.e]+)", b, re.S)
            if mx and my:
                out = (float(mx.group(1)), float(my.group(1)))
    return out


# --- attack + command execution ---------------------------------------------
_attacks = {}     # type -> stop_event
_last_goal = None  # (lat, lon) of the last destination, to resume after an attack


def _relay(cmd):
    try:
        with open(RELAY_FIFO, "w") as f:
            f.write(cmd + "\n")
    except Exception as e:
        print(f"relay write failed: {e}")


def launch_attack(kind, opts=None):
    opts = opts or {}
    _attack_launch_t[kind] = time.time()
    _latency_reported.discard(kind)
    if kind == "gps_spoof":
        _relay("step"); return "GPS spoof engaged (+50 m offset injected)"
    if kind == "ais_spoof":
        import ais_spoof
        stop = threading.Event(); _attacks["ais_spoof"] = stop
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        threading.Thread(target=ais_spoof.run_ghost_vessel, args=(s, stop, 999999001, 2.0), daemon=True).start()
        threading.Thread(target=ais_spoof.run_impersonation,
                         args=(s, stop, lambda: (constants.HOME_LAT, constants.HOME_LON)),
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
                thr = 1300 if command == "rc_stop" else 1900
                c2_replay.inject_forged_rc_override(c, throttle_pwm=thr, steering_pwm=1500, duration_s=8.0)
        threading.Thread(target=_c2, daemon=True).start()
        return "C2 injection: " + labels.get(command, command)
    if kind == "acoustic_spoof":
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
    if "ais_spoof" in _attacks:
        _attacks.pop("ais_spoof").set()
    if "acoustic_spoof" in _attacks:
        A = _attacks.pop("acoustic_spoof")
        with A._lock:
            A.state.active = False
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
    """Sail to a point via the proven AUTO-mission recipe -- verified to
    physically move the vehicle across the Gazebo water. Uses a fresh connection
    on the auto_mission port (the shared cmd conn / GUIDED target did not
    reliably drive it), uploads a 2-waypoint mission (current -> target),
    switches to AUTO, and arms with confirmation."""
    global _last_goal
    _last_goal = (lat, lon)
    c = mavutil.mavlink_connection(f'udpin:127.0.0.1:{constants.MAVLINK_AUTO_MISSION_PORT}')
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
    for _ in range(6):
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


@app.route('/cmd/report', methods=['POST'])
def cmd_report():
    """Score the blind detectors (this session's alerts) vs ground truth and
    render the same precision/recall/FP-rate/latency + overhead tables as
    tools/generate_report.py, scoped to this live session."""
    try:
        result = score_alerts(ALERT_LOG, min_ts=SESSION_START)
        overhead = _live_overhead_snapshot()
        rows = render_family_table(result["families"])
        frag = f"""
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
        return jsonify(ok=True, html=frag)
    except Exception as e:
        return jsonify(ok=False, html=f"<p class='missing'>error building report: {e}</p>"), 500


@app.route('/live/overhead')
def live_overhead():
    return jsonify(_live_overhead_snapshot())


@app.route('/cmd/vehicle', methods=['POST'])
def cmd_vehicle():
    """Switching vehicle means rebooting the whole stack + this dashboard for a
    different profile. Doing that live from here proved fragile (it can leave
    overlapping worlds mid-presentation), so this now just GUIDES the operator to
    relaunch cleanly instead of tearing down the running demo."""
    prof = request.json.get('profile')
    if prof not in ("wamv", "blueboat", "bluerov2"):
        return jsonify(ok=False, msg="unknown profile"), 400
    if prof == PROFILE:
        return jsonify(ok=True, switching=False, msg=f"already running {prof}")
    # Spawn the demo launcher detached. run_demo.sh's `up` self-cleans (kills any
    # running demo of any profile) and reboots for the new one -- including a
    # fresh dashboard with the new profile. This launcher is NOT matched by the
    # teardown patterns, so it survives the current dashboard being killed. The
    # browser polls /whoami and reloads when the new dashboard reports `prof`.
    script = (f"source /opt/ros/jazzy/setup.bash 2>/dev/null; "
              f"source '{_REPO}/ros2_ws/install/setup.bash' 2>/dev/null; "
              f"exec '{_REPO}/tools/run_demo.sh' {prof} up")
    subprocess.Popen(["setsid", "bash", "-c", script],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, start_new_session=True)
    return jsonify(ok=True, switching=True, profile=prof,
                   msg=f"switching to {prof} (~40 s) — the page reloads automatically")


@app.route('/whoami')
def whoami():
    return jsonify(profile=PROFILE, domain=DOMAIN)


if __name__ == '__main__':
    for fn in (gz_pose_thread, believed_thread, ais_thread, detector_thread, overhead_emitter):
        threading.Thread(target=fn, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=8080, allow_unsafe_werkzeug=True)
