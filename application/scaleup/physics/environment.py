"""Site -> physics binding (Axis 2.x, "use the dataset we already have").

The physics models (seastate, acoustics, sensors, ingest) each take raw numbers.
This binds them to a TEST SITE's dataset so sea state, sound speed, density,
current and the sensor error envelopes ALL come from the SAME site numbers --
instead of each model carrying its own generic default. One object, one source
of truth, consumed by the tester, the detectors' noise floor, and the report.

Climbing the fidelity ladder is now a DATA swap, not a code change:
  * Tier A (today): the site's representative climatology (water block in
    scaleup/sites/data/<site>.json).
  * Tier B: drop a measured CTD cast / ADCP current / multibeam bathymetry into
    the site (or via ingest.OceanProfile.from_csv) -- the SAME equations consume
    the better inputs, and this binding passes them to every model unchanged.

Stdlib only.
"""
from .seastate import WaveField
from .acoustics_bellhop import AcousticChannel
from .sensors import GnssErrorModel, DvlErrorModel, ImuErrorModel, MagErrorModel
from .ingest import OceanProfile


class Environment:
    """The physics of one site, bound to the models. Build with
    Environment.from_site("kochi")."""

    def __init__(self, site, seed=0):
        self.site = site
        self.seed = seed

    @classmethod
    def from_site(cls, site_or_id, seed=0):
        if isinstance(site_or_id, str):
            from scaleup.sites import load_site
            site = load_site(site_or_id)
        else:
            site = site_or_id
        return cls(site, seed)

    # --- scalars straight from the site dataset ------------------------------
    def density(self):
        return self.site.density()

    def surface_sound_speed(self):
        return self.site.surface_sound_speed()

    def sound_speed_profile(self):
        return self.site.sound_speed_profile()

    def current_ne(self):
        return self.site.current_ne()

    def water_depth_m(self):
        return self.site.water["max_depth_m"]

    def _is_harbour(self):
        txt = (self.site.name + " " + self.site.region + " " + self.site.notes).lower()
        return "harbour" in txt or "harbor" in txt or "approach" in txt or "traffic" in txt

    # --- models, parameterised by the site ----------------------------------
    def wave_field(self):
        ss = self.site.sea_state
        return WaveField(hs=ss["sig_wave_height_m"], tp=ss["period_s"], seed=self.seed)

    def acoustic_channel(self, src_depth_m=5.0, rcv_depth_m=10.0):
        a = self.site.acoustics
        return AcousticChannel(water_depth_m=self.water_depth_m(), src_depth_m=src_depth_m,
                               rcv_depth_m=rcv_depth_m, freq_khz=a["usbl_freq_khz"],
                               sound_speed_mps=self.surface_sound_speed())

    def ocean_profile(self):
        w = self.site.water
        return OceanProfile.representative(w["surface_temp_c"], w["salinity_psu"], w["max_depth_m"])

    def gnss(self):
        # Harbour/approach sites carry heavier GNSS multipath than open shelf.
        return GnssErrorModel(multipath_m=4.0 if self._is_harbour() else 2.0, seed=self.seed)

    def dvl(self):
        # Bottom-lock dropout envelope keyed to this site's water depth.
        return DvlErrorModel(max_altitude_m=self.water_depth_m(), seed=self.seed)

    def imu(self):
        return ImuErrorModel(seed=self.seed)

    def mag(self):
        return MagErrorModel(seed=self.seed)

    # --- one dict for reports / verdict stamping -----------------------------
    def summary(self):
        a = self.site.acoustics
        ch = self.acoustic_channel()
        try:
            usbl_range = round(ch.detection_range_m(a["source_level_db"], a["det_threshold_db"]), 0)
        except Exception:
            usbl_range = None
        return {
            "site": self.site.id,
            "name": self.site.name,
            "fidelity_tier": self.site.water.get("fidelity", "A") + " (representative site climatology)",
            "water_density_kg_m3": round(self.density(), 1),
            "surface_sound_speed_mps": round(self.surface_sound_speed(), 1),
            "sea_state_hs_m": self.site.sea_state["sig_wave_height_m"],
            "sea_state_tp_s": self.site.sea_state["period_s"],
            "water_depth_m": self.water_depth_m(),
            "acoustic_engine": ch.engine,
            "acoustic_fidelity": ch.tier,
            "usbl_freq_khz": a["usbl_freq_khz"],
            "usbl_detection_range_m": usbl_range,
            "current_speed_mps": self.site.current["speed_mps"],
            "current_ne_mps": [round(x, 3) for x in self.current_ne()],
            "gnss_multipath_m": 4.0 if self._is_harbour() else 2.0,
        }
