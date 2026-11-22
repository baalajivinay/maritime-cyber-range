"""
Operational Technology (OT) Protocol Tampering Engine.

Models the OT buses common to an Integrated Bridge System (IBS) and the engine
room, and the ways an attacker on those buses forges or corrupts their traffic:

  1. NMEA 0183 / NMEA 2000 sensor tampering
       * $SDDPT / $SDDBT  -- echo-sounder depth spoofing (false deep water to
         induce grounding)
       * $HEHDT           -- gyrocompass heading corruption
       * $VHW             -- speed-through-water (STW) falsification
  2. Radar / ARPA false-target generation
       * synthetic target blips + tracking-vector distortion for the ECDIS
         radar overlay
  3. Engine CAN bus / SAE J1939 telemetry sabotage
       * shaft RPM, torque and cooling-water overheat alarms driving the engine
         governor into limp mode

Every emitted frame carries a cryptographic-integrity verdict so the Bus
Inspector can tag it VALID / CORRUPTED / UNAUTHENTICATED.

Stdlib only; Qt-free so it is unit-testable in isolation.
"""
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi

# Integrity verdicts
VALID = "VALID"
CORRUPTED = "CORRUPTED"
UNAUTHENTICATED = "UNAUTHENTICATED"

# J1939 parameter group numbers used below
PGN_EEC1 = 61444   # Electronic Engine Controller 1 (engine speed)
PGN_EEC2 = 61443   # Electronic Engine Controller 2 (load/torque)
PGN_ET1 = 65262    # Engine Temperature 1 (coolant)

# Governor limp-mode trip: coolant over-temperature (deg C)
COOLANT_LIMP_C = 105.0
COOLANT_ALARM_C = 98.0


def nmea_checksum(body: str) -> str:
    """XOR of every character between '$'/'!' and '*', as two upper-hex digits."""
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"{c:02X}"


def build_nmea(body: str, corrupt_checksum: bool = False) -> str:
    """Wrap a sentence body as ``$<body>*HH``. If ``corrupt_checksum`` the
    appended checksum is deliberately wrong (the on-the-wire signature of a
    naive injector that recomputed nothing)."""
    cs = nmea_checksum(body)
    if corrupt_checksum:
        # Flip the low nibble so a conformant receiver rejects the sentence
        bad = (int(cs, 16) ^ 0x1) & 0xFF
        cs = f"{bad:02X}"
    return f"${body}*{cs}"


# =============================================================================
# NMEA 0183 sentence builders (depth / heading / STW)
# =============================================================================
def ddpt_sentence(depth_m: float, offset_m: float = 0.0) -> str:
    """$SDDPT — depth below transducer, plus transducer offset."""
    return build_nmea(f"SDDPT,{depth_m:.1f},{offset_m:.1f}")


def ddbt_sentence(depth_m: float) -> str:
    """$SDDBT — depth below transducer in feet/metres/fathoms."""
    feet = depth_m * 3.28084
    fath = depth_m * 0.546807
    return build_nmea(f"SDDBT,{feet:.1f},f,{depth_m:.1f},M,{fath:.1f},F")


def hehdt_sentence(heading_deg: float) -> str:
    """$HEHDT — gyrocompass true heading."""
    return build_nmea(f"HEHDT,{heading_deg % 360.0:.1f},T")


def vhw_sentence(heading_deg: float, stw_knots: float) -> str:
    """$VHW — water speed and heading (speed through the water)."""
    kmh = stw_knots * 1.852
    return build_nmea(
        f"VHW,{heading_deg % 360.0:.1f},T,{heading_deg % 360.0:.1f},M,"
        f"{stw_knots:.1f},N,{kmh:.1f},K"
    )


@dataclass
class EngineState:
    """SAE J1939 engine-room telemetry snapshot."""
    rpm: float = 0.0
    torque_pct: float = 0.0
    coolant_c: float = 70.0
    limp_mode: bool = False
    overheat_alarm: bool = False


@dataclass
class RadarTarget:
    """One ARPA-tracked contact (true or injected)."""
    track_id: str
    east_m: float
    north_m: float
    course_deg: float
    speed_mps: float
    synthetic: bool = False     # True => injected / not physically present
    distorted: bool = False     # True => a real track whose vector was skewed


@dataclass
class OTFrame:
    proto: str
    payload: str
    verdict: str
    is_anomaly: bool


