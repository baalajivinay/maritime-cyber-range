"""Offline tests: the ocean-physics formulas (vs published reference values),
site loading, and that the water current actually changes a scenario outcome.
Run:  python3 scaleup/tests/test_sites.py
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from scaleup.sites import oceanography as O
from scaleup.sites import load_site, list_sites
from scaleup.scenario import load_scenario, run_scenario, SimExecutor
from scaleup.scenario.model import apply_site


class TestPhysics(unittest.TestCase):
    def test_mackenzie_paper_check(self):
        # the Mackenzie (1981) paper's own documented value
        self.assertAlmostEqual(O.sound_speed_mackenzie(25, 35, 1000), 1550.744, places=2)

    def test_eos80_density_reference(self):
        self.assertAlmostEqual(O.density_eos80(25, 35), 1023.343, places=2)
        self.assertAlmostEqual(O.density_eos80(0, 35), 1028.106, places=2)

    def test_absorption_monotonic(self):
        # higher frequency -> more absorption
        self.assertLess(O.thorp_absorption_db_per_km(10), O.thorp_absorption_db_per_km(50))

    def test_transmission_loss_increases_with_range(self):
        self.assertLess(O.transmission_loss_db(100, 25), O.transmission_loss_db(1000, 25))


class TestSites(unittest.TestCase):
    def test_three_sites_load(self):
        ids = {s.id for s in list_sites()}
        self.assertSetEqual(ids, {"kochi", "visakhapatnam", "mumbai"})

    def test_bay_of_bengal_is_fresher_and_lighter(self):
        # Visakhapatnam (Bay of Bengal, river-freshened) must be LESS dense than
        # Kochi/Mumbai (Arabian Sea, saltier) -- a real, cited physical difference.
        rho = {s.id: s.density() for s in list_sites()}
        self.assertLess(rho["visakhapatnam"], rho["kochi"])
        self.assertLess(rho["visakhapatnam"], rho["mumbai"])

    def test_profile_and_derived_fields(self):
        k = load_site("kochi")
        prof = k.sound_speed_profile()
        self.assertGreater(len(prof), 10)
        self.assertIsNotNone(k.sonic_layer_depth())
        self.assertGreater(k.usbl_detection_range(), 0)


class TestSiteAffectsOutcome(unittest.TestCase):
    def test_current_changes_the_track(self):
        # Same scenario at two sites with different currents must produce a
        # different peak divergence (the water advects the hull).
        path = os.path.join(REPO, "scenarios", "harbor_transit_gps_walkoff.json")
        peaks = {}
        for site_id in ("kochi", "mumbai"):
            sc = load_scenario(path)
            apply_site(sc, load_site(site_id))
            res = run_scenario(sc, SimExecutor())
            peaks[site_id] = res.telemetry_summary["peak_divergence_m"]
        self.assertNotAlmostEqual(peaks["kochi"], peaks["mumbai"], places=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
