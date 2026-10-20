"""Sea state via the JONSWAP wave spectrum (Axis 2.4).

The hydrodynamics plugin currently sees a flat sea. Real surface vehicles are
disturbed by waves, and the resulting motion is exactly the noise a GPS-jump or
acoustic-drift detector has to see through. JONSWAP (Hasselmann et al. 1973) is
the standard fetch-limited spectrum used for ship-motion and offshore work.

Stdlib only. Produces the spectral density S(f), recovers significant wave
height from it (closing the loop as a test), and synthesises a time-domain
surface elevation + a slow wave-drift velocity the range can inject onto the
hull the same way tools/inject_current.py injects ocean current.
"""
import math
import random

_G = 9.81


def jonswap(f, hs, tp, gamma=3.3):
    """Spectral density S(f) [m^2/Hz] at frequency f [Hz] for significant wave
    height hs [m] and peak period tp [s]. gamma=3.3 is the mean JONSWAP peak."""
    if f <= 0:
        return 0.0
    fp = 1.0 / tp
    sigma = 0.07 if f <= fp else 0.09
    r = math.exp(-((f - fp) ** 2) / (2 * sigma * sigma * fp * fp))
    # Pierson-Moskowitz base, scaled by the JONSWAP peak-enhancement gamma^r.
    # The (1 - 0.287 ln gamma) factor normalises the peak enhancement so total
    # energy (and therefore the recovered Hs) is conserved -- the standard form.
    alpha = 5.0 / 16.0 * hs * hs * fp ** 4
    s_pm = alpha * f ** -5 * math.exp(-1.25 * (fp / f) ** 4)
    norm = 1.0 - 0.287 * math.log(gamma)
    return norm * s_pm * gamma ** r


def spectrum(hs, tp, gamma=3.3, f_lo=0.02, f_hi=0.6, n=256):
    """Discrete spectrum as (freqs, S, df)."""
    df = (f_hi - f_lo) / n
    freqs = [f_lo + (i + 0.5) * df for i in range(n)]
    return freqs, [jonswap(f, hs, tp, gamma) for f in freqs], df


def significant_wave_height(freqs, S, df):
    """Hs = 4*sqrt(m0), m0 = integral of S df. Recovers the input Hs -- the test."""
    m0 = sum(s * df for s in S)
    return 4.0 * math.sqrt(m0)


class WaveField:
    """Sum-of-sines realisation of a JONSWAP sea with random phases. Gives the
    surface elevation eta(t) and a slow wave-drift speed (a small fraction of
    orbital velocity) usable as a hull disturbance injected like ocean current."""
    def __init__(self, hs, tp, gamma=3.3, direction_deg=0.0, seed=0, n_components=64):
        self.direction = direction_deg
        freqs, S, df = spectrum(hs, tp, gamma, n=n_components)
        rng = random.Random(seed)
        self.comps = [(f, math.sqrt(2 * s * df), rng.uniform(0, 2 * math.pi), 2 * math.pi * f)
                      for f, s in zip(freqs, S)]
        self.hs, self.tp = hs, tp

    def elevation(self, t):
        return sum(a * math.cos(w * t + ph) for (_f, a, ph, w) in self.comps)

    def drift_velocity(self, t):
        """Stokes-like slow drift magnitude [m/s] along the wave direction --
        a bounded, sea-state-scaled disturbance for the hull."""
        # ~ small fraction of peak orbital velocity; bounded and smooth.
        orb = math.pi * self.hs / self.tp
        slow = 0.02 * orb * (1.0 + 0.5 * math.sin(2 * math.pi * t / (6 * self.tp)))
        return slow, self.direction
