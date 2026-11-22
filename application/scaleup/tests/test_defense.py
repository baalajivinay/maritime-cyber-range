"""
Unit tests for the Autonomous Defense & Failover Autopilot (Task 3):
sensor-fusion failover, COLREGS phantom-AIS verification gate, and failsafe
actuator quarantine / loiter. Qt-free.
"""
import os
import sys
import math
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for p in (REPO, os.path.join(REPO, "application"), os.path.join(REPO, "attacks")):
    if p not in sys.path:
        sys.path.insert(0, p)

from detection.defense import DefenseController, RADAR_CORRELATION_M
from scaleup.physics.marine_dynamics import MarineDynamicsEngine


class TestSensorFailover(unittest.TestCase):
    def test_gnss_isolation_on_high_innovation(self):
        d = DefenseController(innovation_gate=3.5, enabled=True)
        overlay = {"active_attack": "gps_spoof", "simulated_innovation": 5.0}
        directive = d.update(0.1, {"domain": "surface"}, overlay, [])
        self.assertTrue(directive.gnss_isolated)
        self.assertIn("GNSS ISOLATED", directive.banner)
        self.assertIn("DVL", directive.nav_source)
        # Event emitted exactly once on the transition
        self.assertTrue(any("isolating" in m for _, m in directive.new_events))
        d2 = d.update(0.1, {"domain": "surface"}, overlay, [])
        self.assertEqual(d2.new_events, [])  # latched, no duplicate log

    def test_no_isolation_below_gate(self):
        d = DefenseController(innovation_gate=3.5, enabled=True)
        overlay = {"active_attack": "gps_spoof", "simulated_innovation": 1.2}
        directive = d.update(0.1, {"domain": "surface"}, overlay, [])
        self.assertFalse(directive.gnss_isolated)

    def test_underwater_acoustic_failover(self):
        d = DefenseController(enabled=True)
        overlay = {"active_attack": "acoustic_spoof", "simulated_innovation": 6.0}
        directive = d.update(0.1, {"domain": "underwater"}, overlay, [])
        self.assertTrue(directive.gnss_isolated)
        self.assertIn("USBL", directive.nav_source)

    def test_reset_clears_latch(self):
        d = DefenseController(enabled=True)
        d.update(0.1, {"domain": "surface"}, {"active_attack": "gps_spoof", "simulated_innovation": 9.0}, [])
        d.update(0.1, {"domain": "surface"}, {"active_attack": None, "simulated_innovation": 0.0}, [])
        directive = d.update(0.1, {"domain": "surface"}, {"active_attack": None, "simulated_innovation": 0.0}, [])
        self.assertFalse(directive.gnss_isolated)


class TestColregsGate(unittest.TestCase):
    def test_phantom_ais_suppresses_evasion(self):
        d = DefenseController(enabled=True)
        overlay = {
            "active_attack": "ais_spoof",
            "simulated_innovation": 1.0,
            "ghost_vessel": {"pos": (300.0, 200.0)},
        }
        directive = d.update(0.1, {"domain": "surface"}, overlay, radar_tracks=[])
        self.assertTrue(directive.ais_phantom)
        self.assertTrue(directive.suppress_ais_evasion)
        self.assertTrue(any(cat == "IEC62320-1" for cat, _ in directive.new_events))

    def test_synthetic_radar_does_not_corroborate(self):
        d = DefenseController(enabled=True)
        overlay = {"active_attack": "ais_spoof", "simulated_innovation": 1.0,
                   "ghost_vessel": {"pos": (300.0, 200.0)}}
        # A synthetic ARPA blip right on top of the ghost must NOT validate it
        tracks = [{"east_m": 300.0, "north_m": 200.0, "synthetic": True}]
        directive = d.update(0.1, {"domain": "surface"}, overlay, tracks)
        self.assertTrue(directive.suppress_ais_evasion)

    def test_real_radar_contact_authorises_evasion(self):
        d = DefenseController(enabled=True)
        overlay = {"active_attack": "ais_spoof", "simulated_innovation": 1.0,
                   "ghost_vessel": {"pos": (300.0, 200.0)}}
        tracks = [{"east_m": 310.0, "north_m": 205.0, "synthetic": False}]
        directive = d.update(0.1, {"domain": "surface"}, overlay, tracks)
        self.assertFalse(directive.suppress_ais_evasion)
        self.assertFalse(directive.ais_phantom)


class TestActuatorQuarantine(unittest.TestCase):
    def test_c2_triggers_loiter(self):
        d = DefenseController(enabled=True)
        overlay = {"active_attack": "c2_replay", "simulated_innovation": 1.0}
        directive = d.update(0.1, {"domain": "surface"}, overlay, [])
        self.assertTrue(directive.actuator_quarantine)
        self.assertTrue(directive.loiter)
        self.assertIn("LOITER", directive.banner)


class TestPhysicsHonoursDirective(unittest.TestCase):
    def test_loiter_overrides_hijack(self):
        phys = MarineDynamicsEngine("interceptor_usv", "kochi")
        phys.armed = True
        # Without defense, c2 hijack forces full throttle hard-over
        phys.step(0.1, active_attack="c2_replay")
        self.assertEqual(phys.mode, "MANUAL_HIJACKED")
        # With quarantine directive, autopilot loiters instead
        phys.step(0.1, active_attack="c2_replay",
                  defense={"actuator_quarantine": True, "loiter": True})
        self.assertEqual(phys.mode, "DEFENSE_LOITER")
        self.assertLess(phys.throttle_pct, 50.0)

    def test_suppress_ais_holds_course(self):
        phys = MarineDynamicsEngine("interceptor_usv", "kochi")
        phys.armed = True
        phys.set_target_waypoint(0.0, 500.0)
        phys.step(0.1, active_attack="ais_spoof",
                  defense={"suppress_ais_evasion": True})
        # Should fall through to guided LOS, not the Rule-14 evasion mode
        self.assertNotIn("EVASION", phys.mode)


if __name__ == "__main__":
    unittest.main()
