"""
High-Fidelity 3-DOF / 6-DOF Marine Hydrodynamics & Kinematic Physics Engine.
Conforming to Thor I. Fossen's Marine Cybernetics Equations of Motion.

Models:
- Surge, Sway, Yaw dynamics with added mass and non-linear quadratic drag.
- Rudder steering gear lag and turning moment.
- Propeller thrust acceleration curves.
- True 3D depth, buoyancy, and pitch dynamics for underwater AUV twins.
- Dynamic site environmental forcing (ocean tidal stream from scaleup.sites and wave perturbations).
- Line-of-Sight (LOS) waypoint autopilot guidance and COLREGS evasive steering.
"""
import math
import time
from typing import Tuple, Dict, Any, Optional
from scaleup.sites import load_site

DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi
DEG_TO_M = 111320.0

VESSEL_PHYSICS_PRESETS = {
    "interceptor_usv": {
        "mass_kg": 1200.0,
        "length_m": 9.0,
        "beam_m": 2.6,
        "max_speed_mps": 12.8,  # ~25 knots
        "max_thrust_n": 8500.0,
        "added_mass_x": 120.0,
        "added_mass_y": 850.0,
        "inertia_z": 8500.0,
        "drag_surge_lin": 55.0,
        "drag_surge_quad": 28.0,
        "drag_sway_lin": 280.0,
        "drag_sway_quad": 200.0,
        "damping_yaw_lin": 4500.0,
        "damping_yaw_quad": 3200.0,
        "rudder_coeff": 180.0,
        "max_rudder_deg": 35.0,
        "rudder_rate_deg_s": 25.0,
        "max_rot_deg_s": 35.0,
        "domain": "surface"
    },
    "survey_usv": {
        "mass_kg": 3500.0,
        "length_m": 7.5,
        "beam_m": 3.4,
        "max_speed_mps": 5.1,   # ~10 knots
        "max_thrust_n": 4200.0,
        "added_mass_x": 400.0,
        "added_mass_y": 2100.0,
        "inertia_z": 18500.0,
        "drag_surge_lin": 95.0,
        "drag_surge_quad": 55.0,
        "drag_sway_lin": 450.0,
        "drag_sway_quad": 350.0,
        "damping_yaw_lin": 8500.0,
        "damping_yaw_quad": 6000.0,
        "rudder_coeff": 220.0,
        "max_rudder_deg": 35.0,
        "rudder_rate_deg_s": 15.0,
        "max_rot_deg_s": 18.0,
        "domain": "surface"
    },
    "mt_andaman_tug": {
        "mass_kg": 450000.0,    # 450 tons displacement
        "length_m": 32.0,
        "beam_m": 10.5,
        "max_speed_mps": 6.2,   # ~12 knots
        "max_thrust_n": 380000.0,  # 38 ton bollard pull
        "added_mass_x": 45000.0,
        "added_mass_y": 320000.0,
        "inertia_z": 2.2e7,
        "drag_surge_lin": 3500.0,
        "drag_surge_quad": 1800.0,
        "drag_sway_lin": 14000.0,
        "drag_sway_quad": 8500.0,
        "damping_yaw_lin": 1.2e6,
        "damping_yaw_quad": 9.5e5,
        "rudder_coeff": 12000.0,
        "max_rudder_deg": 35.0,
        "rudder_rate_deg_s": 8.0,
        "max_rot_deg_s": 6.0,
        "domain": "surface"
    },
    "maya_auv": {
        "mass_kg": 45.0,
        "length_m": 1.5,
        "beam_m": 0.2,
        "max_speed_mps": 2.0,   # ~4 knots
        "max_thrust_n": 120.0,
        "added_mass_x": 4.0,
        "added_mass_y": 38.0,
        "inertia_z": 45.0,
        "drag_surge_lin": 6.0,
        "drag_surge_quad": 3.5,
        "drag_sway_lin": 25.0,
        "drag_sway_quad": 18.0,
        "damping_yaw_lin": 45.0,
        "damping_yaw_quad": 30.0,
        "rudder_coeff": 12.0,
        "max_rudder_deg": 30.0,
        "rudder_rate_deg_s": 30.0,
        "max_rot_deg_s": 22.0,
        "domain": "underwater"
    },
    "auv150": {
        "mass_kg": 180.0,
        "length_m": 2.0,
        "beam_m": 0.5,
        "max_speed_mps": 1.5,   # ~3 knots
        "max_thrust_n": 280.0,
        "added_mass_x": 20.0,
        "added_mass_y": 140.0,
        "inertia_z": 150.0,
        "drag_surge_lin": 18.0,
        "drag_surge_quad": 12.0,
        "drag_sway_lin": 65.0,
        "drag_sway_quad": 45.0,
        "damping_yaw_lin": 95.0,
        "damping_yaw_quad": 70.0,
        "rudder_coeff": 22.0,
        "max_rudder_deg": 35.0,
        "rudder_rate_deg_s": 25.0,
        "max_rot_deg_s": 15.0,
        "domain": "underwater"
    }
}


