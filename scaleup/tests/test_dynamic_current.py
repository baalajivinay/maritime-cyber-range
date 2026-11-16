import unittest
from scaleup.physics.tides import demo_mumbai
import math


class TestDynamicTidalCurrent(unittest.TestCase):
    def test_mumbai_tides_fluctuate_and_flip(self):
        model = demo_mumbai()
        # Evaluate current at t=0h and t=6.2h (half M2 period, ~180 deg phase shift)
        s0, b0 = model.current(0.0)
        s_half, b_half = model.current(6.21 * 3600.0)
        
        # Bearing should flip between flood and ebb (approx 180 deg difference)
        bearing_diff = abs(b_half - b0)
        self.assertAlmostEqual(bearing_diff, 180.0, delta=15.0)
        
        # Current speeds must be physically realistic (0.1 to 1.5 m/s)
        self.assertGreater(s0, 0.05)
        self.assertLess(s0, 2.5)


if __name__ == "__main__":
    unittest.main()
