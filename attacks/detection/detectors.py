"""
WO-23: rule-based attack detectors, per domain.

ISOLATION RULE (docs/ARCHITECTURE.md): detectors consume ONLY live feeds -- the
same telemetry the dashboard sees (believed position from GLOBAL_POSITION_INT /
LOCAL_POSITION_NED, the AIS UDP stream, the MAVLink command/heartbeat/servo
stream). They must NEVER read attack_logs/*.csv. That ground truth is used only
by the offline scorer (WO-25), AFTER the fact, so a detector's precision/recall
can be measured against attacks it never had privileged knowledge of.

Each detector is a pure state machine: feed it feed-events via .update(evt) and
it returns an Alert or None. This makes the exact same logic runnable live
(detection/run_detectors.py taps the real feeds) and testable offline against
synthetic/recorded event streams.

Event shapes (dicts):
  {"type":"believed_pos", "t":ts, "lat":..,"lon":..}      # GLOBAL_POSITION_INT
  {"type":"local_pos",    "t":ts, "n":..,"e":..,"d":..,"vx":..,"vy":..}  # LOCAL_POSITION_NED
  {"type":"ais",          "t":ts, "mmsi":..,"lat":..,"lon":..}
  {"type":"rc_override",  "t":ts}                          # RC_CHANNELS_OVERRIDE seen
  {"type":"armed",        "t":ts, "armed":bool}            # from HEARTBEAT
"""
import math
import time
from dataclasses import dataclass, asdict


@dataclass
class Alert:
    t: float
    detector: str
    attack_type: str      # matches a ground-truth attack family: gps_spoof|ais_spoof|c2_replay|acoustic_spoof
    domain: str
    detail: str

    def as_dict(self):
        return asdict(self)


# WGS84-ish helpers (geodesy, not vehicle data)
_M_PER_DEG_LAT = 111320.0


def _m_per_deg_lon(lat):
    return _M_PER_DEG_LAT * math.cos(math.radians(lat))


def _horiz_m(lat1, lon1, lat2, lon2):
    dn = (lat2 - lat1) * _M_PER_DEG_LAT
    de = (lon2 - lon1) * _m_per_deg_lon((lat1 + lat2) / 2.0)
    return math.hypot(dn, de)


# ---------------------------------------------------------------------------
class GpsJumpDetector:
    """Surface: a believed-position update that implies a speed no surface
    vessel could achieve = a spoofed GPS discontinuity (the step spoof) or an
    accumulating drift faster than the hull can move."""
    def __init__(self, max_speed_mps=15.0):   # ~29 kn, generous for a USV
        self.max_speed = max_speed_mps
        self.last = None

    def update(self, e):
        if e.get("type") != "believed_pos":
            return None
        t, lat, lon = e["t"], e["lat"], e["lon"]
        if lat == 0 and lon == 0:
            return None
        if self.last is not None:
            lt, la, lo = self.last
            dt = t - lt
            if dt > 0:
                speed = _horiz_m(la, lo, lat, lon) / dt
                if speed > self.max_speed:
                    self.last = (t, lat, lon)
                    return Alert(t, "GpsJumpDetector", "gps_spoof", "surface",
                                 f"believed position moved at {speed:.0f} m/s (> {self.max_speed:.0f}) -- implausible")
        self.last = (t, lat, lon)
        return None


