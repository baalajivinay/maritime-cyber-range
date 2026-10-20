"""Real AIS traffic ingest (Axis 2.1, Tier B). Replaces scripted contacts with
real vessels so the AisConflictDetector and the scenario engine's CPA /
collision-risk consequences are exercised against genuine harbour traffic.

Decodes AIVDM with pyais (already a project dependency). from_file reads a
recorded capture; stream_udp taps a live feed (e.g. an AIS receiver or an
aggregator relay). Each contact is normalised to the shape the detectors and
scenario contacts already use.
"""
import socket
import time

try:
    from pyais import decode as _ais_decode
except Exception:               # pragma: no cover
    _ais_decode = None


def _to_contact(msg):
    d = msg.asdict() if hasattr(msg, "asdict") else dict(msg)
    if d.get("lat") in (None, 181.0) or d.get("lon") in (None, 181.0):
        return None
    return {
        "mmsi": d.get("mmsi"),
        "lat": float(d["lat"]),
        "lon": float(d["lon"]),
        "sog_knots": float(d["speed"]) if d.get("speed") not in (None, 1023) else None,
        "cog_deg": float(d["course"]) if d.get("course") not in (None, 3600) else None,
        "t": time.time(),
    }


class AISFeed:
    def __init__(self, source="feed"):
        self.source = source

    @staticmethod
    def decode_lines(lines):
        """Decode an iterable of AIVDM sentences -> list of contact dicts.
        Silently skips multi-part fragments it can't assemble and junk lines."""
        if _ais_decode is None:
            raise RuntimeError("pyais not installed -- cannot decode AIS")
        out = []
        for ln in lines:
            ln = ln.strip()
            if not ln.startswith("!AIVD"):
                continue
            try:
                c = _to_contact(_ais_decode(ln))
            except Exception:
                continue
            if c:
                out.append(c)
        return out

    @classmethod
    def from_file(cls, path):
        with open(path) as f:
            return cls.decode_lines(f)

    @staticmethod
    def stream_udp(host="127.0.0.1", port=10110, on_contact=None, stop=None):
        """Tap a live AIVDM UDP feed; calls on_contact(contact) for each fix.
        Runs until stop() returns True (or forever)."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.settimeout(1.0)
        while not (stop and stop()):
            try:
                data, _ = s.recvfrom(4096)
            except socket.timeout:
                continue
            for c in AISFeed.decode_lines(data.decode("ascii", "ignore").splitlines()):
                if on_contact:
                    on_contact(c)
