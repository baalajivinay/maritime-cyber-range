"""`twin init` scaffolder (Axis 1.3). Creates a new vehicle_twins/<name>/ folder
pre-populated with a profile.json, target.json and README stub that already pass
the contract, so contributing a twin is "fill in the blanks", not "reverse-
engineer the conventions". Additive; writes nothing outside the new folder.

Usage: python3 -m scaleup.twins.scaffold <name> --domain surface --model <gz_model>
"""
import argparse
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def scaffold(name, domain="surface", model=None, firmware="ArduPilot"):
    model = model or name
    folder = os.path.join(REPO, "vehicle_twins", name)
    os.makedirs(folder, exist_ok=True)
    vtype = "Rover" if domain == "surface" else "Sub"
    profile = {
        "name": name, "domain": domain, "firmware": firmware,
        "ardupilot_vehicle_type": vtype,
        "ais": ({"mmsi": "999000111", "vessel_name": name.upper(), "udp_addr": ["127.0.0.1", 10110]}
                if domain == "surface" else None),
        "ports": {"fdm_relay_bind": ["127.0.0.1", 9002], "fdm_gazebo_addr": ["127.0.0.1", 9100],
                  "mavlink": {"dashboard": 14551, "auto_mission": 14552, "c2_replay": 14553}},
        "model_sdf": f"sim_config/models/{model}/model.sdf",
        "world": {"method": "gz", "sdf": f"sim_config/{model}_world.sdf",
                  "model_name": model, "world_name": f"{model}_world"},
    }
    if domain == "surface":
        attacks = {"gps_spoof": {"enabled": True, "method": "fdm_relay", "step_offset_m": 50.0,
                                 "relay_fifo": f"/tmp/mcr_run/{name}/relay.fifo"},
                   "ais_spoof": {"enabled": False, "reason": "ECDIS/operator-layer; N/A to the autopilot"},
                   "c2_replay": {"enabled": True, "target_mode_for_injection": "HOLD",
                                 "allow_arm_and_actuate": True, "rc_throttle_pwm": 1700, "duration_s": 8.0}}
    else:
        attacks = {"gps_spoof": {"enabled": False, "reason": "N/A submerged"},
                   "ais_spoof": {"enabled": False, "reason": "N/A submerged"},
                   "c2_replay": {"enabled": True, "target_mode_for_injection": "ALT_HOLD",
                                 "allow_arm_and_actuate": True, "rc_throttle_pwm": 1700, "duration_s": 8.0},
                   "acoustic_spoof": {"enabled": True, "endpoint": "tcp:127.0.0.1:5762",
                                      "model_name": model, "step_offset_m": 50.0, "bearing_deg": 90.0}}
    target = {"name": name, "domain": domain, "authorized": True,
              "mavlink": {"connection": "udpin:127.0.0.1:14554", "source_system": 255},
              "attacks": attacks, "timing": {"settle_s": 5.0, "window_s": 20.0}}
    json.dump(profile, open(os.path.join(folder, "profile.json"), "w"), indent=2)
    json.dump(target, open(os.path.join(folder, "target.json"), "w"), indent=2)
    with open(os.path.join(folder, "README.md"), "w") as f:
        f.write(f"# {name}\n\nDomain: {domain} · firmware: {firmware} · gz model: {model}\n\n"
                "Document the real hardware this twin copies (mass, dimensions, hydrodynamics, "
                "sources) and the EXPECTED verdict per attack here.\n")
    return folder


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--domain", default="surface", choices=["surface", "underwater"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--firmware", default="ArduPilot")
    a = ap.parse_args()
    print("scaffolded:", scaffold(a.name, a.domain, a.model, a.firmware))


if __name__ == "__main__":
    main()
