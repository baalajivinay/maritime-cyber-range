"""Offline unit tests for the scenario engine -- no live sim, no Docker.
Run:  python3 scaleup/tests/test_scenario.py     (or: python3 -m unittest)
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from scaleup.scenario import geo, load_scenario, run_scenario, SimExecutor
from scaleup.scenario.model import Hazard, Contact
from scaleup.scenario import consequences as C


class TestGeo(unittest.TestCase):
    def test_horiz_m(self):
        # 0.001 deg lat ~= 111.3 m
        self.assertAlmostEqual(geo.horiz_m(0, 0, 0.001, 0), 111.32, places=1)

    def test_point_in_polygon(self):
        sq = [[0, 0], [0, 1], [1, 1], [1, 0]]
        self.assertTrue(geo.point_in_polygon(0.5, 0.5, sq))
        self.assertFalse(geo.point_in_polygon(2.0, 2.0, sq))


class TestConsequences(unittest.TestCase):
    def _telemetry_south_drift(self, meters, n=50):
        # believed holds at origin; true drifts `meters` south over the run
        out = []
        for i in range(n):
            frac = i / (n - 1)
            tlat, tlon = geo.offset_m(0.0, 0.0, -meters * frac, 0.0)
            out.append({"t": float(i), "true_lat": tlat, "true_lon": tlon,
                        "believed_lat": 0.0, "believed_lon": 0.0, "armed": True})
        return out

    def test_position_divergence_trips_and_not(self):
        tel = self._telemetry_south_drift(90)
        self.assertTrue(C.position_divergence(tel, 50, "high").triggered)
        self.assertFalse(C.position_divergence(tel, 200, "high").triggered)

    def test_grounding(self):
        tel = self._telemetry_south_drift(90)
        shoal = Hazard(type="shoal", name="rock", point=geo.offset_m(0, 0, -80, 0), radius_m=20)
        r = C.grounding(tel, shoal, "critical")
        self.assertTrue(r.triggered)
        self.assertLessEqual(r.metric, 20)

    def test_nogo_breach(self):
        tel = self._telemetry_south_drift(90)
        a = geo.offset_m(0, 0, -40, -30); b = geo.offset_m(0, 0, -40, 30)
        c = geo.offset_m(0, 0, -120, 30); d = geo.offset_m(0, 0, -120, -30)
        zone = Hazard(type="nogo_zone", name="z",
                      polygon=[[a[0], a[1]], [b[0], b[1]], [c[0], c[1]], [d[0], d[1]]])
        self.assertTrue(C.nogo_breach(tel, zone, "critical").triggered)

    def test_cpa(self):
        tel = self._telemetry_south_drift(90)
        # stationary contact right on the drift path -> small CPA
        contact = Contact(name="x", start=list(geo.offset_m(0, 0, -45, 0)), velocity_ne_mps=[0, 0])
        r = C.cpa_violation(tel, contact, threshold_m=50, severity="critical")
        self.assertTrue(r.triggered)


class TestEndToEnd(unittest.TestCase):
    def test_example_scenario_is_critical(self):
        path = os.path.join(REPO, "scenarios", "harbor_transit_gps_walkoff.json")
        sc = load_scenario(path)
        res = run_scenario(sc, SimExecutor())
        self.assertEqual(res.overall_severity, "critical")
        self.assertTrue(all(r.triggered for r in res.results),
                        "every declared consequence should trigger in this scenario")


if __name__ == "__main__":
    unittest.main(verbosity=2)
