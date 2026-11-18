"""ArduPilot backend -- the firmware this range was built on. Wraps the
behaviour that already exists (tools/run_sim.sh boots it; attacks/*.py inject)
behind the generic VehicleBackend interface so nothing downstream has to special-
case ArduPilot."""
from .base import (VehicleBackend, InjectionSpec,
                   GPS_SPOOF, AIS_SPOOF, C2_REPLAY, ACOUSTIC_SPOOF)


def backend():
    return VehicleBackend(
        name="ardupilot",
        firmware="ArduPilot",
        domains=("surface", "underwater"),
        vectors={
            GPS_SPOOF: InjectionSpec("fdm_json", "SITL JSON position[]",
                                     "zero-setup, ArduPilot-specific FDM relay (attacks/gps_spoof.py); "
                                     "GPS_INPUT #232 path also available for hardened GPS1_TYPE=14 twins"),
            C2_REPLAY: InjectionSpec("mavlink", "SET_MODE / RC_CHANNELS_OVERRIDE",
                                     "unauthenticated MAVLink command authority"),
            ACOUSTIC_SPOOF: InjectionSpec("mavlink", "VISION_POSITION_ESTIMATE #102",
                                          "ExternalNav/USBL feed for submerged AUV (ArduSub EK3_SRC1=ExternalNav)"),
            AIS_SPOOF: InjectionSpec("udp_nmea", "AIVDM",
                                     "ECDIS/operator-layer; N/A to the autopilot itself"),
        },
        endpoints={
            "gcs": "udpin:127.0.0.1:14551",
            "tester": "udpin:127.0.0.1:14554",
            "c2": "udpin:127.0.0.1:14553",
            "acoustic": "tcp:127.0.0.1:5762",
        },
        live_boot="tools/run_sim.sh <profile> up  (Gazebo -> FDM relay -> ArduPilot SITL -> mav_bridge)",
    )
