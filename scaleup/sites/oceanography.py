"""Ocean physics -- the EXACT formulas used in real ocean acoustics & oceanography.

These are not approximations invented here; they are the standard published
equations. "As exact as software gets" means: exact equations, driven by inputs
that are REPRESENTATIVE regional climatology now and REAL measured data later
(same equations, better inputs). Each function cites its source.

Fidelity ladder (see scaleup/sites/README.md):
  A. exact equation + representative input  <- implemented here, now
  B. exact equation + real measured input   <- INCOIS/WOA/GEBCO/CTD ingest
  C. validated against NSTL/NPOL trial data  <- partnership

Stdlib only (math).
"""
import math


# --- Speed of sound in seawater: Mackenzie (1981) 9-term equation -----------
# K.V. Mackenzie, "Nine-term equation for sound speed in the oceans",
# J. Acoust. Soc. Am. 70(3), 1981. Valid 2-30 C, 25-40 ppt, 0-8000 m.
def sound_speed_mackenzie(temp_c, salinity_psu, depth_m):
    t, s, d = temp_c, salinity_psu, depth_m
    return (1448.96 + 4.591 * t - 5.304e-2 * t**2 + 2.374e-4 * t**3
            + 1.340 * (s - 35.0) + 1.630e-2 * d + 1.675e-7 * d**2
            - 1.025e-2 * t * (s - 35.0) - 7.139e-13 * t * d**3)


# --- Seawater density at 1 atm: UNESCO EOS-80 (Millero & Poisson 1981) -------
# One-atmosphere International Equation of State of Seawater, 1980.
def density_eos80(temp_c, salinity_psu):
    t, s = temp_c, salinity_psu
    rho_w = (999.842594 + 6.793952e-2 * t - 9.095290e-3 * t**2
             + 1.001685e-4 * t**3 - 1.120083e-6 * t**4 + 6.536336e-9 * t**5)
    A = (8.24493e-1 - 4.0899e-3 * t + 7.6438e-5 * t**2
         - 8.2467e-7 * t**3 + 5.3875e-9 * t**4)
    B = -5.72466e-3 + 1.0227e-4 * t - 1.6546e-6 * t**2
    C = 4.8314e-4
    return rho_w + A * s + B * s**1.5 + C * s**2


# --- Acoustic absorption: Thorp's formula -----------------------------------
# W.H. Thorp, absorption of low-frequency sound in sea water. f in kHz ->
# attenuation in dB/km. Standard form used for sonar-range budgeting.
def thorp_absorption_db_per_km(freq_khz):
    f = freq_khz
    return (0.11 * f**2 / (1 + f**2) + 44.0 * f**2 / (4100.0 + f**2)
            + 2.75e-4 * f**2 + 0.003)


# --- Transmission loss (passive one-way): spreading + absorption -------------
# TL(dB) = k*log10(r) + alpha*r,  k=20 spherical (deep), 10 cylindrical (ducted).
def transmission_loss_db(range_m, freq_khz, spreading="spherical"):
    if range_m <= 1:
        return 0.0
    k = 20.0 if spreading == "spherical" else 10.0
    alpha = thorp_absorption_db_per_km(freq_khz)          # dB/km
    return k * math.log10(range_m) + alpha * (range_m / 1000.0)


# --- Detection range for an acoustic positioning link -----------------------
def detection_range_m(source_level_db, det_threshold_db, freq_khz, spreading="spherical"):
    """Largest range whose one-way TL still leaves signal above threshold.
    SL - TL >= DT  ->  solve TL = SL - DT. Simple bisection (monotonic TL)."""
    budget = source_level_db - det_threshold_db
    if budget <= 0:
        return 0.0
    lo, hi = 1.0, 200000.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if transmission_loss_db(mid, freq_khz, spreading) < budget:
            lo = mid
        else:
            hi = mid
    return round(0.5 * (lo + hi), 1)


# --- Temperature profile -> sound-speed profile -----------------------------
def temperature_at_depth(d, surface_temp, deep_temp, mixed_layer_m, thermocline_bottom_m):
    """3-layer T(d): isothermal mixed layer, linear thermocline, isothermal deep."""
    if d <= mixed_layer_m:
        return surface_temp
    if d >= thermocline_bottom_m:
        return deep_temp
    frac = (d - mixed_layer_m) / max(thermocline_bottom_m - mixed_layer_m, 1e-6)
    return surface_temp + frac * (deep_temp - surface_temp)


def sound_speed_profile(surface_temp, deep_temp, salinity_psu, max_depth_m,
                        mixed_layer_m=20.0, thermocline_bottom_m=200.0, n=40):
    """Return [(depth_m, c_mps, temp_c), ...] from the surface to max_depth.
    The c-profile's shape (surface duct / thermocline minimum) is exactly what
    governs sonar ducting -- computed via Mackenzie at each depth."""
    out = []
    for i in range(n + 1):
        d = max_depth_m * i / n
        t = temperature_at_depth(d, surface_temp, deep_temp, mixed_layer_m, thermocline_bottom_m)
        out.append((round(d, 1), round(sound_speed_mackenzie(t, salinity_psu, d), 2), round(t, 2)))
    return out


def sonic_layer_depth(profile):
    """Depth of the sound-speed maximum in the upper water column -- the base of
    the surface duct (a signature acoustic feature for sonar/USBL)."""
    if not profile:
        return None
    best = max(profile, key=lambda p: p[1])
    return best[0]