# ---------------------------------------------------------------------------
class GpsRampDetector:
    """Surface: catches slow, sustained GPS position drift — the 'ramp' spoof
    profile (e.g. 0.5 m/s) that falls below GpsJumpDetector's speed gate.

    Accumulates a sliding 30s window of believed-position history and alerts
    when the mean displacement speed over that window exceeds `drift_threshold_mps`
    (0.3 m/s default — well above typical GNSS wander noise of ~0.01 m/s in a
    static SITL simulation, well below even a slow-moving autonomous vessel).
    One alert per window_s to avoid repeated firing on the same drift event."""
    def __init__(self, window_s=30.0, drift_threshold_mps=0.3):
        self.window_s = window_s
        self.threshold = drift_threshold_mps
        self.history = []       # [(t, lat, lon)]
        self.last_alert = None

    def update(self, e):
        if e.get("type") != "believed_pos":
            return None
        t, lat, lon = e["t"], e["lat"], e["lon"]
        if lat == 0 and lon == 0:
            return None
        self.history.append((t, lat, lon))
        cutoff = t - self.window_s
        while self.history and self.history[0][0] < cutoff:
            self.history.pop(0)
        if len(self.history) < 5:
            return None
        oldest_t, oldest_lat, oldest_lon = self.history[0]
        dt = t - oldest_t
        if dt <= 0:
            return None
        speed = _horiz_m(oldest_lat, oldest_lon, lat, lon) / dt
        if speed > self.threshold and (
                self.last_alert is None or t - self.last_alert >= self.window_s):
            self.last_alert = t
            return Alert(t, "GpsRampDetector", "gps_spoof", "surface",
                         f"sustained position drift at {speed:.2f} m/s over {dt:.0f}s "
                         f"(> {self.threshold:.2f}) -- possible GPS ramp spoof")


# ---------------------------------------------------------------------------
class AisConflictDetector:
    """Surface: three signatures.
    (a) Impersonation of OUR vessel -- an AIS report under the own-vessel MMSI
        whose position disagrees with the vessel's own telemetry (believed
        position from MAVLink) at every point across a recent lookback window,
        not just the single latest sample. This is a cross-feed check and is
        robust even when the legitimate emulator is between its (sparse)
        position broadcasts -- ITU-R M.1371's own Class-A reporting schedule
        (implemented in nodes/ais_emulator/ais_emulator.py's
        get_report_interval()) drops to one report every 180s for any vessel
        under 3 knots, so a single-latest-sample comparison against a slow or
        stationary vessel produces persistent false "impersonation" alerts
        during completely normal operation (confirmed live 2026-08-08: 12
        false positives / 64% precision over one dashboard session with no
        ais_spoof attack running, purely from the WAM-V holding under ~2 m/s).
        `stale_tolerance_s` bounds the lookback to the spec's own worst-case
        interval (plus slack), so a genuinely forged position -- which won't
        match the vessel's true track at ANY point in that window -- is still
        reliably caught.
    (b) Duplicate-MMSI conflicting position -- any MMSI reporting two positions a
        hull couldn't traverse in the elapsed time.
    (c) Ghost vessel -- a report from a MMSI outside the valid ship MID range
        (a fabricated identity, e.g. 999999001). The own-vessel MMSI is
        whitelisted here even if its MID is unusual (this project uses a test
        MMSI), so the real vessel is never mis-flagged as a ghost.

    Knowing the own-vessel MMSI is operational fleet knowledge (the vessel
    broadcasts it openly), NOT attack ground truth -- so it does not violate the
    detector isolation rule."""
    def __init__(self, known_mmsi=None, max_speed_mps=25.0, mismatch_m=100.0, stale_tolerance_s=200.0):
        self.known = str(known_mmsi) if known_mmsi is not None else None
        self.max_speed = max_speed_mps
        self.mismatch_m = mismatch_m
        self.stale_tolerance_s = stale_tolerance_s
        self.last = {}               # mmsi -> (t, lat, lon)
        self.believed_history = []   # [(t, lat, lon), ...], trimmed to stale_tolerance_s

    @staticmethod
    def _valid_ship_mmsi(mmsi):
        try:
            mid = int(str(int(mmsi))[:3])
        except Exception:
            return False
        return 201 <= mid <= 775

    def update(self, e):
        et = e.get("type")
        if et == "believed_pos":
            if not (e["lat"] == 0 and e["lon"] == 0):
                self.believed_history.append((e["t"], e["lat"], e["lon"]))
                cutoff = e["t"] - self.stale_tolerance_s
                while self.believed_history and self.believed_history[0][0] < cutoff:
                    self.believed_history.pop(0)
            return None
        if et != "ais":
            return None
        t, mmsi, lat, lon = e["t"], e["mmsi"], e["lat"], e["lon"]
        smmsi = str(int(mmsi)) if str(mmsi).isdigit() else str(mmsi)

        # (a) impersonation of our own vessel: AIS says we're somewhere our own
        #     telemetry never showed us, across the whole lookback window --
        #     not just right now.
        if self.known is not None and smmsi == self.known and self.believed_history:
            d = min(_horiz_m(bl, bo, lat, lon) for _, bl, bo in self.believed_history)
            if d > self.mismatch_m:
                return Alert(t, "AisConflictDetector", "ais_spoof", "surface",
                             f"own MMSI {mmsi} broadcast {d:.0f} m from the vessel's own telemetry "
                             f"position (closest match in the last {self.stale_tolerance_s:.0f}s) -- impersonation")

        # (c) ghost: fabricated identity (but never our whitelisted own MMSI)
        if smmsi != self.known and not self._valid_ship_mmsi(mmsi):
            return Alert(t, "AisConflictDetector", "ais_spoof", "surface",
                         f"position report from invalid/fabricated MMSI {mmsi} (ghost vessel)")

        # (b) same-MMSI teleport
        prev = self.last.get(smmsi)
        self.last[smmsi] = (t, lat, lon)
        if prev is not None:
            pt, pla, plo = prev
            dt = t - pt
            if dt > 0 and _horiz_m(pla, plo, lat, lon) / dt > self.max_speed:
                speed = _horiz_m(pla, plo, lat, lon) / dt
                return Alert(t, "AisConflictDetector", "ais_spoof", "surface",
                             f"MMSI {mmsi} reported two positions implying {speed:.0f} m/s -- duplicate-MMSI conflict")
        return None


