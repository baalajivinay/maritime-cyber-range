import unittest
try:
    from communication.ais_emulator.ais_avoidance import AisAvoidanceEngine, calculate_cpa_tcpa
except ImportError:
    from ais_emulator.ais_avoidance import AisAvoidanceEngine, calculate_cpa_tcpa



class TestAisAvoidance(unittest.TestCase):
    def test_cpa_tcpa_head_on(self):
        # Two vessels approaching head-on on East-West axis:
        # Own vessel at (0, 0) moving East at 2 m/s
        # Target at (0, 200) moving West at 2 m/s
        dcpa, tcpa = calculate_cpa_tcpa(
            own_n=0.0, own_e=0.0, own_vn=0.0, own_ve=2.0,
            tgt_n=0.0, tgt_e=200.0, tgt_vn=0.0, tgt_ve=-2.0
        )
        self.assertAlmostEqual(dcpa, 0.0, places=2)
        self.assertAlmostEqual(tcpa, 50.0, places=2)

    def test_ais_ghost_vessel_triggers_colregs_rule14_starboard_turn(self):
        engine = AisAvoidanceEngine(cpa_safety_radius_m=120.0, tcpa_horizon_s=60.0, evasion_course_delta_deg=30.0)
        own_lat = 9.9000
        own_lon = 76.2000
        # Target positioned directly ahead (Head-on) at distance ~200m North, heading South
        tgt_lat = own_lat + (200.0 / 111320.0)
        tgt_lon = own_lon
        engine.update_target_ais(mmsi="999000123", lat=tgt_lat, lon=tgt_lon, speed_mps=2.0, course_deg=180.0)

        res = engine.evaluate_threats(own_lat, own_lon, own_speed_mps=2.0, own_course_deg=0.0)
        self.assertTrue(res["evasion_active"])
        self.assertEqual(res["threat_mmsi"], "999000123")
        self.assertEqual(res["colregs_rule"], "Rule 14 (Head-on)")
        self.assertEqual(res["commanded_course_delta_deg"], 30.0)
        self.assertEqual(res["commanded_heading_deg"], 30.0)

    def test_distant_ais_target_safe(self):
        engine = AisAvoidanceEngine(cpa_safety_radius_m=100.0, tcpa_horizon_s=30.0)
        own_lat = 9.9000
        own_lon = 76.2000
        # Target 2 km away, moving parallel
        tgt_lat = own_lat + (2000.0 / 111320.0)
        tgt_lon = own_lon + (2000.0 / 111320.0)
        engine.update_target_ais(mmsi="419000555", lat=tgt_lat, lon=tgt_lon, speed_mps=1.0, course_deg=90.0)

        res = engine.evaluate_threats(own_lat, own_lon, own_speed_mps=1.5, own_course_deg=90.0)
        self.assertFalse(res["evasion_active"])
        self.assertEqual(res["commanded_course_delta_deg"], 0.0)


if __name__ == "__main__":
    unittest.main()
