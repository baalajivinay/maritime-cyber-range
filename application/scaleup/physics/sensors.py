"""Realistic sensor error models (Axis 2.3).

Everything downstream of a sensor in this range is currently near-ideal, which
means the blind detectors' thresholds (the GPS jump gate, the 0.15 m/s acoustic-
drift gate, ...) are not calibrated against a realistic noise floor. These models
add the error a REAL sensor exhibits, so "did the detector fire" means "did it
fire above genuine noise", not "above nothing".

Stdlib only (random, math). Every model takes a seed for reproducible runs and
separates SLOWLY-CORRELATED error (bias, multipath, random walk) from white
noise -- the distinction that actually fools or doesn't fool a drift detector.
"""
import math
import random

_M_PER_DEG_LAT = 111320.0


class _OU:
    """Ornstein-Uhlenbeck process: a mean-reverting correlated random walk --
    the right shape for multipath/ionospheric wander and sensor bias drift."""
    def __init__(self, sigma, tau_s, rng):
        self.sigma, self.tau = sigma, max(tau_s, 1e-3)
        self.rng = rng
        self.x = 0.0

    def step(self, dt):
        a = math.exp(-dt / self.tau)
        self.x = a * self.x + math.sqrt(max(0.0, 1 - a * a)) * self.sigma * self.rng.gauss(0, 1)
        return self.x


class GnssErrorModel:
    """GNSS horizontal error = correlated multipath/iono wander + white noise.
    Typical open-sky: ~1-3 m CEP; urban/harbour multipath inflates the correlated
    term. Returns (d_north_m, d_east_m) to add to a true position."""
    def __init__(self, multipath_m=2.5, white_m=0.4, tau_s=90.0, seed=0):
        rng = random.Random(seed)
        self.mp_n = _OU(multipath_m, tau_s, rng)
        self.mp_e = _OU(multipath_m, tau_s, rng)
        self.white = white_m
        self.rng = rng

    def error_m(self, dt=1.0):
        return (self.mp_n.step(dt) + self.rng.gauss(0, self.white),
                self.mp_e.step(dt) + self.rng.gauss(0, self.white))

    def perturb(self, lat, lon, dt=1.0):
        dn, de = self.error_m(dt)
        return (lat + dn / _M_PER_DEG_LAT,
                lon + de / (_M_PER_DEG_LAT * math.cos(math.radians(lat))))


class ImuErrorModel:
    """Gyro/accel bias (constant per power-cycle) + bias random walk + white
    noise. Gyro bias in rad/s, accel in m/s^2. Defaults ~ a decent MEMS unit."""
    def __init__(self, gyro_bias=5e-3, gyro_arw=3e-4, accel_bias=0.02, accel_vrw=1.5e-3, seed=0):
        rng = random.Random(seed)
        self.rng = rng
        self.gyro_b0 = rng.gauss(0, gyro_bias)
        self.accel_b0 = rng.gauss(0, accel_bias)
        self.gyro_walk = _OU(gyro_bias, 300.0, rng)
        self.accel_walk = _OU(accel_bias, 300.0, rng)
        self.gyro_arw, self.accel_vrw = gyro_arw, accel_vrw

    def gyro_error(self, dt=1.0):
        return self.gyro_b0 + self.gyro_walk.step(dt) + self.rng.gauss(0, self.gyro_arw / math.sqrt(dt))

    def accel_error(self, dt=1.0):
        return self.accel_b0 + self.accel_walk.step(dt) + self.rng.gauss(0, self.accel_vrw / math.sqrt(dt))


class DvlErrorModel:
    """Doppler Velocity Log: bottom-lock dropout rises as depth approaches the
    instrument's max altitude; velocity has a scale-factor error + white noise.
    locked(depth) tells you whether a fix exists this ping (a dropout is itself a
    detectable/missing-data event)."""
    def __init__(self, max_altitude_m=50.0, scale_err=0.004, white_mps=0.01, seed=0):
        self.max_alt, self.scale, self.white = max_altitude_m, scale_err, white_mps
        self.rng = random.Random(seed)

    def locked(self, altitude_m):
        if altitude_m <= 0:
            return True
        p_drop = min(0.95, max(0.0, (altitude_m - 0.6 * self.max_alt) / (0.4 * self.max_alt)))
        return self.rng.random() > p_drop

    def perturb_velocity(self, v_mps):
        return v_mps * (1.0 + self.rng.gauss(0, self.scale)) + self.rng.gauss(0, self.white)


class MagErrorModel:
    """Magnetometer heading error: hard-iron offset (fixed) + soft-iron + noise,
    reported as a heading error in radians."""
    def __init__(self, hard_iron_deg=4.0, noise_deg=0.8, seed=0):
        rng = random.Random(seed)
        self.offset = math.radians(rng.gauss(0, hard_iron_deg))
        self.noise = math.radians(noise_deg)
        self.rng = rng

    def heading_error(self):
        return self.offset + self.rng.gauss(0, self.noise)
