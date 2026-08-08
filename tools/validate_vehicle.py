#!/usr/bin/env python3
"""
WO-20: vehicle-model contract + validation.

Formalizes what a vehicle designer must expose so the harness can run and attack
a new vehicle, and checks a profile + its model SDF against that contract BEFORE
anyone tries to boot it. Run this on a new profile and fix every FAIL before
wiring it into run_sim.sh / run_attack_suite.

THE CONTRACT (per docs/ARCHITECTURE.md):
  Profile (profiles/<name>.json):
    - loads + passes constants.py validation (required keys, types).
    - domain in {surface, underwater}; ardupilot_vehicle_type in {Rover, Sub}.
    - surface  -> "ais" present (mmsi/vessel_name/udp_addr).
    - underwater -> "ais": null (AIS is N/A submerged, by design).
    - ports.fdm_relay_bind port == the port ArduPilot sends FDM to (9002 here);
      ports.fdm_gazebo_addr port == the model's ArduPilotPlugin <fdm_port_in>.
    - "model_sdf" points at an existing SDF.
  Model SDF (self-contained, resolvable):
    - has an ArduPilotPlugin (libArduPilotPlugin.so) with <fdm_port_in> matching
      the profile's fdm_gazebo_addr port.
    - has an IMU sensor (every vehicle) + at least one <control> channel.
    - surface  -> exposes a navsat/GPS sensor (its position feeds the surface
      GPS path that gps_spoof attacks).
    - underwater -> declares buoyancy + hydrodynamics (so it actually submerges/
      floats) -- checked in the model or its world.
  Attacks:
    - every name in profile "attacks" is either an implemented attack module
      (attacks/<name>.py) or a known domain-N/A entry.

Usage:
  python3 tools/validate_vehicle.py <profile>      # e.g. wamv | bluerov2
Exit code 0 = all checks pass.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

KNOWN_ATTACKS = {"gps_spoof", "ais_spoof", "c2_replay", "acoustic_spoof"}


def main():
    if len(sys.argv) < 2:
        print("usage: validate_vehicle.py <profile>")
        sys.exit(2)
    name = sys.argv[1]
    results = []  # (ok, label, detail)

    def check(ok, label, detail=""):
        results.append((bool(ok), label, detail))

    # --- profile loads + validates ---
    os.environ["MCR_VEHICLE_PROFILE"] = name
    try:
        import constants
        prof = constants.load_profile(name)
        check(True, "profile loads + passes constants validation")
    except Exception as e:
        check(False, "profile loads + passes constants validation", repr(e))
        _report(name, results)
        return

    domain = prof.get("domain")
    vtype = prof.get("ardupilot_vehicle_type")
    check(domain in ("surface", "underwater"), "domain in {surface,underwater}", str(domain))
    check(vtype in ("Rover", "Sub"), "vehicle type in {Rover,Sub}", str(vtype))
    check((domain == "surface") == (vtype == "Rover"),
          "domain matches vehicle type (surface<->Rover, underwater<->Sub)")

    # --- AIS applicability ---
    if domain == "surface":
        check(prof.get("ais") not in (None, {}), "surface profile declares AIS identity")
    else:
        check(prof.get("ais") is None, "underwater profile has ais:null (N/A submerged)")

    # --- ports ---
    ports = prof.get("ports", {})
    relay_port = ports.get("fdm_relay_bind", [None, None])[1]
    gz_port = ports.get("fdm_gazebo_addr", [None, None])[1]
    check(relay_port == 9002, "fdm_relay_bind port is 9002 (ArduPilot's fixed FDM port)", str(relay_port))
    check(isinstance(gz_port, int) and gz_port != relay_port,
          "fdm_gazebo_addr port distinct from relay port", str(gz_port))

    # --- model SDF ---
    model_rel = prof.get("model_sdf")
    check(bool(model_rel), "profile declares model_sdf")
    sdf = None
    if model_rel:
        model_path = os.path.join(REPO, model_rel)
        if os.path.exists(model_path):
            check(True, "model_sdf file exists", model_rel)
            sdf = open(model_path).read()
        else:
            check(False, "model_sdf file exists", model_rel)

    if sdf is not None:
        check("ArduPilotPlugin" in sdf, "model has an ArduPilotPlugin")
        m = re.search(r"<fdm_port_in>\s*(\d+)\s*</fdm_port_in>", sdf)
        check(m is not None and int(m.group(1)) == gz_port,
              "model <fdm_port_in> matches profile fdm_gazebo_addr port",
              f"model={m.group(1) if m else None} profile={gz_port}")
        check('type="imu"' in sdf or "type='imu'" in sdf, "model has an IMU sensor")
        check("<control" in sdf, "model has >=1 ArduPilotPlugin <control> channel")
        if domain == "surface":
            check("navsat" in sdf.lower() or "gps" in sdf.lower(),
                  "surface model exposes a navsat/GPS sensor")
        else:
            has_buoy = ("uoyancy" in sdf) or ("ydrodynamics" in sdf)
            world = os.path.join(REPO, "sim_config", "underwater_world.sdf")
            if not has_buoy and os.path.exists(world):
                has_buoy = "uoyancy" in open(world).read()
            check(has_buoy, "underwater model/world declares buoyancy + hydrodynamics")

    # --- attacks implemented or known N/A ---
    for atk in prof.get("attacks", []):
        impl = os.path.exists(os.path.join(REPO, "attacks", f"{atk}.py"))
        check(impl or atk in KNOWN_ATTACKS, f"attack '{atk}' is implemented or known",
              "implemented" if impl else "known/N-A")

    _report(name, results)


def _report(name, results):
    print(f"=== vehicle contract validation: {name} ===")
    fails = 0
    for ok, label, detail in results:
        tag = "PASS" if ok else "FAIL"
        if not ok:
            fails += 1
        print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))
    print(f"  {'ALL PASS' if fails == 0 else str(fails) + ' FAILURE(S)'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
