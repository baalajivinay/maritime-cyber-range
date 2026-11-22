"""
Unit tests for the live multi-stage cyber campaign runner
(``attacks/scenario_runner.py``) and its resilience scoring. Qt-free.
"""
import os
import sys
import math
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for p in (REPO, os.path.join(REPO, "application"), os.path.join(REPO, "attacks")):
    if p not in sys.path:
        sys.path.insert(0, p)

from scenario_runner import (
    ScenarioRunner, load_scenario, list_scenarios, ResilienceScore, SCENARIO_DIR,
)
from advanced_attacks import AttackExecutionManager
from scaleup.physics.marine_dynamics import MarineDynamicsEngine


def _run_full(runner, dt=0.1):
    """Drive a scenario end-to-end through the real attack + physics engines."""
    attack_mgr = AttackExecutionManager()
    physics = MarineDynamicsEngine(runner.twin, runner.site)
    physics.armed = True
    runner.play()
    steps = int(runner.duration_s / dt) + 5
    for _ in range(steps):
        runner.step(dt, attack_mgr, physics)
        own_pos = (physics.east_m, physics.north_m)
        own_vel = (physics.u * math.sin(physics.psi), physics.u * math.cos(physics.psi))
        overlay = attack_mgr.update(dt, own_pos, own_vel)
        phys = physics.step(dt, active_attack=attack_mgr.active_attack, attack_params=attack_mgr.params)
        sample = dict(phys)
        sample.update({
            "simulated_innovation": overlay["simulated_innovation"],
            "collision_risk": overlay["collision_risk"],
            "cpa_m": overlay["cpa_m"],
            "active_attack": overlay["active_attack"],
        })
        runner.record(sample)
    return attack_mgr, physics


class TestScenarioDiscovery(unittest.TestCase):
    def test_both_scenarios_listed(self):
        ids = {m["id"] for m in list_scenarios(SCENARIO_DIR)}
        self.assertIn("malacca_port_approach_ambush", ids)
        self.assertIn("deep_subsea_auv_sabotage", ids)

    def test_load_by_id(self):
        sc = load_scenario("malacca_port_approach_ambush")
        self.assertEqual(sc["twin"], "interceptor_usv")
        self.assertEqual(len(sc["stages"]), 4)


class TestRunnerControl(unittest.TestCase):
    def setUp(self):
        self.runner = ScenarioRunner(load_scenario("malacca_port_approach_ambush"))

    def test_initial_state(self):
        self.assertEqual(self.runner.state, ScenarioRunner.STATE_IDLE)
        self.assertEqual(self.runner.elapsed_s, 0.0)

    def test_play_pause(self):
        am = AttackExecutionManager()
        self.runner.play()
        self.runner.step(1.0, am)
        self.assertGreater(self.runner.elapsed_s, 0.0)
        self.runner.pause()
        t = self.runner.elapsed_s
        self.runner.step(1.0, am)
        self.assertEqual(self.runner.elapsed_s, t)  # paused: no advance

    def test_seek_and_reset(self):
        self.runner.seek(50.0)
        self.assertAlmostEqual(self.runner.elapsed_s, 50.0)
        st = self.runner.active_stage
        self.assertEqual(st["attack"], "ais_spoof")  # stage 2 window 35-60
        self.runner.reset()
        self.assertEqual(self.runner.elapsed_s, 0.0)
        self.assertEqual(self.runner.state, ScenarioRunner.STATE_IDLE)

    def test_stage_sequence_drives_attacks(self):
        am = AttackExecutionManager()
        self.runner.play()
        # Stage 0 (t<15): no attack
        self.runner.seek(5.0); self.runner.step(0.1, am)
        self.assertIsNone(am.active_attack)
        # Stage 1: gps
        self.runner.seek(20.0); self.runner.step(0.1, am)
        self.assertEqual(am.active_attack, "gps_spoof")
        # Stage 2: ais
        self.runner.seek(40.0); self.runner.step(0.1, am)
        self.assertEqual(am.active_attack, "ais_spoof")
        # Stage 3: c2
        self.runner.seek(70.0); self.runner.step(0.1, am)
        self.assertEqual(am.active_attack, "c2_replay")
        # After end: cleared
        self.runner.seek(95.0); self.runner.step(0.1, am)
        self.assertIsNone(am.active_attack)


class TestResilienceScoring(unittest.TestCase):
    def test_malacca_scores(self):
        runner = ScenarioRunner(load_scenario("malacca_port_approach_ambush"))
        _run_full(runner)
        score = runner.score
        # Every attack stage must be detected
        self.assertEqual(score.detection_rate, 1.0)
        # TTD must be finite and reasonably prompt
        self.assertIsNotNone(score.mean_ttd_s)
        self.assertLess(score.mean_ttd_s, 20.0)
        # XTE accumulated
        self.assertGreater(score.max_xte_m, 0.0)
        # Grade is one of the defined bands
        self.assertRegex(score.grade(), r"^[ABCD] ")
        d = score.as_dict()
        self.assertIn("grade", d)
        self.assertEqual(len(d["stages"]), 4)

    def test_subsea_scores(self):
        runner = ScenarioRunner(load_scenario("deep_subsea_auv_sabotage"))
        _run_full(runner)
        # Acoustic stages detected via innovation growth
        self.assertGreaterEqual(runner.score.detection_rate, 0.5)
        self.assertIsNotNone(runner.score.as_dict())

    def test_cross_track_error_math(self):
        runner = ScenarioRunner(load_scenario("malacca_port_approach_ambush"))
        # Course 45 deg; a point 10 m perpendicular (to NW) off the track
        # Track dir (E,N) = (sin45, cos45). Perp offset of 10 m.
        perp_e = 10.0 * math.cos(math.radians(45.0))
        perp_n = -10.0 * math.sin(math.radians(45.0))
        xte = runner.cross_track_error(perp_e, perp_n)
        self.assertAlmostEqual(xte, 10.0, places=3)
        # On-track point has zero XTE
        on_e = 100.0 * math.sin(math.radians(45.0))
        on_n = 100.0 * math.cos(math.radians(45.0))
        self.assertAlmostEqual(runner.cross_track_error(on_e, on_n), 0.0, places=3)


if __name__ == "__main__":
    unittest.main()
