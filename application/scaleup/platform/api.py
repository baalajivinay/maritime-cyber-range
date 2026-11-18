"""Range-as-a-service REST API (Axis 1.6). Wraps the existing CLI tools so the
range is a platform, not only a terminal workflow: enumerate backends / twins /
sites / compliance frameworks, launch a headless resilience run, and read back
verdicts + their compliance mapping. Flask (already a dependency); default bind
is loopback with the same secure-by-default posture as the dashboard.

Read endpoints are pure (no sim needed) and unit-tested via the Flask test
client. POST /run shells tools/run_sim.sh + tools/test_target.py, so it needs a
host that can boot the stack.

Run: python3 -m scaleup.platform.api   (then GET http://127.0.0.1:8090/backends)
"""
import glob
import json
import os
import subprocess
import sys

from flask import Flask, jsonify, request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from scaleup.backends import registry as backends
from scaleup.twins import registry as twins
from scaleup.compliance import frameworks
from scaleup.sites import list_sites

app = Flask(__name__)


@app.route("/backends")
def list_backends():
    return jsonify([b.describe() for b in backends.all_backends()])


@app.route("/twins")
def list_twins():
    recs = twins.discover()
    for r in recs:
        ok, issues = twins.conformance(r)
        r["conformant"], r["issues"] = ok, issues
    return jsonify(recs)


@app.route("/sites")
def sites():
    return jsonify([{"id": s.id, "name": s.name} for s in list_sites()])


@app.route("/frameworks")
def list_frameworks():
    return jsonify(frameworks.ALL_FRAMEWORKS)


@app.route("/compliance/<kind>")
def compliance(kind):
    fw = request.args.getlist("framework") or None
    return jsonify(frameworks.controls_for(kind, fw))


@app.route("/run", methods=["POST"])
def run():
    """Body: {"twin": "...", "site": "kochi", "attacks": "c2_replay,gps_spoof"}.
    Boots the twin at the site, runs test_target, returns the verdicts.json plus
    its compliance mapping. Requires a host that can boot the sim."""
    body = request.get_json(force=True, silent=True) or {}
    twin = body.get("twin")
    site = body.get("site", "kochi")
    if not twin:
        return jsonify(error="'twin' required"), 400
    env = dict(os.environ, MCR_SITE=site)
    subprocess.run(["bash", "tools/teardown_all.sh"], cwd=REPO, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    boot = subprocess.run(["bash", "tools/run_sim.sh", twin, "up"], cwd=REPO, env=env)
    if boot.returncode != 0:
        subprocess.run(["bash", "tools/teardown_all.sh"], cwd=REPO, env=env)
        return jsonify(error="boot failed"), 500
    cmd = ["python3", "tools/test_target.py", "--target", f"vehicle_twins/{twin}/target.json"]
    if body.get("attacks"):
        cmd += ["--attacks", body["attacks"]]
    subprocess.run(cmd, cwd=REPO, env=env)
    subprocess.run(["bash", "tools/run_sim.sh", twin, "down"], cwd=REPO, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["bash", "tools/teardown_all.sh"], cwd=REPO, env=env)
    runs = sorted(glob.glob(f"{REPO}/target_runs/{twin}/*/verdicts.json"))
    if not runs:
        return jsonify(error="no verdicts produced"), 500
    res = json.load(open(runs[-1]))
    flat = {}
    for atk, data in res.get("attacks", {}).items():
        if "vulnerability" in data:
            flat[atk] = data["vulnerability"]["verdict"]
        else:
            for sub, v in data.items():
                flat[f"{atk}.{sub}"] = v.get("verdict")
    res["compliance"] = frameworks.map_verdicts(flat)
    return jsonify(res)


def create_app():
    return app


if __name__ == "__main__":
    host = os.environ.get("MCR_API_HOST", "127.0.0.1")
    port = int(os.environ.get("MCR_API_PORT", "8090"))
    print(f"[api] maritime-cyber-range API on http://{host}:{port}  (GET /backends /twins /sites /frameworks)")
    app.run(host=host, port=port)
