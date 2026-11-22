"""
Unit tests for harbor traffic + multi-contact COLREGS (Task 5). Qt-free.
"""
import os
import sys
import math
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for p in (REPO, os.path.join(REPO, "application")):
    if p not in sys.path:
        sys.path.insert(0, p)

from scaleup.physics.harbor_traffic import (
    HarborTrafficSim, TrafficVessel, evaluate_colregs, classify_encounter,
    relative_bearing, cpa_tcpa, SITE_TSS, SAFE_CPA_M,
)


class TestTrafficSim(unittest.TestCase):
    def test_vessel_count_bounds(self):
        for n in (3, 6, 12):
            sim = HarborTrafficSim("kochi", n_vessels=n)
            self.assertGreaterEqual(len(sim.vessels), 5)
            self.assertLessEqual(len(sim.vessels), 8)

    def test_all_sites_spawn(self):
        for site in SITE_TSS:
            sim = HarborTrafficSim(site)
            self.assertTrue(sim.vessels)
            self.assertTrue(all(v.speed_mps > 0 for v in sim.vessels))

    def test_vessels_move_and_recycle(self):
        sim = HarborTrafficSim("mumbai", seed=3)
        before = [(v.east_m, v.north_m) for v in sim.vessels]
        for _ in range(100):
            sim.step(0.5)
        after = [(v.east_m, v.north_m) for v in sim.vessels]
        self.assertTrue(any(b != a for b, a in zip(before, after)))
        # None should drift beyond the recycle horizon
        span = SITE_TSS["mumbai"]["span_m"] * 1.2
        self.assertTrue(all(math.hypot(v.east_m, v.north_m) <= span for v in sim.vessels))

    def test_ais_and_radar_tracks(self):
        sim = HarborTrafficSim("kochi")
        ais = sim.ais_tracks()
        radar = sim.radar_tracks()
        self.assertEqual(len(ais), len(sim.vessels))
        self.assertTrue(all(not t["synthetic"] for t in radar))


class TestCPAGeometry(unittest.TestCase):
    def test_relative_bearing_starboard(self):
        # Own heading north (0 deg); target due east -> +90 (starboard)
        rel = relative_bearing(0.0, (0.0, 0.0), (100.0, 0.0))
        self.assertAlmostEqual(rel, 90.0, places=1)

    def test_cpa_head_on_zero(self):
        # Two vessels closing head-on on the same line -> CPA ~ 0
        cpa, tcpa = cpa_tcpa((0.0, 0.0), (0.0, 5.0), (0.0, 500.0), (0.0, -5.0))
        self.assertLess(cpa, 1.0)
        self.assertGreater(tcpa, 0.0)


class TestColregsRules(unittest.TestCase):
    def _own(self):
        return (0.0, 0.0), 0.0, 5.0   # at origin, heading N, 5 m/s

    def test_crossing_give_way_starboard(self):
        # Target on starboard bow crossing left-to-right on collision course
        pos, hdg, spd = self._own()
        tgt = TrafficVessel(1, "X", "cargo", east_m=200.0, north_m=200.0,
                            course_deg=270.0, speed_mps=5.0, lane=0)
        enc = classify_encounter(hdg, pos, tgt)
        self.assertEqual(enc, "crossing_give_way")
        d = evaluate_colregs(pos, hdg, spd, [tgt])
        self.assertEqual(d.action, "give_way")
        self.assertIn("Rule 15", d.rule)
        self.assertGreater(d.course_change_deg, 0.0)

    def test_head_on_both_starboard(self):
        pos, hdg, spd = self._own()
        tgt = TrafficVessel(2, "Y", "tanker", east_m=0.0, north_m=300.0,
                            course_deg=180.0, speed_mps=5.0, lane=1)
        self.assertEqual(classify_encounter(hdg, pos, tgt), "head_on")
        d = evaluate_colregs(pos, hdg, spd, [tgt])
        self.assertEqual(d.action, "give_way")
        self.assertIn("Rule 14", d.rule)

    def test_port_crossing_stand_on(self):
        pos, hdg, spd = self._own()
        # Target on port bow -> own-ship stands on (Rule 17)
        tgt = TrafficVessel(3, "Z", "ferry", east_m=-200.0, north_m=200.0,
                            course_deg=90.0, speed_mps=5.0, lane=0)
        self.assertEqual(classify_encounter(hdg, pos, tgt), "crossing_stand_on")
        d = evaluate_colregs(pos, hdg, spd, [tgt])
        self.assertIn(d.action, ("stand_on", "alter"))

    def test_multi_contact_give_way_dominates(self):
        pos, hdg, spd = self._own()
        stand_on = TrafficVessel(10, "P", "ferry", east_m=-180.0, north_m=150.0,
                                 course_deg=90.0, speed_mps=5.0, lane=0)
        give_way = TrafficVessel(11, "S", "cargo", east_m=160.0, north_m=150.0,
                                 course_deg=270.0, speed_mps=5.0, lane=1)
        d = evaluate_colregs(pos, hdg, spd, [stand_on, give_way])
        self.assertEqual(d.risk_count, 2)
        # Give-way obligation must dominate
        self.assertEqual(d.action, "give_way")
        self.assertEqual(d.worst_mmsi, 11)

    def test_no_risk_when_diverging(self):
        pos, hdg, spd = self._own()
        tgt = TrafficVessel(4, "D", "cargo", east_m=600.0, north_m=0.0,
                            course_deg=90.0, speed_mps=6.0, lane=0)  # moving away
        d = evaluate_colregs(pos, hdg, spd, [tgt])
        self.assertEqual(d.action, "maintain")
        self.assertEqual(d.risk_count, 0)


if __name__ == "__main__":
    unittest.main()
