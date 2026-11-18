"""PX4 backend (Axis 1.1) -- the second autopilot family, proving the range is
firmware-agnostic.

STATUS: interface + injection map are complete and used by the registry/tests.
LIVE BOOT requires a PX4 SITL install (px4_sitl + the Gazebo bridge), which is
NOT bundled in this repo -- so `live_boot` documents the command rather than the
range booting PX4 for you. The ATTACK PATH, however, is already real and shared
with ArduPilot's hardened path: PX4 ingests external position via the SAME
standard MAVLink messages the range forges today --

  * GPS:      GPS_INPUT (#232) / HIL_GPS (#113)  -- PX4's documented sim GPS API
  * ExtNav:   VISION_POSITION_ESTIMATE (#102) / ODOMETRY (#331)
  * C2:       COMMAND_LONG / SET_MODE / MANUAL_CONTROL

so attacks/gps_input_inject.py and the acoustic VISION_POSITION_ESTIMATE path in
tools/test_target.py apply to PX4 unchanged once a PX4 target.json points at a
running PX4 instance. That is the whole point of attacking the protocol, not the
vendor's internals.
"""
from .base import (VehicleBackend, InjectionSpec,
                   GPS_SPOOF, AIS_SPOOF, C2_REPLAY, ACOUSTIC_SPOOF)


def backend():
    return VehicleBackend(
        name="px4",
        firmware="PX4",
        domains=("surface", "underwater"),
        vectors={
            GPS_SPOOF: InjectionSpec("mavlink", "GPS_INPUT #232 / HIL_GPS #113",
                                     "PX4's official simulator GPS API -- autopilot-agnostic, works on real hardware too"),
            C2_REPLAY: InjectionSpec("mavlink", "COMMAND_LONG / SET_MODE / MANUAL_CONTROL",
                                     "unauthenticated MAVLink command authority"),
            ACOUSTIC_SPOOF: InjectionSpec("mavlink", "VISION_POSITION_ESTIMATE #102 / ODOMETRY #331",
                                          "EKF2 external vision/mocap input"),
            AIS_SPOOF: InjectionSpec("udp_nmea", "AIVDM", "ECDIS/operator-layer; N/A to the autopilot itself"),
        },
        endpoints={
            "gcs": "udpin:127.0.0.1:14550",     # PX4 default GCS port
            "tester": "udpin:127.0.0.1:14540",  # PX4 onboard/offboard
            "c2": "udpin:127.0.0.1:14558",
            "acoustic": "udpin:127.0.0.1:14560",
        },
        live_boot="(requires PX4 SITL) make px4_sitl gz_<model>  +  a PX4 target.json; "
                  "attacks use the standard GPS_INPUT/VISION_POSITION_ESTIMATE paths unchanged",
    )
