"""
Regression + fuzz-hardening tests from the aggressive debugging campaign.

Each test pins a specific bug found during fuzzing so it can never recur:
  * AIVDM encoder crashed on negative/out-of-range speed & course (WS3)
  * ECDIS grid rendering could infinite-loop at extreme zoom-out (WS1)
  * repeated Start/Stop leaked background boot threads (WS5)
plus broad singularity / malformed-input sweeps across physics, protocols and
the OT engine.
"""
import os
import sys
import math
import time
import random
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for p in (REPO, os.path.join(REPO, "application"), os.path.join(REPO, "communication"), os.path.join(REPO, "attacks")):
    if p not in sys.path:
        sys.path.insert(0, p)

from attacks.advanced_attacks import encode_aivdm_type1, nmea_checksum, calculate_cpa_tcpa
from attacks.ot_protocols import OTProtocolEngine
from scaleup.physics.marine_dynamics import MarineDynamicsEngine
from scaleup.protocols import nmea0183 as NMEA
from communication.secure_protocol import MAVLink2Signer, ReplayProtectionWindow


# ---------------------------------------------------------------------------
# WS3 — AIVDM encoder must never crash and always emit a legal armored payload
# ---------------------------------------------------------------------------
class TestAIVDMEncoderHardening(unittest.TestCase):
    def test_negative_and_extreme_inputs(self):
        rng = random.Random(42)
        for _ in range(3000):
            s = encode_aivdm_type1(
                rng.randint(-10, 2 ** 34),
                rng.uniform(-300, 300), rng.uniform(-500, 500),
                rng.uniform(-100, 5000), rng.uniform(-999, 9999))
            self.assertTrue(s.startswith("!AIVDM"))
            star = s.rfind("*")
            body = s[1:star]
            self.assertEqual(nmea_checksum(body), s[star + 1:])
            # payload chars must be in the 6-bit armor range (chr 48..119)
            payload = body.split(",")[5]
            self.assertTrue(all(48 <= ord(c) <= 119 for c in payload))

    def test_specific_negative_regression(self):
        # The exact class of input that used to raise ValueError ('-' in bits)
        for spd, crs in [(-5.0, -30.0), (-0.1, -0.1), (-50.0, -720.0)]:
            s = encode_aivdm_type1(419000123, 9.9, 76.2, spd, crs)
            self.assertTrue(s.startswith("!AIVDM"))

    def test_valid_sentence_still_decodes(self):
        try:
            from pyais import decode
        except Exception:
            self.skipTest("pyais not installed")
        m = decode(encode_aivdm_type1(419000123, 9.9, 76.2, 12.0, 180.0))
        self.assertEqual(m.mmsi, 419000123)


# ---------------------------------------------------------------------------
# WS1 — ECDIS must survive extreme zoom/pan without a pathological loop
# ---------------------------------------------------------------------------
class TestECDISRenderHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _render(self, canvas):
        from PyQt6.QtGui import QPixmap
        canvas.resize(800, 600)
        pm = QPixmap(800, 600)
        canvas.render(pm)

    def test_extreme_zoom_out_terminates(self):
        from application.console.widgets.ecdis import ChartCanvas
        c = ChartCanvas()
        # Directly force a sub-pixel scale that previously caused int(step)=0
        c.scale_m_to_px = 0.0001
        c.pan_x = 1e7
        c.pan_y = -1e7
        done = {"ok": False}

        def run():
            self._render(c)
            done["ok"] = True

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=10.0)
        self.assertTrue(done["ok"], "ECDIS render hung at extreme zoom-out")
        # paintEvent clamps the scale back into range
        self.assertGreaterEqual(c.scale_m_to_px, 0.02)
        self.assertLessEqual(c.scale_m_to_px, 50.0)

    def test_extreme_zoom_in_and_many_waypoints(self):
        from application.console.widgets.ecdis import ChartCanvas
        c = ChartCanvas()
        for _ in range(50):
            c.append_route_wp(random.uniform(-1e6, 1e6), random.uniform(-1e6, 1e6))
        c.scale_m_to_px = 1000.0
        done = {"ok": False}

        def run():
            self._render(c)
            done["ok"] = True

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=10.0)
        self.assertTrue(done["ok"])


# ---------------------------------------------------------------------------
# WS5 — repeated Start/Stop must not leak background boot threads
# ---------------------------------------------------------------------------
class _StubBackend:
    """A fast, side-effect-free stand-in for UnifiedBackend that mimics the
    boot/teardown surface the app lifecycle drives."""
    def __init__(self):
        self.engine = None
        self.connected = False
        self.boots = 0
        self.teardowns = 0
        self._state = {"lat": None}

    @property
    def state(self):
        return self._state

    def boot(self, site, twin, domain):
        self.boots += 1
        time.sleep(0.05)
        self.engine = object()

    def teardown(self):
        self.teardowns += 1
        self.engine = None

    def arm(self): pass
    def disarm(self): pass
    def goto(self, *a): pass
    def attack(self, *a): pass
    def stop_attack(self): pass


class TestBackendLifecycleNoLeak(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_repeated_start_stop_no_thread_growth(self):
        from application.console.app import MCRMainWindow
        w = MCRMainWindow()
        w.backend = _StubBackend()
        base = threading.active_count()
        for _ in range(15):
            w._on_start_clicked()
            for _ in range(2):
                w._update_loop()
            w._on_stop_clicked()
            for _ in range(2):
                w._update_loop()
        # let any boot/teardown threads drain
        for _ in range(20):
            time.sleep(0.1)
            if threading.active_count() <= base + 1:
                break
        self.assertLessEqual(threading.active_count(), base + 1,
                             "background threads accumulated across Start/Stop cycles")
        self.assertGreaterEqual(w.backend.teardowns, 1)
        w.close()

    def test_reentrant_start_is_noop(self):
        from application.console.app import MCRMainWindow
        w = MCRMainWindow()
        w.backend = _StubBackend()
        w._on_start_clicked()
        self.assertTrue(w.is_running)
        w._on_start_clicked()   # re-entrant: must not boot again
        w._on_start_clicked()
        time.sleep(0.2)
        self.assertEqual(w.backend.boots, 1)
        w._on_stop_clicked()
        w.close()


# ---------------------------------------------------------------------------
# Broad singularity / malformed-input sweeps
# ---------------------------------------------------------------------------
class TestPhysicsSingularities(unittest.TestCase):
    def test_waypoint_on_ownship_no_nan(self):
        e = MarineDynamicsEngine("interceptor_usv", "kochi")
        e.armed = True
        e.set_target_waypoint(e.east_m, e.north_m)
        for _ in range(50):
            s = e.step(0.1)
            for v in s.values():
                if isinstance(v, (int, float)):
                    self.assertTrue(math.isfinite(v))

    def test_zero_speed_hard_rudder(self):
        e = MarineDynamicsEngine("maya_auv", "kochi")
        e.armed = True
        e.rudder_cmd_deg = 35.0
        for _ in range(20):
            self.assertTrue(math.isfinite(e.step(0.1)["hdg"]))

    def test_depth_saturation_bounds(self):
        e = MarineDynamicsEngine("auv150", "kochi")
        e.armed = True
        e.target_depth_m = 1e5
        for _ in range(60):
            e.step(0.1)
        self.assertLessEqual(e.depth_m, e.max_water_depth)
        self.assertGreaterEqual(e.depth_m, 0.0)

    def test_cpa_parallel_and_diverging_finite(self):
        c, t = calculate_cpa_tcpa((0, 0), (0, 5), (100, 0), (0, 5))  # parallel
        self.assertTrue(math.isfinite(c) and math.isfinite(t))
        c, t = calculate_cpa_tcpa((0, 0), (0, 5), (0, 100), (0, 10))  # diverging
        self.assertTrue(math.isfinite(c) and math.isfinite(t))


class TestProtocolParserHardening(unittest.TestCase):
    def test_nmea_parse_never_raises(self):
        rng = random.Random(3)
        corpus = ["", "$", "*", "$*", "$GPGGA", "$GPGGA,,,,,,,,*00",
                  "$GPRMC,x,A,,N,,E,zz,,,,*7F", "$SDDPT,,,*00", "garbage",
                  "$GPGGA,.5,N,.5,E*00", "$,,,,"]
        for _ in range(2000):
            corpus.append("$" + "".join(
                rng.choice("0123456789,.*ABCDEFGPRMCNSEW") for _ in range(rng.randint(0, 30))))
        for s in corpus:
            NMEA.parse(s)  # must not raise

    def test_mavlink_rejects_malformed(self):
        s = MAVLink2Signer()
        good = s.sign_packet(b"PAYLOAD")
        ok, _, _ = s.verify_packet(good)
        self.assertTrue(ok)
        rng = random.Random(9)
        for _ in range(500):
            n = rng.randint(0, 40)
            blob = bytes(rng.randrange(256) for _ in range(n))
            res, _, _ = s.verify_packet(blob)  # must return, not raise
            self.assertIn(res, (True, False))

    def test_replay_window_rejects_duplicates(self):
        w = ReplayProtectionWindow(64)
        self.assertTrue(w.check_and_update(100))
        self.assertFalse(w.check_and_update(100))     # duplicate
        self.assertTrue(w.check_and_update(50))       # older, fresh
        self.assertFalse(w.check_and_update(50))      # duplicate
        self.assertFalse(w.check_and_update(100 - 64))  # outside window


class TestOTEngineHardening(unittest.TestCase):
    def test_extreme_inputs_finite(self):
        e = OTProtocolEngine()
        for a in ("depth_spoof", "heading_spoof", "stw_spoof", "arpa_false_targets", "engine_sabotage"):
            e.set_attack(a, True)
        rng = random.Random(11)
        for _ in range(500):
            st = {"depth": rng.uniform(-100, 1e5), "hdg": rng.uniform(-1e4, 1e4),
                  "speed_knots": rng.uniform(-100, 1e4), "throttle_pct": rng.uniform(-50, 1e4),
                  "altitude": rng.uniform(-100, 1e5), "east_m": rng.uniform(-1e6, 1e6),
                  "north_m": rng.uniform(-1e6, 1e6)}
            ov = e.update(0.1, st)
            for k in ("engine_rpm", "coolant_c", "engine_torque_pct"):
                self.assertTrue(math.isfinite(ov[k]))


if __name__ == "__main__":
    unittest.main()
