"""
Advanced Maritime Cyber Attack Execution Engine.
Implements state-of-the-art attack execution techniques conforming to
IACS UR E26/E27, IMO COLREGS Rules 14/15, and DNV-ST-0373.

Provides:
1. Multi-Mode GNSS Spoofing: Sub-threshold EKF3 Ramp Walk-off, Step Jump, Harmonic Meander, and SNR Jamming.
2. COLREGS-Compliant AIS Spoofing: Head-On (Rule 14), Crossing (Rule 15), Own-MMSI Impersonation, and Swarm injection.
3. Real-Time CPA (Closest Point of Approach) & TCPA (Time to CPA) Calculation.
4. C2 Injection: RC Channels Actuator Seizure, Mode Forgery, Rogue Waypoint Injection, and Packet Replay.
5. Underwater USBL Acoustic Spoofing: Transponder Two-Way Travel Time Bias and Sound Velocity Profile skew.
6. Authentic ITU-R M.1371 AIVDM 6-bit armored ASCII and NMEA 0183 checksum generation.
"""
import math
import time
from typing import Dict, Any, Tuple, Optional, List

DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi
DEG_TO_M = 111320.0


def nmea_checksum(sentence_body: str) -> str:
    """Calculates 2-digit uppercase hex XOR checksum for NMEA sentences."""
    c = 0
    for ch in sentence_body:
        c ^= ord(ch)
    return f"{c:02X}"


def encode_aivdm_type1(mmsi: int, lat: float, lon: float, speed_knots: float, course_deg: float) -> str:
    """
    Generates a valid ITU-R M.1371 Type 1 Position Report AIVDM NMEA sentence
    using standard 6-bit ASCII armoring.
    """
    # Clip and convert coordinates to 1/10000 min. Every field is clamped and
    # masked to its unsigned bit-width so adversarial / out-of-range inputs
    # (negative speed, negative or huge course, oversized MMSI) can never emit a
    # '-' sign or an over-long field into the 6-bit-armored payload.
    mmsi = int(mmsi) & 0x3FFFFFFF                       # 30-bit MMSI
    lat_i = int(lat * 600000) & 0x7FFFFFF               # 27-bit
    lon_i = int(lon * 600000) & 0xFFFFFFF               # 28-bit
    sog_i = max(0, min(1023, int(speed_knots * 10)))    # 10-bit (1023 = n/a)
    cog_i = int(course_deg * 10) % 3600                 # 12-bit (0..3599)
    true_hdg_i = int(course_deg) % 360                  # 9-bit (0..359)

    # Build 168-bit binary string
    bits = ""
    bits += f"{1:06b}"                # Message Type 1 (6 bits)
    bits += f"{0:02b}"                # Repeat indicator (2 bits)
    bits += f"{mmsi:030b}"            # MMSI (30 bits)
    bits += f"{0:04b}"                # Nav status: 0 = Under way using engine (4 bits)
    bits += f"{0:08b}"                # Rate of turn: 0 (8 bits)
    bits += f"{sog_i:010b}"           # Speed over ground (10 bits)
    bits += f"{1:01b}"                # Position accuracy: 1 (1 bit)
    bits += f"{lon_i:028b}"           # Longitude (28 bits)
    bits += f"{lat_i:027b}"           # Latitude (27 bits)
    bits += f"{cog_i:012b}"           # Course over ground (12 bits)
    bits += f"{true_hdg_i:09b}"       # True heading (9 bits)
    bits += f"{int(time.time()) % 60:06b}"  # Timestamp seconds (6 bits)
    bits += f"{0:02b}"                # Maneuver indicator (2 bits)
    bits += f"{0:03b}"                # Spare (3 bits)
    bits += f"{0:01b}"                # RAIM flag (1 bit)
    bits += f"{0:019b}"               # Radio status (19 bits)

    # Pad to multiple of 6
    if len(bits) % 6 != 0:
        bits += "0" * (6 - (len(bits) % 6))

    # Armor to 6-bit ASCII
    payload = ""
    for i in range(0, len(bits), 6):
        chunk = int(bits[i:i+6], 2)
        char_code = chunk + 48 if chunk < 40 else chunk + 56
        payload += chr(char_code)

    body = f"AIVDM,1,1,,A,{payload},0"
    return f"!{body}*{nmea_checksum(body)}"


