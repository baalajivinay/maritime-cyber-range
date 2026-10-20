"""Twin registry (Axis 1.3). Generalises tools/validate_vehicle.py's one-off
contract check into discovery: scan vehicle_twins/, read each self-contained
folder's manifest (profile.json + target.json + README.md), and return a
structured record per twin -- so the dashboard, the matrix runner and any
future UI enumerate twins from one place instead of hard-coded lists.

Stdlib only. conformance() reuses the contract idea (does the folder have what
the harness needs to boot and attack it?) without a live connection.
"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TWINS_DIR = os.path.join(REPO, "vehicle_twins")


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def discover(twins_dir=TWINS_DIR):
    """Return [{id, path, domain, firmware, profile, target, has_readme,
    hardened, attacks}] for every well-formed twin folder."""
    out = []
    if not os.path.isdir(twins_dir):
        return out
    for name in sorted(os.listdir(twins_dir)):
        folder = os.path.join(twins_dir, name)
        if not os.path.isdir(folder):
            continue
        prof = _load(os.path.join(folder, "profile.json"))
        tgt = _load(os.path.join(folder, "target.json"))
        if prof is None or tgt is None:
            continue
        attacks = {k: v.get("enabled", False) for k, v in tgt.get("attacks", {}).items()}
        out.append({
            "id": name,
            "path": os.path.relpath(folder, REPO),
            "domain": prof.get("domain"),
            "firmware": prof.get("firmware", "ArduPilot"),
            "model": prof.get("world", {}).get("model_name"),
            "has_readme": os.path.exists(os.path.join(folder, "README.md")),
            "hardened": any(f.endswith(".parm") and "harden" in f.lower() for f in os.listdir(folder)),
            "attacks": attacks,
        })
    return out


def conformance(twin_record):
    """Lightweight contract check (no live boot). Returns (ok, [issues])."""
    issues = []
    if twin_record.get("domain") not in ("surface", "underwater"):
        issues.append("domain must be surface|underwater")
    if not twin_record.get("model"):
        issues.append("profile.world.model_name missing")
    if not twin_record.get("attacks"):
        issues.append("target.json declares no attacks")
    if not twin_record.get("has_readme"):
        issues.append("no README.md (twin should document expected per-attack result)")
    return (not issues, issues)
