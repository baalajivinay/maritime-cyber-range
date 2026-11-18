import os
import subprocess
import time
import json
import glob
import sys

PROFILES = [
    "interceptor_usv",
    "survey_usv",
    "maya_auv",
    "auv150"
]

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _teardown():
    """Reliable orphan reaper (tools/teardown_all.sh) -- more robust than
    run_sim.sh's per-profile `down`, which can leave orphans from a crashed
    boot that then wedge the next run."""
    subprocess.run(["bash", "tools/teardown_all.sh"], cwd=REPO,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _boot_and_test(profile):
    """One boot -> test_target -> teardown cycle. Returns the parsed verdicts
    dict, or None if the stack never produced one (boot/connect failure)."""
    _teardown()
    print(f"[*] Booting {profile}...")
    r = subprocess.run(["bash", "tools/run_sim.sh", profile, "up"], cwd=REPO)
    if r.returncode != 0:
        print(f"[!] Failed to boot {profile}")
        _teardown()
        return None
    time.sleep(10)  # let physics/EKF settle
    print(f"[*] Running test_target suite for {profile}...")
    target_path = f"vehicle_twins/{profile}/target.json"
    subprocess.run([sys.executable, "tools/test_target.py", "--target", target_path], cwd=REPO)
    runs = sorted(glob.glob(f"{REPO}/target_runs/{profile}/*/verdicts.json"))
    res = None
    if runs:
        with open(runs[-1]) as f:
            res = json.load(f)
    print(f"[*] Tearing down {profile}...")
    subprocess.run(["bash", "tools/run_sim.sh", profile, "down"], cwd=REPO,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _teardown()
    time.sleep(3)
    return res


def main():
    final_report = {}

    for profile in PROFILES:
        print(f"\n{'='*60}")
        print(f"=== TESTING VEHICLE: {profile} ===")
        print(f"{'='*60}")

        res = _boot_and_test(profile)
        # Retry once if the stack produced NO verdicts at all -- that is a flaky
        # boot / dropped connection (the orphan-stack failure mode), not a real
        # finding. (A legitimate INCONCLUSIVE verdict -- e.g. a hardened twin the
        # attacker can't even arm, or the documented ArduSub ~1s auto-disarm race
        # -- IS a real result and is reported as-is, not retried.)
        if res is None:
            print(f"[*] {profile}: no verdicts produced -- retrying once ...")
            res = _boot_and_test(profile)

        final_report[profile] = res if res is not None else {"error": "No verdicts.json generated"}

    # Write final aggregate report
    report_path = "/tmp/mcr_run/all_4_vehicles_report.json"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(final_report, f, indent=2)
        
    print(f"\n\n{'='*60}")
    print("=== ALL 4 VEHICLES TESTED ===")
    for profile, data in final_report.items():
        print(f"\n{profile}:")
        if "error" in data:
            print(f"  ERROR: {data['error']}")
            continue
            
        attacks = data.get("attacks", {})
        for atk, atk_data in attacks.items():
            if "vulnerability" in atk_data:
                vuln = atk_data.get("vulnerability", {})
                verdict = vuln.get("verdict", "UNKNOWN")
                print(f"  - {atk}: {verdict}")
            else:
                for sub_k, sub_v in atk_data.items():
                    verdict = sub_v.get("verdict", "UNKNOWN")
                    print(f"  - {atk}.{sub_k}: {verdict}")
            
        det = data.get("detectability", {})
        print(f"  - Detectability: {det.get('alerts_generated', 0)} raw alerts generated")
        
    print(f"\nFull detailed JSON saved to {report_path}")

if __name__ == "__main__":
    main()