# ---------------------------------------------------------------------------
class C2CommandDetector:
    """Both domains: detects unauthenticated C2 seizure via two signatures.

    (a) RC_CHANNELS_OVERRIDE — an external party commanding actuators directly.
        There is no legitimate reason for one in this project's autonomous
        operation, so any override is treated as a C2 seizure.
    (b) mode_change — a SET_MODE message observed on the wire that changes the
        vehicle's operating mode. In fully autonomous operation any unexpected
        mode change is a forged command (the inject_forged_mode_change attack).
        Event emitted by detection/run_detectors.py and tools/test_target.py's
        _mavlink_to_event() when a SET_MODE message is seen.

    Backward compat: C2OverrideDetector is an alias for this class — alert
    logs and verdict files reference attack_type='c2_replay', not the detector
    class name, so no existing output breaks."""
    def __init__(self, refractory_s=3.0):
        self.refractory = refractory_s
        self.last_alert = None

    def _emit(self, t, detail, domain):
        if self.last_alert is not None and t - self.last_alert < self.refractory:
            return None
        self.last_alert = t
        return Alert(t, "C2CommandDetector", "c2_replay", domain, detail)

    def update(self, e):
        t = e.get("t", time.time())
        et = e.get("type")
        if et == "rc_override":
            return self._emit(t, "RC_CHANNELS_OVERRIDE observed -- actuator command authority seized",
                              e.get("domain", "surface"))
        if et == "mode_change":
            new_mode = e.get("new_mode", "UNKNOWN")
            prev_mode = e.get("prev_mode", "UNKNOWN")
            return self._emit(t,
                              f"Unexpected SET_MODE observed: {prev_mode} -> {new_mode} -- forged mode change",
                              e.get("domain", "surface"))
        return None


# Backward compat alias -- alert logs reference attack_type='c2_replay', not
# this class name, so renaming is safe for all existing output files.
C2OverrideDetector = C2CommandDetector


