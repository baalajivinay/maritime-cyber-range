"""
Unit tests for the OT protocol tampering engine (``attacks/ot_protocols.py``):
NMEA 0183 depth/heading/STW spoofing, Radar/ARPA false targets, and J1939
engine CAN sabotage with governor limp mode. Qt-free.
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for p in (REPO, os.path.join(REPO, "attacks")):
    if p not in sys.path:
        sys.path.insert(0, p)

import ot_protocols as ot
from ot_protocols import OTProtocolEngine, nmea_checksum, VALID, CORRUPTED, UNAUTHENTICATED


BASE_STATE = {
    "depth": 6.0, "hdg": 90.0, "speed_knots": 12.0, "throttle_pct": 70.0,
    "altitude": 34.0, "east_m": 0.0, "north_m": 0.0,
}


class TestNMEA(unittest.TestCase):
    def test_checksum_roundtrip(self):
        s = ot.hehdt_sentence(123.4)
        self.assertTrue(s.startswith("$HEHDT,"))
        body, cs = s[1:].split("*")
        self.assertEqual(nmea_checksum(body), cs)

    def test_depth_sentences_formats(self):
        self.assertIn("SDDPT", ot.ddpt_sentence(12.3))
        self.assertIn("SDDBT", ot.ddbt_sentence(12.3))

    def test_corrupt_checksum_is_wrong(self):
        good = ot.build_nmea("SDDPT,10.0,0.0", corrupt_checksum=False)
        bad = ot.build_nmea("SDDPT,10.0,0.0", corrupt_checksum=True)
        self.assertNotEqual(good.split("*")[1], bad.split("*")[1])


class TestTampering(unittest.TestCase):
    def setUp(self):
        self.e = OTProtocolEngine()

    def test_baseline_all_valid(self):
        self.e.update(0.1, BASE_STATE)
        self.assertFalse(self.e.any_active())
        self.assertTrue(all(f.verdict == VALID and not f.is_anomaly for f in self.e.frames()))

    def test_depth_spoof_reports_false_deep_water(self):
        self.e.set_attack("depth_spoof", True)
        self.e.update(0.1, dict(BASE_STATE, depth=3.0))
        depth_frames = [f for f in self.e.frames() if "SDDPT" in f.payload or "SDDBT" in f.payload]
        self.assertTrue(depth_frames)
        self.assertTrue(all(f.is_anomaly for f in depth_frames))
        # The forged depth (45 m) must appear, not the true shallow 3 m
        self.assertTrue(any("45.0" in f.payload for f in depth_frames))
        self.assertIn(UNAUTHENTICATED, {f.verdict for f in depth_frames})

    def test_heading_spoof_biases_gyro(self):
        self.e.set_attack("heading_spoof", True)
        self.e.update(0.1, dict(BASE_STATE, hdg=90.0))
        hdt = [f for f in self.e.frames() if "HEHDT" in f.payload][0]
        self.assertEqual(hdt.verdict, CORRUPTED)
        # 90 + 18 bias = 108
        self.assertIn("108", hdt.payload)

    def test_stw_spoof_underreports(self):
        self.e.set_attack("stw_spoof", True)
        self.e.update(0.1, dict(BASE_STATE, speed_knots=12.0))
        vhw = [f for f in self.e.frames() if "VHW" in f.payload][0]
        self.assertTrue(vhw.is_anomaly)
        self.assertIn("10.0", vhw.payload)  # 12 - 2


class TestEngineSabotage(unittest.TestCase):
    def test_limp_mode_trips_on_overheat(self):
        e = OTProtocolEngine()
        e.set_attack("engine_sabotage", True)
        ov = {}
        for _ in range(200):  # 20 s at dt=0.1
            ov = e.update(0.1, BASE_STATE)
        self.assertTrue(ov["engine_overheat"])
        self.assertTrue(ov["engine_limp_mode"])
        self.assertGreaterEqual(ov["coolant_c"], ot.COOLANT_LIMP_C)
        # Limp mode clamps RPM
        self.assertLessEqual(ov["engine_rpm"], 900.0 + 1e-6)
        # J1939 frames tagged as tampered
        verdicts = {f.verdict for f in e.frames() if "J1939" in f.proto}
        self.assertTrue(verdicts & {CORRUPTED, UNAUTHENTICATED})

    def test_nominal_engine_stays_cool(self):
        e = OTProtocolEngine()
        ov = {}
        for _ in range(50):
            ov = e.update(0.1, BASE_STATE)
        self.assertFalse(ov["engine_limp_mode"])
        self.assertLess(ov["coolant_c"], ot.COOLANT_ALARM_C)


class TestRadarARPA(unittest.TestCase):
    def test_false_targets_generated_and_move(self):
        e = OTProtocolEngine()
        e.set_attack("arpa_false_targets", True)
        e.update(0.1, BASE_STATE)
        t0 = {t.track_id: (t.east_m, t.north_m) for t in e.radar_targets()}
        self.assertGreaterEqual(len(t0), 3)
        self.assertTrue(all(t.synthetic for t in e.radar_targets()))
        for _ in range(20):
            e.update(0.1, BASE_STATE)
        t1 = {t.track_id: (t.east_m, t.north_m) for t in e.radar_targets()}
        # At least one blip moved along its vector
        self.assertTrue(any(t0[k] != t1[k] for k in t0))

    def test_clear_removes_targets(self):
        e = OTProtocolEngine()
        e.set_attack("arpa_false_targets", True)
        e.update(0.1, BASE_STATE)
        e.clear()
        self.assertEqual(e.radar_targets(), [])
        self.assertFalse(e.any_active())


if __name__ == "__main__":
    unittest.main()
