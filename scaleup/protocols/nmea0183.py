"""NMEA 0183 adapter (Axis 1.2) -- real, stdlib-only codec for the sentences a
GNSS/sounder/compass puts on a ship's serial bus, plus a position spoofer that
walks a forged fix (the serial-bus analog of attacks/gps_spoof.py).

This is what lets the range attack a real ECDIS / chart plotter / autopilot that
consumes NMEA 0183 over RS-422, instead of only an ArduPilot MAVLink endpoint --
and it is exactly what the ESP32 NMEA injector firmware (hardware/) emits on its
UART for true hardware-in-the-loop sensor spoofing.

Supported sentences: GGA (fix), RMC (position/velocity/time), VTG (track/speed),
DBT (depth), HDT (heading). All with correct ddmm.mmmm formatting and XOR
checksum. parse() round-trips our own output and real receiver sentences.
"""
import time
import math
from .base import ProtocolAdapter

_M_PER_DEG_LAT = 111320.0


def checksum(body):
    """XOR of every char between '$' and '*' (exclusive), as 2 upper-hex digits."""
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"{c:02X}"


def build(talker, stype, fields):
    """Assemble a full sentence: '$<talker><type>,<f1>,<f2>,...*HH\\r\\n'."""
    body = f"{talker}{stype}," + ",".join("" if f is None else str(f) for f in fields)
    return f"${body}*{checksum(body)}\r\n"


def _dm(value, is_lat):
    """Decimal degrees -> (ddmm.mmmm, hemisphere) NMEA form."""
    hemi = ("N" if value >= 0 else "S") if is_lat else ("E" if value >= 0 else "W")
    v = abs(value)
    deg = int(v)
    minutes = (v - deg) * 60.0
    width = 2 if is_lat else 3
    return f"{deg:0{width}d}{minutes:07.4f}", hemi


def _from_dm(dm, hemi):
    """ddmm.mmmm + hemisphere -> decimal degrees."""
    if not dm:
        return None
    dot = dm.find(".")
    deg = int(dm[:dot - 2]) if dot >= 2 else 0
    minutes = float(dm[dot - 2:])
    val = deg + minutes / 60.0
    if hemi in ("S", "W"):
        val = -val
    return val


def encode_gga(lat, lon, t=None, fix_quality=1, num_sats=9, hdop=0.8, alt_m=0.0):
    hhmmss = time.strftime("%H%M%S", time.gmtime(t if t is not None else time.time()))
    lat_dm, ns = _dm(lat, True)
    lon_dm, ew = _dm(lon, False)
    return build("GP", "GGA", [hhmmss + ".00", lat_dm, ns, lon_dm, ew,
                               fix_quality, num_sats, f"{hdop:.1f}", f"{alt_m:.1f}", "M", "0.0", "M", "", ""])


def encode_rmc(lat, lon, sog_knots=0.0, cog_deg=0.0, t=None):
    tm = time.gmtime(t if t is not None else time.time())
    hhmmss = time.strftime("%H%M%S", tm)
    ddmmyy = time.strftime("%d%m%y", tm)
    lat_dm, ns = _dm(lat, True)
    lon_dm, ew = _dm(lon, False)
    return build("GP", "RMC", [hhmmss + ".00", "A", lat_dm, ns, lon_dm, ew,
                               f"{sog_knots:.1f}", f"{cog_deg:.1f}", ddmmyy, "", "", "A"])


def encode_vtg(cog_deg=0.0, sog_knots=0.0):
    return build("GP", "VTG", [f"{cog_deg:.1f}", "T", "", "M",
                               f"{sog_knots:.1f}", "N", f"{sog_knots * 1.852:.1f}", "K", "A"])


def encode_dbt(depth_m):
    return build("SD", "DBT", [f"{depth_m / 0.3048:.1f}", "f", f"{depth_m:.1f}", "M",
                               f"{depth_m / 1.852:.1f}", "F"])


