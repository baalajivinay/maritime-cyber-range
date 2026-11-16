import unittest
from scaleup.adversarial import (
    AttackerPolicy,
    DefenderPolicy,
    StatisticalDefenseFilter,
    AdversarialEnvironment,
    AdversarialTournament,
)


class TestAdversarialEngine(unittest.TestCase):
    def test_attacker_policy_generates_drift(self):
        att = AttackerPolicy(drift_rate_mps=0.5, onset_delay_s=5.0, bearing_deg=90.0, jitter_sigma_m=0.0)
        # Before onset -> 0 offset
        off_n, off_e = att.generate_offset(2.0)
        self.assertEqual(off_n, 0.0)
        self.assertEqual(off_e, 0.0)
        # At t=15s (10s after onset) -> 5.0m east
        off_n, off_e = att.generate_offset(15.0)
        self.assertAlmostEqual(off_n, 0.0, places=4)
        self.assertAlmostEqual(off_e, 5.0, places=4)

    def test_defender_cusum_catches_stealthy_drift(self):
        # Attacker drifts slowly at 0.2 m/s (below a static 0.3 m/s gate)
        att = AttackerPolicy(drift_rate_mps=0.2, onset_delay_s=0.0, jitter_sigma_m=0.0)
        def_pol = DefenderPolicy(cusum_slack_mps=0.08, cusum_threshold_m=3.0)
        env = AdversarialEnvironment(duration_s=40.0, dt_s=0.2, wave_noise_sigma=0.01)
        res = env.simulate(att, def_pol)
        self.assertTrue(res["detected"])
        self.assertIn("CUSUM anomaly", res["det_reason"])

    def test_defender_baseline_false_alarm_bounded(self):
        # On a clean run with realistic ocean wave jitter, false alarm rate should be 0
        def_pol = DefenderPolicy(cusum_slack_mps=0.15, cusum_threshold_m=6.0)
        env = AdversarialEnvironment(duration_s=60.0, dt_s=0.2, wave_noise_sigma=0.05)
        res = env.simulate(None, def_pol)
        self.assertFalse(res["detected"])

    def test_tournament_runs_and_improves(self):
        env = AdversarialEnvironment(duration_s=25.0, dt_s=0.5)
        tournament = AdversarialTournament(env)
        results = tournament.run_coevolution(rounds=3, population_size=4)
        self.assertEqual(results["rounds_completed"], 3)
        self.assertIn("best_attacker", results)
        self.assertIn("best_defender", results)
        self.assertTrue(results["best_attacker"].drift_rate_mps > 0)


if __name__ == "__main__":
    unittest.main()
