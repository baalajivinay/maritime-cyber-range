#!/usr/bin/env python3
"""Inspect / compare the Indian test sites' computed environment physics.

Scale-up tool (not in the shipped package's default flow).

  python3 tools/site_info.py                 # compare all 3 sites
  python3 tools/site_info.py kochi --json     # one site, full environment JSON
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from scaleup.sites import load_site, list_sites


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", nargs="?", help="kochi | visakhapatnam | mumbai (omit = compare all)")
    ap.add_argument("--json", action="store_true", help="print the full computed-environment JSON")
    args = ap.parse_args()

    if args.site:
        env = load_site(args.site).environment()
        if args.json:
            print(json.dumps(env, indent=2))
        else:
            for k, v in env.items():
                if k == "profile":
                    v = f"{len(v)} depth points"
                print(f"  {k:<26} {v}")
        return

    sites = list_sites()
    print(f"{'site':<15}{'ρ kg/m³':>9}{'c0 m/s':>9}{'SLD m':>7}{'USBL km':>9}{'cur m/s':>9}  establishment")
    print("-" * 100)
    for s in sites:
        e = s.environment()
        print(f"{s.id:<15}{e['water_density_kg_m3']:>9.2f}{e['surface_sound_speed_mps']:>9.1f}"
              f"{e['sonic_layer_depth_m']:>7.0f}{e['usbl_detection_range_m']/1000:>9.2f}"
              f"{e['current_speed_mps']:>9.2f}  {s.establishment[:46]}")
    print("\nEvery site supports every attack; the site sets the water, not the attack set.")
    print("Fidelity: exact equations (Mackenzie/EOS-80/Thorp) + representative regional climatology.")


if __name__ == "__main__":
    main()
