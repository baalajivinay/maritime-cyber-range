"""Protocol-adapter abstraction (Axis 1.2 -- the universality unlock).

Today the "vehicle" is an autopilot speaking MAVLink. The real maritime attack
surface is the BRIDGE EQUIPMENT BUS: NMEA 0183/2000, AIS, ECDIS, radar/ARPA,
GNSS/RTK, DVL, INS, gyrocompass. A ProtocolAdapter makes an attack
"inject on interface X" and a detector "tap interface X", so the same range can
target a real ship's bridge, not just a flight controller.

Each adapter converts between (a) a forged *intent* ("report position P",
"change mode to M") and (b) the on-wire bytes of its protocol, and parses
observed bytes back into the detector event shapes detection/detectors.py
already consumes ({"type":"believed_pos",...} etc.) -- so the existing blind
detectors work across protocols unchanged.
"""


class ProtocolAdapter:
    name = "abstract"

    def encode(self, kind, **fields):
        """Craft the on-wire bytes for a forged message of `kind`."""
        raise NotImplementedError

    def decode(self, raw):
        """Parse observed bytes into a list of detector events (possibly empty)."""
        raise NotImplementedError
