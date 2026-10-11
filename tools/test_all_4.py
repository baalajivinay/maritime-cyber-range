import os
import subprocess
import time
import json
import sys

PROFILES = [
    "mass_vulnerable_cusv",
    "mass_resilient_cusv",
    "auv_vulnerable_remus100",
    "auv_resilient_remus100_hardened"
]

REPO = "/home/vinay/maritime-cyber-range"

def main():
    final_report = {}
    
    for profile in PROFILES:
        print(f"\n{'='*60}")
        print(f"=== TESTING VEHICLE: {profile} ===")
        print(f"{'='*60}")
        
        # 1. Clean environment
        subprocess.run(["bash", "tools/run_sim.sh", profile, "down"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for proc in ["gz sim", "ardurover", "ardusub", "mav_bridge.py", "gps_spoof.py"]:
            subprocess.run(["pkill", "-9", "-f", proc], stderr=subprocess.DEVNULL)
        
        # 2. Boot vehicle headless
        print(f"[*] Booting {profile}...")
        r = subprocess.run(["bash", "tools/run_sim.sh", profile, "up"], cwd=REPO)
        if r.returncode != 0:
            print(f"[!] Failed to boot {profile}")
            continue
            
        time.sleep(10) # Let physics/EKF settle
        
        # 3. Run full attack suite via test_target.py
        # This will command movement and run all attacks (GPS, C2, AIS, Acoustic)
        print(f"[*] Running test_target suite for {profile}...")
        target_path = f"vehicle_twins/{profile}/target.json"
        
        # Run test_target.py synchronously
        r = subprocess.run(["python3", "tools/test_target.py", "--target", target_path], cwd=REPO)
        
        # 4. Parse results
        import glob
        runs = sorted(glob.glob(f"{REPO}/target_runs/{profile}/*/verdicts.json"))
        if runs:
            with open(runs[-1]) as f:
                res = json.load(f)
                final_report[profile] = res
        else:
            final_report[profile] = {"error": "No verdicts.json generated"}
            
        # 5. Teardown
        print(f"[*] Tearing down {profile}...")
        subprocess.run(["bash", "tools/run_sim.sh", profile, "down"], cwd=REPO)
        time.sleep(3)
        
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
