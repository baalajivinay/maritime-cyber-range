#!/usr/bin/env python3
"""Run a mission scenario and produce an operational-consequence / T&E report.

Scale-up prototype -- NOT part of the shipped package's default flow (nothing
else imports or calls it). Default mode is 'sim' (synthetic model, no live
sim/Docker/hardware needed).

  python3 tools/run_scenario.py scenarios/harbor_transit_gps_walkoff.json
  python3 tools/run_scenario.py scenarios/<x>.json --out target_runs/scenario_x
  python3 tools/run_scenario.py scenarios/<x>.json --mode live    # needs a booted twin
"""
import argparse
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from scaleup.scenario import (load_scenario, run_scenario, SimExecutor, LiveExecutor,
                              report, report_html)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", help="path to a scenario JSON (see scenarios/)")
    ap.add_argument("--mode", choices=["sim", "live"], default="sim",
                    help="sim = synthetic model (default); live = against a booted twin")
    ap.add_argument("--out", default=None,
                    help="directory to write report.md + result.json + report.html (the visual T&E report)")
    ap.add_argument("--json", action="store_true", help="print machine JSON instead of the Markdown report")
    args = ap.parse_args()

    scenario = load_scenario(args.scenario)
    executor = SimExecutor() if args.mode == "sim" else LiveExecutor()
    result = run_scenario(scenario, executor, keep_telemetry=bool(args.out))

    print(report.to_json(result) if args.json else report.to_markdown(result))

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "report.md"), "w") as f:
            f.write(report.to_markdown(result))
        with open(os.path.join(args.out, "result.json"), "w") as f:
            f.write(report.to_json(result))
        with open(os.path.join(args.out, "report.html"), "w") as f:
            f.write(report_html.to_html(result, scenario))
        print(f"\n[written] {args.out}/report.md, result.json, report.html")

    # non-zero exit if any critical consequence triggered -- CI/gate friendly
    sys.exit(2 if result.overall_severity == "critical" else 0)


if __name__ == "__main__":
    main()