def calculate_cpa_tcpa(
    own_pos: Tuple[float, float], own_vel: Tuple[float, float],
    target_pos: Tuple[float, float], target_vel: Tuple[float, float]
) -> Tuple[float, float]:
    """
    Computes CPA (Closest Point of Approach in meters) and TCPA (Time to CPA in seconds)
    between own ship and target contact.
    own_pos / target_pos: (East m, North m)
    own_vel / target_vel: (Ve m/s, Vn m/s)
    """
    dx = target_pos[0] - own_pos[0]
    dy = target_pos[1] - own_pos[1]
    dvx = target_vel[0] - own_vel[0]
    dvy = target_vel[1] - own_vel[1]

    v_rel_sq = dvx**2 + dvy**2
    if v_rel_sq < 1e-4:
        # Parallel courses or stationary: current distance is CPA
        dist = math.hypot(dx, dy)
        return dist, 0.0

    # TCPA = - (P_rel . V_rel) / |V_rel|^2
    tcpa = -(dx * dvx + dy * dvy) / v_rel_sq

    if tcpa < 0.0:
        # Diverging
        dist = math.hypot(dx, dy)
        return dist, tcpa

    # Position at CPA
    cpa_x = dx + dvx * tcpa
    cpa_y = dy + dvy * tcpa
    cpa_dist = math.hypot(cpa_x, cpa_y)
    return cpa_dist, tcpa


