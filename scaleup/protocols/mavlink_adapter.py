"""MAVLink protocol adapter (Axis 1.2). Thin shim that presents the range's
existing MAVLink attack/tap behaviour through the same ProtocolAdapter interface
as the NMEA bus, so the tester and detectors treat 'MAVLink' as just one bus
among several. The heavy lifting still lives in attacks/*.py and
tools/test_target.py's _mavlink_to_event(); this records the mapping so a
multi-bus run can describe every interface uniformly.
"""
from .base import ProtocolAdapter

# vector -> the standard MAVLink message used to inject it (vendor-independent).
INJECTION_MESSAGE = {
    "gps_spoof": "GPS_INPUT (#232)",
    "c2_replay": "SET_MODE / RC_CHANNELS_OVERRIDE",
    "acoustic_spoof": "VISION_POSITION_ESTIMATE (#102)",
}


class MavlinkAdapter(ProtocolAdapter):
    name = "mavlink"

    def encode(self, kind, **fields):
        msg = INJECTION_MESSAGE.get(kind)
        if not msg:
            raise ValueError(f"mavlink: no injection message mapped for '{kind}'")
        # Actual byte emission is done live by pymavlink in the attack modules;
        # here we return the descriptor a multi-bus plan/report uses.
        return {"bus": "mavlink", "message": msg, "fields": fields}

    def decode(self, msg_dict):
        """msg_dict is an already-parsed MAVLink message (.to_dict()); map the
        position-bearing ones to the believed_pos event shape."""
        import time
        mt = msg_dict.get("mavpackettype")
        if mt == "GLOBAL_POSITION_INT" and not (msg_dict.get("lat") == 0 and msg_dict.get("lon") == 0):
            return [{"type": "believed_pos", "t": time.time(),
                     "lat": msg_dict["lat"] / 1e7, "lon": msg_dict["lon"] / 1e7}]
        return []
