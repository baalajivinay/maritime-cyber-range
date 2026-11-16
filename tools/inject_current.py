#!/usr/bin/env python3
"""Inject an Indian test-site's ocean current into the LIVE Gazebo sim.

The twins already run gz-sim-hydrodynamics, which drags the hull relative to the
water. This publishes the site's current (converted to the Gazebo ENU world
frame) to the plugin's `/ocean_current` topic, so a BOOTED twin physically
drifts with that water body -- the real-sim counterpart of the scenario engine's
current advection. No SDF or plugin change needed.

Run it alongside a booted twin (same Gazebo transport domain):

  python3 tools/inject_current.py --site kochi        # hold Kochi's current
  python3 tools/inject_current.py --site mumbai --once # set once and exit
  python3 tools/inject_current.py --off               # zero the current

Scale-up tool -- not part of the shipped package's default boot.
"""
import argparse
import math
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from scaleup.sites import load_site
from scaleup.physics.tides import demo_mumbai, TidalModel

TOPIC = "/ocean_current"   # gz-sim-hydrodynamics default current topic


def publish(east, north, topic=TOPIC):
    # Gazebo world is ENU: x=East, y=North, z=Up.
    subprocess.run(
        ["gz", "topic", "-t", topic, "-m", "gz.msgs.Vector3d",
         "-p", f"x: {east:.4f}, y: {north:.4f}, z: 0.0"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default=os.environ.get("MCR_SITE"),
                    help="kochi | visakhapatnam | mumbai (or set MCR_SITE)")
    ap.add_argument("--off", action="store_true", help="zero the current and exit")
    ap.add_argument("--once", action="store_true", help="publish once and exit (plugin holds the value)")
    ap.add_argument("--tides", action="store_true", help="enable dynamic harmonic M2 tidal stream modulation")
    ap.add_argument("--interval", type=float, default=2.0, help="republish period seconds (default 2)")
    ap.add_argument("--topic", default=TOPIC)
    args = ap.parse_args()

    if args.off:
        publish(0.0, 0.0, args.topic)
        print("[inject_current] current zeroed.")
        return
    if not args.site:
        ap.error("give --site <kochi|visakhapatnam|mumbai> or set MCR_SITE")

    site = load_site(args.site)
    tidal_model = demo_mumbai() if (args.tides or args.site.lower() == "mumbai") else None

    if tidal_model:
        print(f"[inject_current] {site.name}: dynamic harmonic tidal constituent active (M2/S2/K1/O1)")
    else:
        spd = site.current["speed_mps"]
        brg = site.current["bearing_deg"]
        print(f"[inject_current] {site.name}: {spd:.2f} m/s @ {brg:.0f} deg (static vector)")

    t0 = time.time()
    def get_ne(elapsed):
        if tidal_model:
            spd, brg = tidal_model.current(elapsed)
            rad = math.radians(brg)
            return spd * math.cos(rad), spd * math.sin(rad), spd, brg
        n, e = site.current_ne()
        return n, e, site.current["speed_mps"], site.current["bearing_deg"]

    n, e, spd, brg = get_ne(0.0)
    print(f"[inject_current] initial -> ENU (E={e:.3f}, N={n:.3f}) on {args.topic}")
    publish(e, n, args.topic)
    if args.once:
        print("[inject_current] published once.")
        return
    print("[inject_current] holding/modulating current (Ctrl-C to stop; run --off to zero) ...")
    try:
        while True:
            time.sleep(args.interval)
            elapsed = time.time() - t0
            n, e, spd, brg = get_ne(elapsed)
            publish(e, n, args.topic)
    except KeyboardInterrupt:
        print("\n[inject_current] stopped (current left at last value; run --off to zero).")


if __name__ == "__main__":
    main()