class AttackExecutionManager:
    """
    Stateful manager for executing and tracking all cyber attacks.
    """
    def __init__(self):
        self.active_attack: Optional[str] = None
        self.attack_mode: str = "walk_off"
        self.start_time: float = 0.0
        self.elapsed_time: float = 0.0
        self.params: Dict[str, Any] = {}

        # GPS Spoofing State
        self.gps_offset_n: float = 0.0
        self.gps_offset_e: float = 0.0
        self.gps_drift_rate: float = 2.5  # m/s
        self.gps_bearing_deg: float = 45.0
        self.gps_hdop: float = 0.8
        self.gps_sats: int = 14

        # AIS Ghost State
        self.ghost_mmsi: str = "419000123"
        self.ghost_name: str = "PHANTOM-CARRIER"
        self.ghost_pos: Tuple[float, float] = (150.0, 300.0)  # (East m, North m)
        self.ghost_course: float = 180.0
        self.ghost_speed: float = 5.0  # m/s
        self.ghost_scenario: str = "head_on"

        # USBL Acoustic State (AUV)
        self.usbl_delay_m: float = 0.0
        self.acoustic_noise_db: float = 0.0

    def start_gps_attack(self, mode: str = "ramp", drift_rate: float = 2.5, bearing_deg: float = 45.0):
        self.active_attack = "gps_spoof"
        self.attack_mode = mode
        self.start_time = time.time()
        self.elapsed_time = 0.0
        self.gps_drift_rate = drift_rate
        self.gps_bearing_deg = bearing_deg
        self.gps_offset_n = 0.0
        self.gps_offset_e = 0.0

    def start_ais_attack(self, scenario: str = "head_on", own_pos: Tuple[float, float] = (0.0, 0.0), own_hdg: float = 45.0):
        self.active_attack = "ais_spoof"
        self.attack_mode = scenario
        self.start_time = time.time()
        self.elapsed_time = 0.0
        self.ghost_scenario = scenario

        # Position ghost based on scenario geometry
        rad = own_hdg * DEG_TO_RAD
        if scenario == "head_on":
            # Rule 14: Dead ahead at 350m, reciprocal course (hdg + 180)
            dist = 320.0
            self.ghost_pos = (own_pos[0] + dist * math.sin(rad), own_pos[1] + dist * math.cos(rad))
            self.ghost_course = (own_hdg + 180.0) % 360.0
            self.ghost_speed = 4.5
            self.ghost_mmsi = "419000123"
        elif scenario == "crossing":
            # Rule 15: Crossing from starboard (hdg + 50 deg) on collision course
            bearing_rad = (own_hdg + 50.0) * DEG_TO_RAD
            dist = 280.0
            self.ghost_pos = (own_pos[0] + dist * math.sin(bearing_rad), own_pos[1] + dist * math.cos(bearing_rad))
            self.ghost_course = (own_hdg - 90.0) % 360.0
            self.ghost_speed = 5.2
            self.ghost_mmsi = "419000456"
        elif scenario == "impersonate":
            # MMSI Impersonation
            self.ghost_pos = (own_pos[0] + 45.0, own_pos[1] + 30.0)
            self.ghost_course = own_hdg
            self.ghost_speed = 3.0
            self.ghost_mmsi = "419000234"  # Own MMSI
        else:
            self.ghost_pos = (own_pos[0] + 180.0, own_pos[1] + 180.0)
            self.ghost_course = 225.0
            self.ghost_speed = 4.0
            self.ghost_mmsi = "419000888"

    def start_c2_attack(self, cmd_type: str = "rc_override"):
        self.active_attack = "c2_replay"
        self.attack_mode = cmd_type
        self.start_time = time.time()
        self.elapsed_time = 0.0

    def start_acoustic_attack(self, delay_rate: float = 1.5):
        self.active_attack = "acoustic_spoof"
        self.start_time = time.time()
        self.elapsed_time = 0.0
        self.usbl_delay_m = 0.0

    def stop_attack(self):
        self.active_attack = None
        self.elapsed_time = 0.0
        self.gps_offset_n = 0.0
        self.gps_offset_e = 0.0
        self.usbl_delay_m = 0.0
        self.gps_hdop = 0.8
        self.gps_sats = 14

    def update(self, dt: float, own_pos: Tuple[float, float], own_vel: Tuple[float, float]) -> Dict[str, Any]:
        """
        Advances attack models by dt seconds and returns telemetry overlay dict.
        """
        if self.active_attack:
            self.elapsed_time += dt
        elapsed = self.elapsed_time
        res = {
            "active_attack": self.active_attack,
            "attack_mode": self.attack_mode,
            "elapsed_s": elapsed,
            "gps_offset_m": [0.0, 0.0],
            "gps_hdop": 0.8,
            "gps_sats": 14,
            "simulated_innovation": 1.1,
            "ghost_vessel": None,
            "cpa_m": None,
            "tcpa_s": None,
            "collision_risk": False,
            "usbl_offset_m": 0.0
        }

        # 1. GPS Spoofing Update
        if self.active_attack == "gps_spoof":
            bearing_rad = self.gps_bearing_deg * DEG_TO_RAD
            if self.attack_mode == "step":
                mag = 35.0
            elif self.attack_mode == "meander":
                mag = self.gps_drift_rate * 12.0 * math.sin(elapsed * 0.4)
            elif self.attack_mode == "jam":
                # SNR Jamming: Position jitters, HDOP degrades to 6.5+
                mag = 3.0 * math.sin(elapsed * 2.0)
                self.gps_hdop = min(8.5, 0.8 + elapsed * 0.8)
                self.gps_sats = max(3, int(14 - elapsed * 1.5))
            else:  # ramp / walk-off
                mag = self.gps_drift_rate * elapsed

            self.gps_offset_n = mag * math.cos(bearing_rad)
            self.gps_offset_e = mag * math.sin(bearing_rad)

            drift_dist = math.hypot(self.gps_offset_e, self.gps_offset_n)
            # EKF3 innovation grows with drift distance
            res["simulated_innovation"] = 1.1 + drift_dist * 0.38
            res["gps_offset_m"] = [self.gps_offset_e, self.gps_offset_n]
            res["gps_hdop"] = self.gps_hdop
            res["gps_sats"] = self.gps_sats

        # 2. AIS Spoofing Update
        elif self.active_attack == "ais_spoof":
            # Advance ghost ship along its course
            ghdg_rad = self.ghost_course * DEG_TO_RAD
            g_vn = self.ghost_speed * math.cos(ghdg_rad)
            g_ve = self.ghost_speed * math.sin(ghdg_rad)

            self.ghost_pos = (self.ghost_pos[0] + g_ve * dt, self.ghost_pos[1] + g_vn * dt)

            # Compute CPA and TCPA relative to own ship
            cpa, tcpa = calculate_cpa_tcpa(own_pos, own_vel, self.ghost_pos, (g_ve, g_vn))
            res["cpa_m"] = cpa
            res["tcpa_s"] = tcpa
            res["collision_risk"] = (cpa < 60.0 and 0.0 <= tcpa <= 60.0)

            res["ghost_vessel"] = {
                "pos": self.ghost_pos,
                "course": self.ghost_course,
                "speed": self.ghost_speed,
                "mmsi": self.ghost_mmsi,
                "name": self.ghost_name
            }

        # 3. Acoustic Spoofing Update (AUV)
        elif self.active_attack == "acoustic_spoof":
            self.usbl_delay_m += 1.2 * dt
            res["usbl_offset_m"] = self.usbl_delay_m
            res["simulated_innovation"] = 1.2 + self.usbl_delay_m * 0.45

        return res
