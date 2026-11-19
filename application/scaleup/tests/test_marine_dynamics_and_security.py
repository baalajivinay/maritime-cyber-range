"""
Tests for MarineDynamicsEngine (Fossen 3-DOF/6-DOF physics) and SecureTelemetryChannel (IACS UR E26 / MAVLink 2 signing).
"""
import pytest
from scaleup.physics.marine_dynamics import MarineDynamicsEngine, VESSEL_PHYSICS_PRESETS
from communication.secure_protocol import MAVLink2Signer, AISAuthenticator, ReplayProtectionWindow, SecureTelemetryChannel


def test_marine_dynamics_presets_exist():
    twins = ["interceptor_usv", "survey_usv", "mt_andaman_tug", "maya_auv", "auv150"]
    for t in twins:
        assert t in VESSEL_PHYSICS_PRESETS
        cfg = VESSEL_PHYSICS_PRESETS[t]
        assert cfg["mass_kg"] > 0
        assert cfg["max_speed_mps"] > 0
        assert cfg["domain"] in ("surface", "underwater")


def test_marine_dynamics_step_and_waypoint():
    eng = MarineDynamicsEngine("interceptor_usv", "kochi")
    eng.armed = True
    eng.set_target_waypoint(100.0, 100.0)
    for _ in range(30):
        state = eng.step(0.1)

    assert state["speed"] > 0.0
    assert state["armed"] is True
    assert "lat" in state and "lon" in state
    assert "rudder_angle" in state
    assert state["domain"] == "surface"


def test_auv_depth_dynamics():
    eng = MarineDynamicsEngine("maya_auv", "kochi")
    eng.armed = True
    state = eng.step(0.1)
    assert state["domain"] == "underwater"
    assert state["depth"] > 0.0
    assert state["altitude"] > 0.0


def test_c2_override_forces_maneuver():
    eng = MarineDynamicsEngine("survey_usv", "mumbai")
    eng.armed = True
    for _ in range(15):
        state = eng.step(0.1, active_attack="c2_override")

    assert state["mode"] == "MANUAL_HIJACKED"
    assert state["rudder_cmd"] > 20.0  # Rudder commanded hard over


def test_mavlink2_signing_and_anti_replay():
    signer = MAVLink2Signer()
    raw = b"\xfd\x0c\x00\x00\x00\x01\x01\x1e\x00\x00\xaa\xbb\xcc\xdd"
    signed = signer.sign_packet(raw)
    ok, reason, payload = signer.verify_packet(signed)
    assert ok is True
    assert payload == raw

    # Replay of exact packet must be rejected
    ok2, reason2, _ = signer.verify_packet(signed)
    assert ok2 is False
    assert "REPLAY" in reason2


def test_ais_transponder_authenticator():
    ais = AISAuthenticator()
    ok, _ = ais.verify_ais_transmission("419000234", "!AIVDM,1,1,,A,15N7v80P00IS?1rM7nUa?wp00000,0*1E")
    assert ok is True
    ok_ghost, reason_ghost = ais.verify_ais_transmission("999999999", "!AIVDM,1,1,,A,15N7v80P00IS?1rM7nUa?wp00000,0*1E")
    assert ok_ghost is False
