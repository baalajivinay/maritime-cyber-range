#!/usr/bin/env python3
"""Twin x site resilience matrix -- the tool the multi-site framework was
missing. Boots each (twin, site) combination headless, runs
tools/test_target.py against it, tears the stack down, and aggregates one
verdict matrix with a site-invariance check.

The framework's central claim is that the SECURITY verdict is site-invariant
(a vulnerability is a property of the autopilot config, not of the water) while
the PHYSICS differs per site. This tool demonstrates that run-over-run instead
of asserting it: it prints each combination's verdicts + per-attack detector
alerts, then reports, per twin, whether the verdicts were INVARIANT across the
sites tested.

Defaults to the two vulnerable twins across all three sites (6 boots), since the
resilient twins' verdicts are also site-invariant and the vulnerable ones are
where the per-site GPS/acoustic physics actually exercises a positive result.
Override with --twins / --sites (e.g. --twins interceptor_usv --sites kochi).

Writes /tmp/mcr_run/twin_site_matrix.json.
"""
import argparse
import glob
import json
import os
import subprocess
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALL_TWINS = ["interceptor_usv", "survey_usv", "maya_auv", "auv150"]
DEFAULT_TWINS = ["interceptor_usv", "survey_usv", "maya_auv", "auv150"]
ALL_SITES = ["kochi", "mumbai", "visakhapatnam"]


def _teardown():
    subprocess.run(["bash", os.path.join(REPO, "tools", "teardown_all.sh")],
                   cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_one(twin, site, settle_s=10):
    env = dict(os.environ, MCR_SITE=site)
    _teardown()
    boot = subprocess.run(["bash", "tools/run_sim.sh", twin, "up"], cwd=REPO, env=env)
    if boot.returncode != 0:
        _teardown()
        return {"error": "boot failed"}
    time.sleep(settle_s)  # let physics/EKF settle
    target = f"vehicle_twins/{twin}/target.json"
    subprocess.run(["python3", "tools/test_target.py", "--target", target], cwd=REPO, env=env)
    runs = sorted(glob.glob(f"{REPO}/target_runs/{twin}/*/verdicts.json"))
    res = json.load(open(runs[-1])) if runs else {"error": "no verdicts.json generated"}
    subprocess.run(["bash", "tools/run_sim.sh", twin, "down"], cwd=REPO, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _teardown()
    time.sleep(3)
    return res


def verdict_cells(res):
    """Flatten a verdicts.json 'attacks' block to {attack(.sub): verdict}."""
    out = {}
    for atk, data in res.get("attacks", {}).items():
        if "vulnerability" in data:
            out[atk] = data["vulnerability"]["verdict"]
        else:
            for sub, v in data.items():
                out[f"{atk}.{sub}"] = v.get("verdict", "?")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--twins", default=",".join(DEFAULT_TWINS),
                    help=f"comma-separated (default: {','.join(DEFAULT_TWINS)}; all: {','.join(ALL_TWINS)})")
    ap.add_argument("--sites", default=",".join(ALL_SITES), help="comma-separated site ids")
    args = ap.parse_args()
    twins = [t.strip() for t in args.twins.split(",") if t.strip()]
    sites = [s.strip() for s in args.sites.split(",") if s.strip()]

    matrix = {}
    for twin in twins:
        matrix[twin] = {}
        for site in sites:
            print(f"\n{'=' * 60}\n=== {twin} @ {site} ===\n{'=' * 60}")
            res = run_one(twin, site)
            matrix[twin][site] = {
                "site": res.get("site"),
                "git_sha": res.get("git_sha"),
                "verdicts": verdict_cells(res),
                "detectability": res.get("detectability", {}),
                "error": res.get("error"),
            }

    out_path = "/tmp/mcr_run/twin_site_matrix.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(matrix, f, indent=2)

    print(f"\n\n{'=' * 60}\n=== TWIN x SITE MATRIX ===\n{'=' * 60}")
    for twin, bysite in matrix.items():
        print(f"\n{twin}:")
        for site, cell in bysite.items():
            if cell.get("error"):
                print(f"  {site:<16} ERROR: {cell['error']}")
                continue
            vs = "  ".join(f"{k}={v}" for k, v in cell["verdicts"].items())
            det = cell["detectability"].get("by_attack_type", {})
            print(f"  {site:<16} {vs}  | alerts={det}")

    print("\n-- site-invariance (a twin's security verdicts should match across sites) --")
    for twin, bysite in matrix.items():
        sigs = {site: tuple(sorted(cell.get("verdicts", {}).items()))
                for site, cell in bysite.items() if not cell.get("error")}
        status = "INVARIANT" if len(set(sigs.values())) <= 1 else "DIFFERS (investigate)"
        print(f"  {twin}: {status} across {list(sigs.keys())}")

    print(f"\nFull matrix -> {out_path}")


if __name__ == "__main__":
    main()