def encode_hdt(heading_deg):
    return build("HE", "HDT", [f"{heading_deg:.1f}", "T"])


def parse(sentence):
    """Parse one sentence -> dict. 'valid' reflects the checksum."""
    s = sentence.strip()
    if not s.startswith("$"):
        return {"valid": False, "error": "no '$'"}
    star = s.rfind("*")
    body = s[1:star] if star >= 0 else s[1:]
    got = s[star + 1:star + 3].upper() if star >= 0 else None
    valid = (got == checksum(body)) if got else False
    parts = body.split(",")
    head = parts[0]
    talker, stype = head[:2], head[2:]
    fields = parts[1:]
    out = {"valid": valid, "talker": talker, "type": stype, "fields": fields}
    try:
        if stype == "GGA":
            out["lat"] = _from_dm(fields[1], fields[2])
            out["lon"] = _from_dm(fields[3], fields[4])
        elif stype == "RMC":
            out["lat"] = _from_dm(fields[2], fields[3])
            out["lon"] = _from_dm(fields[4], fields[5])
            out["sog_knots"] = float(fields[6]) if fields[6] else None
        elif stype == "DBT":
            out["depth_m"] = float(fields[2]) if len(fields) > 2 and fields[2] else None
    except (IndexError, ValueError):
        pass
    return out


class NMEA0183Adapter(ProtocolAdapter):
    """Encodes forged fixes and decodes observed sentences into detector events
    (believed_pos) so the existing blind detectors tap a serial bus unchanged."""
    name = "nmea0183"

    def encode(self, kind, **fields):
        if kind in ("gps", "position"):
            return encode_gga(fields["lat"], fields["lon"], t=fields.get("t"))
        if kind == "rmc":
            return encode_rmc(fields["lat"], fields["lon"],
                              fields.get("sog_knots", 0.0), fields.get("cog_deg", 0.0), t=fields.get("t"))
        if kind == "depth":
            return encode_dbt(fields["depth_m"])
        if kind == "heading":
            return encode_hdt(fields["heading_deg"])
        raise ValueError(f"nmea0183: unknown kind '{kind}'")

    def decode(self, raw):
        events = []
        for line in raw.splitlines():
            p = parse(line)
            if p.get("valid") and p.get("type") in ("GGA", "RMC") and p.get("lat") is not None:
                events.append({"type": "believed_pos", "t": time.time(),
                               "lat": p["lat"], "lon": p["lon"]})
        return events


class NMEASpoofer:
    """Walks a forged NMEA position off a start point -- the serial-bus analog of
    the GPS FDM relay. step() snaps an offset; ramp() drifts it; sentences()
    yields the forged GGA+RMC for the current forged position."""
    def __init__(self, lat0, lon0, bearing_deg=90.0):
        self.lat0, self.lon0 = lat0, lon0
        self.bearing = bearing_deg
        self.mode = None
        self.step_m = 0.0
        self.rate_mps = 0.0
        self.t_start = None

    def step(self, offset_m):
        self.mode, self.step_m, self.t_start = "step", offset_m, time.time()

    def ramp(self, rate_mps):
        self.mode, self.rate_mps, self.t_start = "ramp", rate_mps, time.time()

    def off(self):
        self.mode = None

    def _offset_m(self):
        if self.mode == "step":
            return self.step_m
        if self.mode == "ramp":
            return self.rate_mps * (time.time() - self.t_start)
        return 0.0

    def current(self):
        mag = self._offset_m()
        br = math.radians(self.bearing)
        dn, de = mag * math.cos(br), mag * math.sin(br)
        lat = self.lat0 + dn / _M_PER_DEG_LAT
        lon = self.lon0 + de / (_M_PER_DEG_LAT * math.cos(math.radians(self.lat0)))
        return lat, lon

    def sentences(self, sog_knots=0.0, cog_deg=None):
        lat, lon = self.current()
        return encode_gga(lat, lon) + encode_rmc(lat, lon, sog_knots,
                                                 self.bearing if cog_deg is None else cog_deg)
