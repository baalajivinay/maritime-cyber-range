import unittest
import time
from detection.detectors import (
    CusumDriftDetector,
    KinematicConsistencyDetector,
    DetectorSuite,
    Alert
)


class TestStatisticalDetectors(unittest.TestCase):
    def test_cusum_drift_detector_triggers_on_sustained_walkoff(self):
        det = CusumDriftDetector(slack_mps=0.15, threshold_m=4.0)
        t = 0.0
        n, e = 0.0, 0.0
        alerts = []
        # Walk off at 0.35 m/s in North direction for 30s
        for _ in range(150):
            t += 0.2
            n += 0.35 * 0.2
            evt = {"type": "local_pos", "t": t, "n": n, "e": e, "vx": 0.0, "vy": 0.0, "domain": "surface"}
            alert = det.update(evt)
            if alert:
                alerts.append(alert)
        self.assertGreaterEqual(len(alerts), 1)
        self.assertEqual(alerts[0].detector, "CusumDriftDetector")
        self.assertEqual(alerts[0].attack_type, "gps_spoof")

    def test_cusum_detector_rejects_wave_noise(self):
        import random
        random.seed(42)
        det = CusumDriftDetector(slack_mps=0.15, threshold_m=4.0)
        t = 0.0
        alerts = []
        # Zero-mean wave noise with 0.05m sigma
        for _ in range(150):
            t += 0.2
            n = random.gauss(0, 0.05)
            e = random.gauss(0, 0.05)
            evt = {"type": "local_pos", "t": t, "n": n, "e": e, "vx": 0.0, "vy": 0.0, "domain": "surface"}
            alert = det.update(evt)
            if alert:
                alerts.append(alert)
        self.assertEqual(len(alerts), 0)

    def test_kinematic_consistency_detector(self):
        det = KinematicConsistencyDetector(speed_discrepancy_mps=1.0)
        t = 0.0
        # Position moving at 2.5 m/s while INS speed is 0.0 m/s
        evt1 = {"type": "local_pos", "t": t, "n": 0.0, "e": 0.0, "vx": 0.0, "vy": 0.0}
        det.update(evt1)
        t += 0.5
        evt2 = {"type": "local_pos", "t": t, "n": 1.25, "e": 0.0, "vx": 0.0, "vy": 0.0}
        alert = det.update(evt2)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.detector, "KinematicConsistencyDetector")

    def test_detector_suite_surface_and_underwater(self):
        suite_s = DetectorSuite("surface")
        self.assertTrue(any(d.__class__.__name__ == "CusumDriftDetector" for d in suite_s.detectors))
        suite_u = DetectorSuite("underwater")
        self.assertTrue(any(d.__class__.__name__ == "CusumDriftDetector" for d in suite_u.detectors))


if __name__ == "__main__":
    unittest.main()