# ---------------------------------------------------------------------------
class AcousticDivergenceDetector:
    """Underwater: the acoustic (ExternalNav) position spoof walks the AUV's
    believed position. Physical tell: the vehicle's believed position moves
    while it is NOT under propulsion (disarmed, or thrusters idle) -- position
    changing with no way to have caused it. Catches both the step and the
    stealthy slow ramp, which a pure speed gate would miss."""
    def __init__(self, drift_speed_mps=0.15, refractory_s=3.0):
        self.drift_speed = drift_speed_mps
        self.refractory = refractory_s
        self.armed = False
        self.last = None        # (t, n, e)
        self.last_alert = None

    def update(self, ev):
        et = ev.get("type")
        if et == "armed":
            self.armed = ev["armed"]
            return None
        if et != "local_pos":
            return None
        t, n, e = ev["t"], ev["n"], ev["e"]
        alert = None
        if self.last is not None and not self.armed:
            lt, ln, le = self.last
            dt = t - lt
            if dt > 0:
                speed = math.hypot(n - ln, e - le) / dt
                if speed > self.drift_speed and (
                        self.last_alert is None or t - self.last_alert >= self.refractory):
                    self.last_alert = t
                    alert = Alert(t, "AcousticDivergenceDetector", "acoustic_spoof", "underwater",
                                  f"believed position drifting {speed:.2f} m/s while UNPROPELLED (disarmed) -- external-nav/acoustic spoof")
        self.last = (t, n, e)
        return alert


# ---------------------------------------------------------------------------
class CusumDriftDetector:
    """Surface & Underwater: Two-Sided Page's CUSUM sequential change-point detector.
    
    Catches stealthy low-rate walk-offs (e.g. 0.15 - 0.4 m/s) that stay below static
    speed gates, without privileged knowledge of attack trajectory or timing.
    Applies exponential smoothing (tau ~ 1.0s) to reject zero-mean wave agitation,
    accumulating persistent velocity divergence along Cartesian axes.
    """
    def __init__(self, slack_mps=0.15, threshold_m=5.0, smoothing_tau_s=1.0, refractory_s=5.0):
        self.k = slack_mps
        self.h = threshold_m
        self.tau = smoothing_tau_s
        self.refractory_s = refractory_s
        self.last_t = None
        self.last_n = None
        self.last_e = None
        self.res_vn_filt = 0.0
        self.res_ve_filt = 0.0
        self.cusum_n_pos = 0.0
        self.cusum_n_neg = 0.0
        self.cusum_e_pos = 0.0
        self.cusum_e_neg = 0.0
        self.last_alert = None

    def update(self, e):
        et = e.get("type")
        t = e.get("t")
        if t is None:
            return None
            
        cur_n, cur_e = None, None
        meas_vn, meas_ve = None, None

        if et == "local_pos":
            cur_n, cur_e = e["n"], e["e"]
            meas_vn, meas_ve = e.get("vx", 0.0), e.get("vy", 0.0)
            domain = e.get("domain", "surface")
        elif et == "believed_pos":
            lat, lon = e["lat"], e["lon"]
            if lat == 0 and lon == 0:
                return None
            # Project to local Cartesian tangent frame (meters)
            cur_n = lat * _M_PER_DEG_LAT
            cur_e = lon * _m_per_deg_lon(lat)
            meas_vn = e.get("vn", 0.0)
            meas_ve = e.get("ve", 0.0)
            domain = "surface"
        else:
            return None

        if self.last_t is None:
            self.last_t = t
            self.last_n = cur_n
            self.last_e = cur_e
            return None

        dt = t - self.last_t
        if dt <= 0.001:
            return None

        # Velocity from position differences
        v_diff_n = (cur_n - self.last_n) / dt
        v_diff_e = (cur_e - self.last_e) / dt
        self.last_t = t
        self.last_n = cur_n
        self.last_e = cur_e

        # Innovation residual against measured velocity (or 0 if stationary)
        ref_vn = meas_vn if meas_vn is not None else 0.0
        ref_ve = meas_ve if meas_ve is not None else 0.0
        raw_res_n = v_diff_n - ref_vn
        raw_res_e = v_diff_e - ref_ve

        # Exponential low-pass filter
        alpha = dt / (self.tau + dt)
        self.res_vn_filt += alpha * (raw_res_n - self.res_vn_filt)
        self.res_ve_filt += alpha * (raw_res_e - self.res_ve_filt)

        # Page's Two-Sided CUSUM integration
        self.cusum_n_pos = max(0.0, self.cusum_n_pos + (self.res_vn_filt - self.k) * dt)
        self.cusum_n_neg = max(0.0, self.cusum_n_neg + (-self.res_vn_filt - self.k) * dt)
        self.cusum_e_pos = max(0.0, self.cusum_e_pos + (self.res_ve_filt - self.k) * dt)
        self.cusum_e_neg = max(0.0, self.cusum_e_neg + (-self.res_ve_filt - self.k) * dt)

        peak = max(self.cusum_n_pos, self.cusum_n_neg, self.cusum_e_pos, self.cusum_e_neg)
        if peak >= self.h and (self.last_alert is None or t - self.last_alert >= self.refractory_s):
            self.last_alert = t
            self.cusum_n_pos = self.cusum_n_neg = self.cusum_e_pos = self.cusum_e_neg = 0.0
            attack_type = "acoustic_spoof" if domain == "underwater" else "gps_spoof"
            return Alert(t, "CusumDriftDetector", attack_type, domain,
                         f"cumulative Page's CUSUM residual reached {peak:.2f} m (> {self.h:.2f} m) -- stealthy drift detected")

        return None