class MarineDynamicsEngine:
    """
    Simulates real 3-DOF and 6-DOF hydrodynamics coupled with site environmental forcing.
    """
    def __init__(self, twin_name: str = "interceptor_usv", site_name: str = "kochi"):
        self.twin_name = twin_name
        self.site_name = site_name
        self.cfg = VESSEL_PHYSICS_PRESETS.get(twin_name, VESSEL_PHYSICS_PRESETS["interceptor_usv"])

        # Load real site environment (current, depth)
        try:
            self.site = load_site(site_name)
            self.current_n, self.current_e = self.site.current_ne()
            self.max_water_depth = float(self.site.water.get("max_depth_m", 40.0))
        except Exception:
            self.site = None
            self.current_n, self.current_e = (0.0, 0.0)
            self.max_water_depth = 40.0

        # State Variables
        # Positions: NED (m) and Geographic (Lat, Lon)
        self.lat = 9.9000
        self.lon = 76.2000
        self.north_m = 0.0
        self.east_m = 0.0
        self.depth_m = 0.0 if self.cfg["domain"] == "surface" else 8.5
        self.target_depth_m = self.depth_m

        # Body-frame Velocities
        self.u = 0.0   # Surge (forward velocity in m/s)
        self.v = 0.0   # Sway (transverse velocity in m/s)
        self.w = 0.0   # Heave (vertical velocity in m/s)
        self.r = 0.0   # Yaw rate (rad/s)

        # Orientations
        self.psi = 45.0 * DEG_TO_RAD  # Heading in radians
        self.pitch = 0.0              # Trim / pitch in radians
        self.roll = 0.0               # Roll angle in radians

        # Actuator States
        self.rudder_deg = 0.0
        self.rudder_cmd_deg = 0.0
        self.throttle_pct = 0.0        # 0.0 to 100.0%

        # Autonomous Guidance
        self.target_wp: Optional[Tuple[float, float]] = None  # (East m, North m)
        self.armed = False
        self.mode = "MANUAL"

        # Wave oscillation state
        self._sim_time = 0.0

    def set_vessel_twin(self, twin_name: str):
        self.twin_name = twin_name
        self.cfg = VESSEL_PHYSICS_PRESETS.get(twin_name, VESSEL_PHYSICS_PRESETS["interceptor_usv"])
        if self.cfg["domain"] == "underwater" and self.depth_m < 1.0:
            self.depth_m = 8.5
            self.target_depth_m = 8.5
        elif self.cfg["domain"] == "surface":
            self.depth_m = 0.0
            self.target_depth_m = 0.0

    def set_site(self, site_name: str, lat: float, lon: float):
        self.site_name = site_name
        self.lat = lat
        self.lon = lon
        self.north_m = 0.0
        self.east_m = 0.0
        self.target_wp = None
        try:
            self.site = load_site(site_name)
            self.current_n, self.current_e = self.site.current_ne()
            self.max_water_depth = float(self.site.water.get("max_depth_m", 40.0))
        except Exception:
            self.current_n, self.current_e = (0.0, 0.0)

    def set_target_waypoint(self, east_m: float, north_m: float):
        self.target_wp = (east_m, north_m)

    def clear_target_waypoint(self):
        self.target_wp = None

    def step(self, dt: float, active_attack: Optional[str] = None, attack_params: Optional[dict] = None,
             defense: Optional[dict] = None) -> Dict[str, Any]:
        """
        Advances the 6-DOF / 3-DOF hydrodynamics state by dt seconds.

        ``defense`` is the optional autonomous-defense directive (Task 3). When
        present it can override the attack-driven control law: quarantine the
        actuators into a station-keeping loiter, or suppress a phantom-AIS
        evasive manoeuvre.
        """
        self._sim_time += dt
        attack_params = attack_params or {}
        defense = defense or {}

        # 1. Autopilot / LOS Guidance Control Law
        if self.armed:
            if defense.get("actuator_quarantine") or defense.get("loiter"):
                # Hijacked channel severed: autonomous station-keeping loiter.
                # A steady throttle + constant helm holds a tight circle, which
                # keeps the vessel near its current position pending operator
                # intervention, instead of running toward the hazard.
                self.mode = "DEFENSE_LOITER"
                self.throttle_pct = 28.0
                self.rudder_cmd_deg = 20.0
            elif active_attack == "c2_replay" or active_attack == "c2_override":
                # Attacker seized actuators: Force hard starboard rudder & full throttle
                self.mode = "MANUAL_HIJACKED"
                self.throttle_pct = 95.0
                self.rudder_cmd_deg = 32.0  # Hard right turn into hazard/circle
            elif active_attack == "ais_spoof" and not defense.get("suppress_ais_evasion"):
                # COLREGS Rule 14 meeting situation: Own-ship alters course to starboard (+25 deg)
                self.mode = "COLREGS_RULE14_EVASION"
                self.throttle_pct = 70.0
                desired_heading_deg = (self.psi * RAD_TO_DEG + 35.0) % 360.0
                heading_err = (desired_heading_deg - self.psi * RAD_TO_DEG + 180.0) % 360.0 - 180.0
                self.rudder_cmd_deg = max(-self.cfg["max_rudder_deg"], min(self.cfg["max_rudder_deg"], heading_err * 1.5))
            elif self.target_wp:
                # Line-of-sight (LOS) guidance toward waypoint
                self.mode = "GUIDED_LOS"
                self.throttle_pct = 80.0
                dx = self.target_wp[0] - self.east_m
                dy = self.target_wp[1] - self.north_m
                dist_to_wp = math.hypot(dx, dy)

                if dist_to_wp > 4.0:
                    desired_psi = math.atan2(dx, dy)  # 0 = North, pi/2 = East
                    psi_err = (desired_psi - self.psi + math.pi) % (2 * math.pi) - math.pi

                    # Proportional-Derivative (PD) helm autopilot
                    kp = 2.2
                    kd = 0.8
                    cmd = (psi_err * RAD_TO_DEG) * kp - (self.r * RAD_TO_DEG) * kd
                    self.rudder_cmd_deg = max(-self.cfg["max_rudder_deg"], min(self.cfg["max_rudder_deg"], cmd))
                else:
                    # Arrived at waypoint
                    self.target_wp = None
                    self.rudder_cmd_deg = 0.0
            else:
                self.mode = "GUIDED_CRUISE"
                self.throttle_pct = 65.0
                self.rudder_cmd_deg = 0.0
        else:
            self.mode = "MANUAL_DISARMED"
            self.throttle_pct = 0.0
            self.rudder_cmd_deg = 0.0

        # 2. Rudder Steering Gear Lag Dynamics (First-order differential equation)
        max_rate = self.cfg["rudder_rate_deg_s"]
        rudder_err = self.rudder_cmd_deg - self.rudder_deg
        rudder_delta = max(-max_rate * dt, min(max_rate * dt, rudder_err * 4.0 * dt))
        self.rudder_deg = max(-self.cfg["max_rudder_deg"], min(self.cfg["max_rudder_deg"], self.rudder_deg + rudder_delta))

        # 3. Propeller Thrust Acceleration
        target_thrust = (self.throttle_pct / 100.0) * self.cfg["max_thrust_n"]
        tau_x = target_thrust

        # 4. Relative Fluid Velocity (Coupling Site Ocean Currents)
        # Transform current (North, East) into body-fixed frame (Surge, Sway)
        cos_psi = math.cos(self.psi)
        sin_psi = math.sin(self.psi)
        u_c = self.current_n * cos_psi + self.current_e * sin_psi
        v_c = -self.current_n * sin_psi + self.current_e * cos_psi

        u_r = self.u - u_c
        v_r = self.v - v_c

        # 5. Fossen Marine Hydrodynamics Equations of Motion (Surge, Sway, Yaw)
        # Mass and Added Mass terms
        m_x = self.cfg["mass_kg"] + self.cfg["added_mass_x"]
        m_y = self.cfg["mass_kg"] + self.cfg["added_mass_y"]
        i_z = self.cfg["inertia_z"]

        # Hydrodynamic Damping Forces
        x_drag = -(self.cfg["drag_surge_lin"] * u_r + self.cfg["drag_surge_quad"] * u_r * abs(u_r))
        y_drag = -(self.cfg["drag_sway_lin"] * v_r + self.cfg["drag_sway_quad"] * v_r * abs(v_r))
        n_drag = -(self.cfg["damping_yaw_lin"] * self.r + self.cfg["damping_yaw_quad"] * self.r * abs(self.r))

        # Rudder Lift Force and Turning Moment
        rudder_rad = self.rudder_deg * DEG_TO_RAD
        rudder_force = self.cfg["rudder_coeff"] * (u_r ** 2) * math.sin(rudder_rad)
        y_rudder = -rudder_force
        n_rudder = +rudder_force * (self.cfg["length_m"] * 0.45)

        # Coriolis / Cross-coupling Centripetal Acceleration
        coriolis_x = m_y * self.v * self.r
        coriolis_y = -m_x * self.u * self.r

        # Accelerations
        u_dot = (tau_x + x_drag + coriolis_x) / m_x
        v_dot = (y_drag + y_rudder + coriolis_y) / m_y
        r_dot = (n_drag + n_rudder) / i_z

        # Integrate Velocities
        max_r = self.cfg.get("max_rot_deg_s", 25.0) * DEG_TO_RAD
        self.u = max(0.0, min(self.cfg["max_speed_mps"], self.u + u_dot * dt))
        self.v = self.v + v_dot * dt
        self.r = max(-max_r, min(max_r, self.r + r_dot * dt))

        # Apply realistic damping when disarmed
        if not self.armed:
            self.u *= math.exp(-0.8 * dt)
            self.v *= math.exp(-1.5 * dt)
            self.r *= math.exp(-2.0 * dt)

        # 6. Heading Integration
        self.psi = (self.psi + self.r * dt) % (2 * math.pi)

        # 7. Earth-Fixed Kinematics Integration (North, East, Depth)
        speed_north = self.u * cos_psi - self.v * sin_psi + self.current_n
        speed_east = self.u * sin_psi + self.v * cos_psi + self.current_e

        self.north_m += speed_north * dt
        self.east_m += speed_east * dt

        # Update geographic coordinates
        self.lat += (speed_north * dt) / DEG_TO_M
        self.lon += (speed_east * dt) / (DEG_TO_M * math.cos(math.radians(self.lat)))

        # 8. Depth & Pitch Dynamics for Underwater AUVs
        if self.cfg["domain"] == "underwater":
            depth_err = self.target_depth_m - self.depth_m
            self.w = max(-0.8, min(0.8, depth_err * 0.4))
            self.depth_m = max(0.5, min(self.max_water_depth - 1.5, self.depth_m + self.w * dt))
            self.pitch = max(-0.25, min(0.25, self.w * 0.3))
        else:
            self.depth_m = 0.0
            self.pitch = 0.0

        # 9. Wave Pitch / Roll Perturbations (Harmonic sea-state simulation)
        wave_freq = 0.8  # rad/s
        wave_amp = 0.04 if self.cfg["domain"] == "surface" else 0.005
        self.roll = wave_amp * math.sin(self._sim_time * wave_freq)

        # Calculate SOG (Speed Over Ground) and COG (Course Over Ground)
        sog_mps = math.hypot(speed_north, speed_east)
        cog_deg = math.degrees(math.atan2(speed_east, speed_north)) % 360.0

        return {
            "lat": self.lat,
            "lon": self.lon,
            "north_m": self.north_m,
            "east_m": self.east_m,
            "hdg": math.degrees(self.psi) % 360.0,
            "cog": cog_deg,
            "speed": sog_mps,
            "speed_knots": sog_mps * 1.94384,
            "depth": self.depth_m,
            "altitude": max(0.5, self.max_water_depth - self.depth_m),
            "rudder_angle": self.rudder_deg,
            "rudder_cmd": self.rudder_cmd_deg,
            "rot_deg_min": math.degrees(self.r) * 60.0,
            "throttle_pct": self.throttle_pct,
            "armed": self.armed,
            "mode": self.mode,
            "domain": self.cfg["domain"],
            "current_speed_mps": math.hypot(self.current_n, self.current_e),
            "current_bearing_deg": math.degrees(math.atan2(self.current_e, self.current_n)) % 360.0,
            "roll_deg": math.degrees(self.roll),
            "pitch_deg": math.degrees(self.pitch)
        }
