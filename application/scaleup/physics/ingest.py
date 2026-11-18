"""Ocean profile ingest (Axis 2.1, Tier B). Turns a real CTD / World-Ocean-Atlas
/ INCOIS depth profile into the temperature & salinity inputs the EXACT
oceanography equations already use -- the literal definition of climbing the
fidelity ladder: "same equations, better inputs".

from_csv ingests 'depth,temp,salinity' rows (pure stdlib). representative()
builds a Tier-A profile from a site's surface values so callers always have
something. Either way, sound_speed()/density() defer to
scaleup/sites/oceanography.py so there is one source of truth for the physics.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from scaleup.sites import oceanography as O


class OceanProfile:
    def __init__(self, samples, source="representative", tier="A"):
        # samples: list of (depth_m, temp_c, salinity_psu), sorted by depth
        self.samples = sorted(samples, key=lambda s: s[0])
        self.source = source
        self.tier = tier

    @classmethod
    def from_csv(cls, path):
        rows = []
        with open(path) as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#") or ln.lower().startswith("depth"):
                    continue
                p = ln.replace(",", " ").split()
                if len(p) < 3:
                    continue
                try:
                    rows.append((float(p[0]), float(p[1]), float(p[2])))
                except ValueError:
                    continue
        return cls(rows or [(0.0, 20.0, 35.0)],
                   source=f"csv:{os.path.basename(path)}", tier="B")

    @classmethod
    def representative(cls, surf_temp_c, surf_salinity_psu, max_depth_m=60.0):
        """A simple stratified Tier-A profile: a warm mixed layer over a cooler,
        slightly saltier deep -- enough to exercise the SSP-driven acoustics."""
        return cls([
            (0.0, surf_temp_c, surf_salinity_psu),
            (max_depth_m * 0.3, surf_temp_c - 1.5, surf_salinity_psu + 0.1),
            (max_depth_m, surf_temp_c - 4.0, surf_salinity_psu + 0.3),
        ], source="representative-stratified", tier="A")

    def at(self, depth_m):
        """Linearly interpolate (temp, salinity) at depth."""
        s = self.samples
        if depth_m <= s[0][0]:
            return s[0][1], s[0][2]
        if depth_m >= s[-1][0]:
            return s[-1][1], s[-1][2]
        for (d0, t0, sa0), (d1, t1, sa1) in zip(s, s[1:]):
            if d0 <= depth_m <= d1:
                f = (depth_m - d0) / (d1 - d0) if d1 > d0 else 0.0
                return t0 + f * (t1 - t0), sa0 + f * (sa1 - sa0)
        return s[-1][1], s[-1][2]

    def sound_speed(self, depth_m):
        t, sa = self.at(depth_m)
        return O.sound_speed_mackenzie(t, sa, depth_m)

    def density_surface(self):
        t, sa = self.at(0.0)
        return O.density_eos80(t, sa)

    def sound_speed_profile(self, step_m=5.0):
        """(depths, speeds) sampled through the column -- feeds AcousticChannel."""
        dmax = self.samples[-1][0]
        depths, speeds, d = [], [], 0.0
        while d <= dmax:
            depths.append(d)
            speeds.append(self.sound_speed(d))
            d += step_m
        return depths, speeds
