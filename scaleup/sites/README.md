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

## Feeding it into the live Gazebo sim

- **Current → vehicle: IMPLEMENTED.** The twins already run
  `gz-sim-hydrodynamics`, which drags the hull relative to the water. The site's
  current (ENU world frame) is published to the plugin's `/ocean_current` topic
  by `tools/inject_current.py`, so a **booted twin physically drifts** with that
  water body -- no SDF or plugin change. Verified live: Kochi's 160° current
  drifts the CUSV hull south.
  ```bash
  tools/run_vehicle.sh vehicle_twins/mass_vulnerable_cusv up    # boot a twin
  python3 tools/inject_current.py --site kochi                   # hold its current
  python3 tools/inject_current.py --off                          # zero it
  ```
  Honest limits (Tier A): a **uniform, steady** current. Spatially-varying /
  tidal time-series (INCOIS fields, via the plugin's water-current table) is
  Tier B. An actively-navigating autopilot partially rejects the current
  (realistic); a disarmed/low-thrust hull drifts with it.
- **Density → buoyancy: IMPLEMENTED.** When `MCR_SITE` is set, `run_sim.sh`
  patches the world buoyancy `<default_density>` to `site.density()` (EOS-80) in
  a per-session world copy, so buoyant force uses the real site density.
  Verified live: Kochi → the CUSV world goes from freshwater 1000 to 1022.4 kg/m³.
  ```bash
  MCR_SITE=kochi tools/run_vehicle.sh vehicle_twins/mass_vulnerable_cusv up
  ```
  Honest note: seawater density varies <1%, so the buoyant-force effect is small
  (mainly correctness + a slight trim shift for a neutrally-buoyant AUV).
- **Sound-speed → acoustic attack: IMPLEMENTED (site-aware bounds).** With
  `MCR_SITE` set, `attacks/acoustic_spoof.py` loads the site, reports the sound
  speed, and **bounds the forged USBL offset to the site's acoustic detection
  range** (a fix beyond it is implausible). Honest limit: the sim injects
  position directly — it has **no modelled acoustic travel-time channel** — so
  the sound speed informs the attack's *plausibility / detectability* bounds
  (detection range, ranging bias) rather than the injected value. Ray-traced
  travel-time ranging & multipath (**Bellhop**) is the Tier-B upgrade.
- **Bathymetry / sea-state** (Tier B): GEBCO heightmap + the Gazebo wave plugin.

## Files
`oceanography.py` (the equations) · `sites.py` (Site model + derived physics) ·
`data/*.json` (cited site data) · consumed by `scaleup/scenario` and
`tools/{run_scenario,site_info}.py`.
