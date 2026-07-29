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
class AisConflictDetector:
    """Surface: three signatures.
    (a) Impersonation of OUR vessel -- an AIS report under the own-vessel MMSI
        whose position disagrees with the vessel's own telemetry (believed
        position from MAVLink). This is a cross-feed check and is robust even
        when the legitimate emulator is between its (sparse) position broadcasts.
    (b) Duplicate-MMSI conflicting position -- any MMSI reporting two positions a
        hull couldn't traverse in the elapsed time.
    (c) Ghost vessel -- a report from a MMSI outside the valid ship MID range
        (a fabricated identity, e.g. 999999001). The own-vessel MMSI is
        whitelisted here even if its MID is unusual (this project uses a test
        MMSI), so the real vessel is never mis-flagged as a ghost.

    Knowing the own-vessel MMSI is operational fleet knowledge (the vessel
    broadcasts it openly), NOT attack ground truth -- so it does not violate the
    detector isolation rule."""
    def __init__(self, known_mmsi=None, max_speed_mps=25.0, mismatch_m=100.0):
        self.known = str(known_mmsi) if known_mmsi is not None else None
        self.max_speed = max_speed_mps
        self.mismatch_m = mismatch_m
        self.last = {}          # mmsi -> (t, lat, lon)
        self.believed = None    # (lat, lon) of our own vessel, from MAVLink

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
                self.believed = (e["lat"], e["lon"])
            return None
        if et != "ais":
            return None
        t, mmsi, lat, lon = e["t"], e["mmsi"], e["lat"], e["lon"]
        smmsi = str(int(mmsi)) if str(mmsi).isdigit() else str(mmsi)

        # (a) impersonation of our own vessel: AIS says we're somewhere our own
        #     telemetry says we're not.
        if self.known is not None and smmsi == self.known and self.believed is not None:
            d = _horiz_m(self.believed[0], self.believed[1], lat, lon)
            if d > self.mismatch_m:
                return Alert(t, "AisConflictDetector", "ais_spoof", "surface",
                             f"own MMSI {mmsi} broadcast {d:.0f} m from the vessel's own telemetry "
                             f"position -- impersonation")

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
class C2OverrideDetector:
    """Both domains: an RC_CHANNELS_OVERRIDE is an external party commanding
    actuators directly -- there is no legitimate reason for one in this project's
    autonomous operation, so any override is a C2 seizure."""
    def __init__(self, refractory_s=3.0):
        self.refractory = refractory_s
        self.last_alert = None

    def update(self, e):
        if e.get("type") != "rc_override":
            return None
        t = e["t"]
        if self.last_alert is not None and t - self.last_alert < self.refractory:
            return None
        self.last_alert = t
        return Alert(t, "C2OverrideDetector", "c2_replay", e.get("domain", "surface"),
                     "RC_CHANNELS_OVERRIDE observed -- actuator command authority seized")


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
DOMAIN_DETECTORS = {
    "surface": lambda cfg: [GpsJumpDetector(), AisConflictDetector(known_mmsi=cfg.get("known_mmsi")), C2OverrideDetector()],
    "underwater": lambda cfg: [AcousticDivergenceDetector(), C2OverrideDetector()],
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
