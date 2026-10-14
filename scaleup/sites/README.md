# Indian test-site framework — real ocean physics, cited

Three selectable water bodies, each a **cited environment** (current, density,
sound-speed, bathymetry) computed with the **exact equations** real ocean-acoustics
and oceanography use. **Every site supports every attack** — a site is a physics
*environment* overlay, orthogonal to the attack set. Pick a site to change the
water the vehicle sits in, not what you can do to it.

| Site | Establishment | Water body |
|---|---|---|
| **Kochi** | Southern Naval Command · NPOL (sonar/acoustics) | Arabian Sea shelf |
| **Visakhapatnam** | Eastern Naval Command · NSTL (UUV hydrodynamics) | Bay of Bengal shelf |
| **Mumbai** | Western Naval Command | Arabian Sea harbour approaches |

## What's exact vs. what's representative (be honest about this)

The **equations are exact** — the same ones used in the field, verified against
their published reference values (`scaleup/tests/test_sites.py`):

| Quantity | Equation | Verified against |
|---|---|---|
| Sound speed | **Mackenzie (1981)** 9-term | paper's own check: c(25 °C,35,1000 m)=1550.744 m/s ✓ |
| Seawater density | **UNESCO EOS-80** (Millero-Poisson 1981) | ρ(25,35)=1023.343, ρ(0,35)=1028.106 ✓ |
| Acoustic absorption | **Thorp** | monotonic in frequency ✓ |
| Transmission loss | spreading + absorption | — |

The **inputs are representative regional climatology** (INCOIS / World Ocean
Atlas means, GEBCO depth) — typical values, not a measured cast for a given day.
So each site's density, sound-speed profile, USBL range and current are *real
physics on representative water*. The Bay-of-Bengal low-salinity freshening, for
instance, correctly makes Visakhapatnam **less dense** than Kochi/Mumbai.

### Fidelity ladder
- **Tier A (here, now):** exact equation + representative climatology input.
- **Tier B (next):** exact equation + **real measured input** — ingest INCOIS
  current/tide fields, GEBCO bathymetry, and CTD casts (→ real sound-speed).
- **Tier C:** **validated** against NSTL/NPOL trial data (partnership).

Nothing here claims Tier C; the framework is built to climb to it.

## How the site affects a run

The water **current advects the hull** in the scenario engine (first-order; the
position-spoofed vehicle doesn't reject the current). The *same* attack scenario
therefore yields *different* mission outcomes at different sites — e.g. Kochi's
SSE coastal current drives a GPS-walked hull into the shoal (grounding) while
Visakhapatnam's / Mumbai's currents carry it clear.

```bash
python3 tools/run_scenario.py scenarios/harbor_transit_gps_walkoff.json --site kochi --out out_k
python3 tools/run_scenario.py scenarios/harbor_transit_gps_walkoff.json --site visakhapatnam --out out_v
python3 tools/site_info.py                      # compare all three environments
python3 tools/site_info.py kochi --json          # full computed environment
python3 scaleup/tests/test_sites.py              # physics + site tests
```

The visual report gains a **Test-site environment** section: a cited physics
table + a computed **sound-speed profile** (the sonic-layer depth that governs
sonar/USBL ducting), and a current vector on the tactical map.

## Feeding it into the live Gazebo sim (integration notes)

- **Current → vehicle:** apply as a body force in Gazebo. For the AUV, the DAVE
  ocean-current plugin; for the surface hull, a drift force. The site's
  `current_ne()` gives the vector. (World-SDF change → ships via release flow.)
- **Density → buoyancy:** the world `<density>` / the hull buoyancy uses
  `site.density()` instead of a fixed 1025.
- **Sound-speed → acoustic attack:** `acoustic_spoof.py`'s USBL range/geometry
  uses the site profile; `transmission_loss_db()` bounds plausible spoof range.
- **Bathymetry/sea-state:** Tier-B GEBCO heightmap + the Gazebo wave plugin.

## Files
`oceanography.py` (the equations) · `sites.py` (Site model + derived physics) ·
`data/*.json` (cited site data) · consumed by `scaleup/scenario` and
`tools/{run_scenario,site_info}.py`.
