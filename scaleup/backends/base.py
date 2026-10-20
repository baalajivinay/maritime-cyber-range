"""Autopilot-agnostic vehicle backend abstraction (Axis 1.1 -- "make it generic").

A VehicleBackend describes ONE autopilot family (ArduPilot, PX4, ...) in the
terms the range needs to drive and attack it, so the tester and attack layer can
be written against an interface instead of ArduPilot internals.

It does NOT replace tools/run_sim.sh (the live boot engine); it is the seam that
makes the rest of the stack firmware-agnostic. What is universal here:

  * the connection endpoints for each role (gcs / tester / vision / acoustic),
  * the attack-vector applicability matrix per firmware + domain,
  * the STANDARD message each attack vector uses -- so an attack is
    "send GPS_INPUT #232" or "send VISION_POSITION_ESTIMATE #102", not
    "poke ArduPilot's proprietary JSON FDM".

Stdlib only. Live-boot wiring is per-backend and documented on each subclass.
"""
from dataclasses import dataclass, field

# --- attack vectors (firmware-independent names) -----------------------------
GPS_SPOOF = "gps_spoof"
AIS_SPOOF = "ais_spoof"
C2_REPLAY = "c2_replay"
ACOUSTIC_SPOOF = "acoustic_spoof"
ALL_VECTORS = (GPS_SPOOF, AIS_SPOOF, C2_REPLAY, ACOUSTIC_SPOOF)


@dataclass
class InjectionSpec:
    """How a given attack vector is delivered to THIS firmware."""
    transport: str          # "mavlink" | "fdm_json" | "udp_nmea" | ...
    message: str            # e.g. "GPS_INPUT", "VISION_POSITION_ESTIMATE", "SET_MODE"
    note: str = ""


@dataclass
class VehicleBackend:
    name: str
    firmware: str                       # "ArduPilot" | "PX4"
    domains: tuple = ("surface", "underwater")
    # vector -> InjectionSpec (present == applicable for this firmware);
    # domain-level N/A (e.g. GPS submerged) is decided by applies(vector, domain).
    vectors: dict = field(default_factory=dict)
    endpoints: dict = field(default_factory=dict)   # role -> connection string
    live_boot: str = ""                 # one line: how this backend boots for real

    def supports(self, vector):
        return vector in self.vectors

    def applies(self, vector, domain):
        """Firmware supports it AND it is physically applicable in this domain."""
        if vector not in self.vectors:
            return False
        if domain == "underwater" and vector in (GPS_SPOOF, AIS_SPOOF):
            return False            # RF does not penetrate water
        if domain == "surface" and vector == ACOUSTIC_SPOOF:
            return False            # surface vessels use GNSS, not USBL/DVL
        return True

    def injection(self, vector):
        return self.vectors.get(vector)

    def connection(self, role):
        return self.endpoints.get(role)

    def describe(self):
        return {
            "name": self.name, "firmware": self.firmware, "domains": list(self.domains),
            "vectors": {v: {"transport": s.transport, "message": s.message, "note": s.note}
                        for v, s in self.vectors.items()},
            "endpoints": dict(self.endpoints),
            "live_boot": self.live_boot,
        }
