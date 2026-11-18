"""Self-contained geodesy helpers for the scenario engine.

Deliberately NOT imported from detection/ or constants/ -- the scale-up code
stays additive and standalone so it can never perturb the shipped package.
Stdlib only (math). Equirectangular meters approximation, good for the
harbour-scale distances these scenarios cover.
"""
import math

M_PER_DEG_LAT = 111320.0


def m_per_deg_lon(lat):
    return M_PER_DEG_LAT * math.cos(math.radians(lat))


def horiz_m(lat1, lon1, lat2, lon2):
    """Horizontal distance in metres between two lat/lon points."""
    dn = (lat2 - lat1) * M_PER_DEG_LAT
    de = (lon2 - lon1) * m_per_deg_lon((lat1 + lat2) / 2.0)
    return math.hypot(dn, de)


def offset_m(lat, lon, north_m, east_m):
    """Return (lat, lon) displaced by north_m / east_m metres."""
    return (lat + north_m / M_PER_DEG_LAT,
            lon + east_m / m_per_deg_lon(lat))


def point_in_polygon(lat, lon, polygon):
    """Ray-casting point-in-polygon. `polygon` is [[lat, lon], ...] (the first
    and last vertex need not repeat). Works in lat/lon directly, which is fine
    for the small, non-polar areas these no-go zones cover."""
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i][0], polygon[i][1]     # lat, lon
        yj, xj = polygon[j][0], polygon[j][1]
        if ((yi > lat) != (yj > lat)) and \
           (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside
