"""Indian test-site framework (additive, default-off).

Three selectable water bodies -- Kochi (NPOL), Visakhapatnam (NSTL), Mumbai
(WNC) -- each a cited ENVIRONMENT (current, density, sound-speed, bathymetry)
computed with exact ocean-physics equations (see oceanography.py). Every site
supports every attack; the site changes the water, not the attack set.
"""
from .oceanography import (sound_speed_mackenzie, density_eos80,
                           thorp_absorption_db_per_km, transmission_loss_db,
                           detection_range_m, sound_speed_profile)
from .sites import Site, load_site, list_sites

__all__ = ["Site", "load_site", "list_sites",
           "sound_speed_mackenzie", "density_eos80", "thorp_absorption_db_per_km",
           "transmission_loss_db", "detection_range_m", "sound_speed_profile"]
