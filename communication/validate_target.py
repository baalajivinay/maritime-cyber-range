#!/usr/bin/env python3
"""
Contract check for a targets/<name>.json file -- catches config mistakes
before tools/test_target.py spends a live run on them, and surfaces the
safety implications of a config's choices loudly rather than silently.

Usage:
  python3 tools/validate_target.py <name>
"""
import argparse
import ipaddress
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "targets"))
sys.path.insert(0, REPO)
from targets.loader import load_target  # noqa: E402


def _host_of(connection):
    """Best-effort extraction of the host from a pymavlink connection
    string (e.g. 'udpout:203.0.113.5:14550' -> '203.0.113.5')."""
    rest = connection.split(":", 1)[1] if ":" in connection else connection
    return rest.rsplit(":", 1)[0] if ":" in rest else rest


def _is_loopback(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in ("localhost",)


def validate(name):
    faults, warnings = [], []
    try:
        target = load_target(name)
    except ValueError as e:
        return [str(e)], []

    conn = target["mavlink"]["connection"]
    host = _host_of(conn)
    loopback = _is_loopback(host)

    attacks = target.get("attacks", {})

    gcfg = attacks.get("gps_spoof", {})
    if gcfg.get("enabled") and gcfg.get("method", "gps_input") == "fdm_relay":
        if not loopback:
            faults.append(
                f"gps_spoof.method=fdm_relay but mavlink.connection host '{host}' is not "
                "loopback -- fdm_relay only works when WE own the target's physics engine "
                "(our own reference vehicles). Use method=gps_input for a real external target."
            )

    ccfg = attacks.get("c2_replay", {})
    if ccfg.get("enabled") and ccfg.get("allow_arm_and_actuate") and not loopback:
        warnings.append(
            f"c2_replay.allow_arm_and_actuate=true against a NON-loopback target ({host}). "
            "This will arm and physically actuate a vehicle you don't control the boot of. "
            "Confirm this is really intended and authorized before running."
        )

    acfg = attacks.get("ais_spoof", {})
    if acfg.get("enabled") and "impersonate" in acfg.get("modes", []) and not acfg.get("own_mmsi"):
        warnings.append(
            "ais_spoof.modes includes 'impersonate' but own_mmsi is not set -- "
            "impersonation mode will be skipped at run time (nothing to impersonate)."
        )

    if not attacks:
        warnings.append("No attacks configured -- this target run would do nothing.")

    return faults, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    args = ap.parse_args()

    faults, warnings = validate(args.name)

    for w in warnings:
        print(f"WARN  {w}")
    for f in faults:
        print(f"FAIL  {f}")

    if faults:
        print(f"\n{args.name}: {len(faults)} fault(s), {len(warnings)} warning(s) -- NOT valid.")
        sys.exit(1)
    print(f"\n{args.name}: valid ({len(warnings)} warning(s)).")


if __name__ == "__main__":
    main()
