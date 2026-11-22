"""
Tests for ECDIS route planning + S-52 symbology + IEC 62288 palettes (Task 4).
Runs the Qt widgets headless (offscreen).
"""
import os
import sys
import math
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for p in (REPO, os.path.join(REPO, "application")):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from PyQt6.QtWidgets import QApplication
    _HAVE_QT = True
except Exception:  # pragma: no cover
    _HAVE_QT = False

if _HAVE_QT:
    from application.console.widgets.ecdis import ChartCanvas, PALETTES, default_s52_features


@unittest.skipUnless(_HAVE_QT, "PyQt6 not available")
class TestRoutePlanning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.c = ChartCanvas()
        self.c.true_pos = (0.0, 0.0)

    def test_append_and_active(self):
        self.c.append_route_wp(0.0, 100.0)
        self.c.append_route_wp(100.0, 100.0)
        self.assertEqual(len(self.c.route), 2)
        self.assertEqual(self.c.active_route_wp(), (0.0, 100.0))

    def test_leg_course_and_distance(self):
        self.c.append_route_wp(0.0, 100.0)    # due north, 100 m
        self.c.append_route_wp(100.0, 100.0)  # due east, 100 m
        legs = self.c.route_legs()
        self.assertAlmostEqual(legs[0]["dist_m"], 100.0, places=1)
        self.assertAlmostEqual(legs[0]["course_deg"], 0.0, places=1)
        self.assertAlmostEqual(legs[1]["dist_m"], 100.0, places=1)
        self.assertAlmostEqual(legs[1]["course_deg"], 90.0, places=1)

    def test_advance_and_complete(self):
        self.c.append_route_wp(0.0, 50.0)
        self.c.append_route_wp(0.0, 100.0)
        self.assertFalse(self.c.route_complete())
        self.assertEqual(self.c.advance_route(), (0.0, 100.0))
        self.assertIsNone(self.c.advance_route())
        self.assertTrue(self.c.route_complete())

    def test_turn_radius_only_intermediate(self):
        for wp in [(0, 50), (50, 50), (100, 50)]:
            self.c.append_route_wp(*wp)
        legs = self.c.route_legs()
        self.assertEqual(legs[0]["turn_r_m"], 0.0)       # first WP: no turn circle
        self.assertGreater(legs[1]["turn_r_m"], 0.0)     # middle WP: turn circle
        self.assertEqual(legs[2]["turn_r_m"], 0.0)       # last WP: no turn circle

    def test_clear_route(self):
        self.c.append_route_wp(0.0, 50.0)
        self.c.clear_waypoint()
        self.assertEqual(self.c.route, [])
        self.assertIsNone(self.c.target_wp)


@unittest.skipUnless(_HAVE_QT, "PyQt6 not available")
class TestPaletteAndSymbology(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_three_palettes(self):
        self.assertEqual(set(PALETTES), {"day", "dusk", "night"})
        c = ChartCanvas()
        for mode in ("day", "dusk", "night"):
            c.set_palette(mode)
            self.assertEqual(c.palette_mode, mode)
            self.assertEqual(c._pal, PALETTES[mode])
        # Night must be darker than day (lower background luminance)
        self.assertLess(PALETTES["night"]["water_deep"], PALETTES["day"]["water_deep"])

    def test_s52_feature_set(self):
        f = default_s52_features()
        self.assertTrue(any(c.get("safety") for c in f["depth_contours"]))
        kinds = {b["kind"] for b in f["buoys"]}
        self.assertEqual(kinds, {"port", "starboard"})
        self.assertTrue(f["cardinals"])
        self.assertTrue(f["lights"])


if __name__ == "__main__":
    unittest.main()
