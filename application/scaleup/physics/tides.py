"""Harmonic tidal prediction (Axis 2.1, Tier-B input for currents).

Mumbai's current is "tidally dominated" -- a fixed vector is Tier A. A harmonic
model predicts tide height AND the tidal-stream current for a real date/time
from constituent amplitudes/phases, which is what a real run at the harbour
approaches needs. Feed it real constituents (from a TPXO/FES extraction or a
published tide-table fit) to reach Tier B; the defaults here are illustrative.

Stdlib only. h(t) = Z0 + Sum_i A_i * cos(w_i * t - g_i). Standard constituent
speeds are in deg/hour (astronomical); we convert to rad/s.
"""
import math

# principal constituent speeds, degrees per solar hour
CONSTITUENT_SPEED_DEG_PER_HR = {
    "M2": 28.9841042,   # principal lunar semidiurnal (period 12.42 h)
    "S2": 30.0000000,   # principal solar semidiurnal (12.00 h)
    "N2": 28.4397295,
    "K1": 15.0410686,   # lunisolar diurnal (23.93 h)
    "O1": 13.9430356,   # principal lunar diurnal (25.82 h)
    "P1": 14.9589314,
    "K2": 30.0821373,
    "Q1": 13.3986609,
}


def _omega(name):
    return math.radians(CONSTITUENT_SPEED_DEG_PER_HR[name]) / 3600.0  # rad/s


class TidalModel:
    """constituents: {name: (amplitude_m, phase_deg)}. z0 is mean level.
    current_gain converts the tidal rate-of-change into a stream speed proxy
    (m/s per m/s of height rate) -- site-fit in a real deployment."""
    def __init__(self, constituents, z0=0.0, current_gain=1200.0, current_bearing_deg=20.0):
        self.c = {k: (a, math.radians(g)) for k, (a, g) in constituents.items()}
        self.z0 = z0
        self.current_gain = current_gain
        self.bearing = current_bearing_deg

    def height(self, t_s):
        h = self.z0
        for name, (a, g) in self.c.items():
            h += a * math.cos(_omega(name) * t_s - g)
        return h

    def height_rate(self, t_s):
        """dh/dt [m/s] analytically."""
        r = 0.0
        for name, (a, g) in self.c.items():
            w = _omega(name)
            r += -a * w * math.sin(w * t_s - g)
        return r

    def current(self, t_s):
        """Tidal-stream (speed_mps, bearing_deg). Flood/ebb flips the bearing by
        180 deg with the sign of dh/dt -- the behaviour a fixed vector can't model."""
        rate = self.height_rate(t_s)
        speed = abs(rate) * self.current_gain
        bearing = self.bearing if rate >= 0 else (self.bearing + 180.0) % 360.0
        return speed, bearing


def demo_mumbai():
    """Illustrative mixed semidiurnal model for the Mumbai approaches (NOT a real
    tide-table fit -- replace amplitudes/phases with a TPXO/FES extraction for
    Tier B)."""
    return TidalModel(
        constituents={"M2": (1.6, 120.0), "S2": (0.6, 150.0), "K1": (0.5, 300.0), "O1": (0.3, 280.0)},
        z0=2.5, current_bearing_deg=20.0,
    )