class OTProtocolEngine:
    """
    Stateful generator of IBS / engine-room OT bus traffic with attacker
    tampering. Toggle individual vectors, then call :meth:`update` once per
    telemetry tick to advance state and :meth:`frames`/:meth:`radar_targets`
    to read the bus.
    """

    def __init__(self):
        # Attack toggles
        self.depth_spoof = False
        self.heading_spoof = False
        self.stw_spoof = False
        self.arpa_false_targets = False
        self.engine_sabotage = False

        # Tamper magnitudes
        self.depth_false_m = 45.0       # reported (false) deep water
        self.heading_bias_deg = 18.0    # injected gyro error
        self.stw_false_knots = 2.0      # under-reported STW

        self.engine = EngineState()
        self._elapsed = 0.0
        self._synthetic_tracks: List[RadarTarget] = []
        self._frames: List[OTFrame] = []

    # ------------------------------------------------------------------ toggles
    def set_attack(self, name: str, on: bool):
        if hasattr(self, name):
            setattr(self, name, bool(on))

    def any_active(self) -> bool:
        return any((self.depth_spoof, self.heading_spoof, self.stw_spoof,
                    self.arpa_false_targets, self.engine_sabotage))

    def clear(self):
        self.depth_spoof = self.heading_spoof = self.stw_spoof = False
        self.arpa_false_targets = self.engine_sabotage = False
        self.engine = EngineState()
        self._synthetic_tracks.clear()
        self._frames.clear()

    # ------------------------------------------------------------------- update
    def update(self, dt: float, state: Dict[str, Any]) -> Dict[str, Any]:
        """Advance OT models by ``dt`` using the live vessel ``state``.

        Returns a small overlay dict (engine telemetry + alarm flags) and
        refreshes :attr:`_frames` / :attr:`_synthetic_tracks`.
        """
        self._elapsed += dt
        self._frames = []

        true_depth = float(state.get("depth", 0.0) or 0.0)
        true_hdg = float(state.get("hdg", 0.0) or 0.0)
        true_sog_kn = float(state.get("speed_knots", 0.0) or 0.0)
        throttle = float(state.get("throttle_pct", 0.0) or 0.0)
        water_depth = float(state.get("altitude", 40.0) or 40.0) + true_depth

        # --- NMEA depth (echo sounder) --------------------------------------
        if self.depth_spoof:
            # Report false DEEP water so the OOW believes it is safe
            self._frames.append(OTFrame(
                "NMEA 0183", ddpt_sentence(self.depth_false_m),
                UNAUTHENTICATED, True))
            self._frames.append(OTFrame(
                "NMEA 0183", ddbt_sentence(self.depth_false_m),
                CORRUPTED, True))
        else:
            under_keel = max(0.5, water_depth - true_depth) if water_depth else 20.0
            self._frames.append(OTFrame(
                "NMEA 0183", ddpt_sentence(under_keel), VALID, False))

        # --- NMEA gyrocompass heading ---------------------------------------
        if self.heading_spoof:
            self._frames.append(OTFrame(
                "NMEA 0183", hehdt_sentence(true_hdg + self.heading_bias_deg),
                CORRUPTED, True))
        else:
            self._frames.append(OTFrame(
                "NMEA 0183", hehdt_sentence(true_hdg), VALID, False))

        # --- NMEA speed through water ---------------------------------------
        if self.stw_spoof:
            self._frames.append(OTFrame(
                "NMEA 0183", vhw_sentence(true_hdg, max(0.0, true_sog_kn - self.stw_false_knots)),
                CORRUPTED, True))
        else:
            self._frames.append(OTFrame(
                "NMEA 0183", vhw_sentence(true_hdg, true_sog_kn), VALID, False))

        # --- Engine CAN / J1939 ---------------------------------------------
        self._step_engine(dt, throttle)

        # --- Radar / ARPA ----------------------------------------------------
        self._step_radar(dt, state)

        return {
            "ot_active": self.any_active(),
            "engine_rpm": self.engine.rpm,
            "engine_torque_pct": self.engine.torque_pct,
            "coolant_c": self.engine.coolant_c,
            "engine_limp_mode": self.engine.limp_mode,
            "engine_overheat": self.engine.overheat_alarm,
            "arpa_false_target_count": sum(1 for t in self._synthetic_tracks if t.synthetic),
        }

    # ------------------------------------------------------------------- engine
    def _step_engine(self, dt: float, throttle_pct: float):
        eng = self.engine
        # Nominal governor: RPM tracks throttle toward ~1800 rpm redline band
        target_rpm = 600.0 + (throttle_pct / 100.0) * 1200.0
        eng.rpm += (target_rpm - eng.rpm) * min(1.0, dt * 1.5)
        eng.torque_pct = max(0.0, min(100.0, throttle_pct * 0.9 + 5.0))

        if self.engine_sabotage:
            # Forced coolant over-temperature + torque spike
            eng.coolant_c += 9.0 * dt
            eng.coolant_c = min(125.0, eng.coolant_c)
            eng.torque_pct = min(118.0, eng.torque_pct + 25.0)  # implausible >100%
            eng.overheat_alarm = eng.coolant_c >= COOLANT_ALARM_C
            if eng.coolant_c >= COOLANT_LIMP_C:
                eng.limp_mode = True
            if eng.limp_mode:
                # Governor limp mode clamps RPM/torque to protect the plant
                eng.rpm = min(eng.rpm, 900.0)
                eng.torque_pct = min(eng.torque_pct, 40.0)

            self._frames.append(OTFrame(
                "J1939 CAN", self._j1939_eec1(eng.rpm), CORRUPTED, True))
            self._frames.append(OTFrame(
                "J1939 CAN", self._j1939_eec2(eng.torque_pct), CORRUPTED, True))
            self._frames.append(OTFrame(
                "J1939 CAN", self._j1939_et1(eng.coolant_c),
                UNAUTHENTICATED, True))
        else:
            # Cool back toward steady state
            steady = 82.0 if throttle_pct > 10 else 70.0
            eng.coolant_c += (steady - eng.coolant_c) * min(1.0, dt * 0.3)
            eng.overheat_alarm = False
            eng.limp_mode = False
            self._frames.append(OTFrame(
                "J1939 CAN", self._j1939_eec1(eng.rpm), VALID, False))

    @staticmethod
    def _j1939_eec1(rpm: float) -> str:
        # EEC1: SPN 190 engine speed (0.125 rpm/bit)
        raw = int(min(8031.875, max(0.0, rpm)) / 0.125) & 0xFFFF
        return (f"PGN {PGN_EEC1} EEC1 [SPN190 EngSpeed={rpm:.0f}rpm "
                f"raw=0x{raw:04X}]")

    @staticmethod
    def _j1939_eec2(torque_pct: float) -> str:
        raw = int(min(250, max(0, torque_pct + 125))) & 0xFF
        return (f"PGN {PGN_EEC2} EEC2 [SPN513 ActualTorque={torque_pct:.0f}% "
                f"raw=0x{raw:02X}]")

    @staticmethod
    def _j1939_et1(coolant_c: float) -> str:
        raw = int(min(255, max(0, coolant_c + 40))) & 0xFF
        return (f"PGN {PGN_ET1} ET1 [SPN110 CoolantTemp={coolant_c:.0f}C "
                f"raw=0x{raw:02X}]")

    # -------------------------------------------------------------------- radar
    def _step_radar(self, dt: float, state: Dict[str, Any]):
        own_e = float(state.get("east_m", 0.0) or 0.0)
        own_n = float(state.get("north_m", 0.0) or 0.0)

        if not self.arpa_false_targets:
            self._synthetic_tracks = []
            return

        if not self._synthetic_tracks:
            # Seed a small raid of synthetic blips around own-ship
            self._synthetic_tracks = [
                RadarTarget("T-FAKE-01", own_e + 420.0, own_n + 180.0, 250.0, 6.0, synthetic=True),
                RadarTarget("T-FAKE-02", own_e - 260.0, own_n + 500.0, 190.0, 4.5, synthetic=True),
                RadarTarget("T-FAKE-03", own_e + 120.0, own_n - 480.0, 20.0, 7.5, synthetic=True),
            ]

        # Advance synthetic blips along their (false) vectors
        for t in self._synthetic_tracks:
            vn = t.speed_mps * math.cos(t.course_deg * DEG_TO_RAD)
            ve = t.speed_mps * math.sin(t.course_deg * DEG_TO_RAD)
            t.east_m += ve * dt
            t.north_m += vn * dt
            self._frames.append(OTFrame(
                "Radar/ARPA",
                f"TTM {t.track_id} brg/rng synthetic blip "
                f"spd={t.speed_mps*1.944:.1f}kn crs={t.course_deg:.0f}",
                UNAUTHENTICATED, True))

    # ------------------------------------------------------------------- access
    def frames(self) -> List[OTFrame]:
        return list(self._frames)

    def radar_targets(self) -> List[RadarTarget]:
        return list(self._synthetic_tracks)
