"""Bathymetry source (Axis 2.1, Tier B). Real seabed depth under a position so
the scenario engine's `grounding` / `nogo_breach` consequences become physical
instead of geometric.

Two real ingest paths + an honest fallback:
  * from_csv(path): a 'lon lat depth' (or comma) grid -- pure stdlib, so a site
    can reach Tier B with a lightweight extract and NO heavy GIS deps.
  * from_gebco(path): a GEBCO NetCDF grid IF netCDF4 is installed; if it is not,
    it says so and falls back to flat depth rather than pretending.
  * default: flat depth from the site's max_depth (Tier A).
"""
import math
import os


class BathymetrySource:
    def __init__(self, default_depth_m=45.0, source="fallback-flat"):
        self.default = default_depth_m
        self.grid = None            # list of (lon, lat, depth_m_positive_down)
        self.source = source

    @classmethod
    def from_csv(cls, path, default_depth_m=45.0):
        obj = cls(default_depth_m, source=f"csv:{os.path.basename(path)}")
        pts = []
        with open(path) as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                p = ln.replace(",", " ").split()
                if len(p) < 3:
                    continue
                try:
                    lon, lat, depth = float(p[0]), float(p[1]), float(p[2])
                except ValueError:
                    continue
                pts.append((lon, lat, abs(depth)))   # store positive-down
        obj.grid = pts or None
        return obj

    @classmethod
    def from_gebco(cls, path, default_depth_m=45.0):
        try:
            from netCDF4 import Dataset  # noqa: F401
        except Exception:
            return cls(default_depth_m, source="gebco-unavailable(netCDF4 not installed)->flat")
        from netCDF4 import Dataset
        ds = Dataset(path)
        lats = ds.variables["lat"][:]
        lons = ds.variables["lon"][:]
        elev = ds.variables["elevation"]     # GEBCO: metres, negative below sea level
        obj = cls(default_depth_m, source=f"gebco:{os.path.basename(path)}")
        obj._gebco = (lats, lons, elev)
        return obj

    def depth_at(self, lat, lon):
        g = getattr(self, "_gebco", None)
        if g is not None:
            lats, lons, elev = g
            i = min(range(len(lats)), key=lambda k: abs(lats[k] - lat))
            j = min(range(len(lons)), key=lambda k: abs(lons[k] - lon))
            return max(0.0, -float(elev[i, j]))
        if self.grid:
            best, bd = None, 1e18
            for glon, glat, d in self.grid:
                dd = (glon - lon) ** 2 + (glat - lat) ** 2
                if dd < bd:
                    bd, best = dd, d
            return best if best is not None else self.default
        return self.default

    def grounding_risk(self, lat, lon, draft_m):
        """True if the hull's draft meets/exceeds the water depth here."""
        return self.depth_at(lat, lon) <= draft_m
