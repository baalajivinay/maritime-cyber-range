import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "nodes", "app"))
sys.path.insert(0, os.path.join(REPO, "tools"))

from nodes.app.mcr_app import Backend
from tools.stonefish_source import StonefishSource


class TestSimulationParity(unittest.TestCase):
    def test_telemetry_schema_parity(self):
        backend_gz = Backend()
        source_sf = StonefishSource()

        # Check that both have matching state keys
        gz_keys = set(backend_gz.state.keys())
        sf_keys = set(source_sf.state.keys())
        self.assertEqual(gz_keys, sf_keys)

        # Standard required telemetry fields
        required_fields = {
            "lat", "lon", "hdg", "roll", "pitch", "depth",
            "speed", "mode", "armed", "hb", "sim_backend"
        }
        self.assertTrue(required_fields.issubset(gz_keys))
        self.assertEqual(backend_gz.state["sim_backend"], "gazebo")
        self.assertEqual(source_sf.state["sim_backend"], "stonefish")

        # Both maintain track list
        self.assertIsInstance(backend_gz.track, list)
        self.assertIsInstance(source_sf.track, list)


if __name__ == "__main__":
    unittest.main()