# ---------------------------------------------------------------------------
class KinematicConsistencyDetector:
    """Cross-sensor kinematic consistency: checks whether the rate of change of
    believed/reported position matches internal vehicle dynamic state (IMU/velocities).
    If GPS/Acoustic position is walking off while vehicle thrusters are idle or INS speed is ~0,
    triggers an alert."""
    def __init__(self, speed_discrepancy_mps=1.5, refractory_s=4.0):
        self.speed_discrepancy = speed_discrepancy_mps
        self.refractory_s = refractory_s
        self.last_pos = None     # (t, n, e)
        self.last_alert = None

    def update(self, e):
        et = e.get("type")
        if et != "local_pos":
            return None
        t, n, e_pos = e["t"], e["n"], e["e"]
        ins_vx, ins_vy = e.get("vx", 0.0), e.get("vy", 0.0)
        domain = e.get("domain", "surface")

        if self.last_pos is None:
            self.last_pos = (t, n, e_pos)
            return None

        lt, ln, le = self.last_pos
        dt = t - lt
        if dt < 0.1:
            return None
        self.last_pos = (t, n, e_pos)

        diff_vn = (n - ln) / dt
        diff_ve = (e_pos - le) / dt
        gps_speed = math.hypot(diff_vn, diff_ve)
        ins_speed = math.hypot(ins_vx, ins_vy)

        speed_error = abs(gps_speed - ins_speed)
        if speed_error > self.speed_discrepancy and (self.last_alert is None or t - self.last_alert >= self.refractory_s):
            self.last_alert = t
            attack_type = "acoustic_spoof" if domain == "underwater" else "gps_spoof"
            return Alert(t, "KinematicConsistencyDetector", attack_type, domain,
                         f"kinematic discrepancy: pos rate {gps_speed:.2f} m/s vs INS speed {ins_speed:.2f} m/s "
                         f"(delta {speed_error:.2f} m/s > {self.speed_discrepancy:.2f} m/s)")
        return None


# ---------------------------------------------------------------------------
DOMAIN_DETECTORS = {
    "surface": lambda cfg: [
        GpsJumpDetector(),
        GpsRampDetector(),
        CusumDriftDetector(),
        KinematicConsistencyDetector(),
        AisConflictDetector(known_mmsi=cfg.get("known_mmsi")),
        C2CommandDetector(),
    ],
    "underwater": lambda cfg: [
        AcousticDivergenceDetector(),
        CusumDriftDetector(),
        KinematicConsistencyDetector(),
        C2CommandDetector(),
    ],
}


class DetectorSuite:
    """Holds the detectors applicable to a domain and fans each event to all of
    them, collecting alerts. `cfg` carries operational context (e.g. the own
    vessel's MMSI) -- NOT attack ground truth."""
    def __init__(self, domain, cfg=None):
        self.domain = domain
        self.detectors = DOMAIN_DETECTORS[domain](cfg or {})

    def update(self, event):
        out = []
        for d in self.detectors:
            a = d.update(event)
            if a is not None:
                out.append(a)
        return out
