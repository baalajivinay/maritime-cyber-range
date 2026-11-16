import unittest
import math
import xml.etree.ElementTree as ET


class TestInterceptorSpeedHydrodynamics(unittest.TestCase):
    def test_cusv_sdf_planing_drag_and_thrust(self):
        # Parse sim_config/models/cusv/model.sdf
        tree = ET.parse("sim_config/models/cusv/model.sdf")
        root = tree.getroot()
        
        # Check Hydrodynamics drag
        hydro = root.find(".//plugin[@name='gz::sim::systems::Hydrodynamics']")
        self.assertIsNotNone(hydro)
        xu = float(hydro.find("xU").text)
        xuabsu = float(hydro.find("xUabsU").text)
        
        # Check Thruster multipliers
        controls = root.findall(".//control")
        multipliers = [float(c.find("multiplier").text) for c in controls]
        self.assertEqual(len(multipliers), 2)
        
        # Max thrust = 2 * (multiplier * 0.5) = sum of multipliers * 0.5
        max_thrust = sum(m * 0.5 for m in multipliers)
        self.assertGreaterEqual(max_thrust, 20000.0)  # At least 20 kN for 7.7t hull
        
        # Solve steady-state terminal velocity: Drag = abs(xU)*u + abs(xUabsU)*u^2 = Thrust
        # a*u^2 + b*u - T = 0
        a = abs(xuabsu)
        b = abs(xu)
        c = -max_thrust
        terminal_u = (-b + math.sqrt(b**2 - 4*a*c)) / (2*a)
        
        # Interceptor must plane at ~15-18 m/s (~30-35 knots), not crawl at 1-2 m/s
        self.assertGreaterEqual(terminal_u, 14.5)
        self.assertLessEqual(terminal_u, 22.0)


if __name__ == "__main__":
    unittest.main()
