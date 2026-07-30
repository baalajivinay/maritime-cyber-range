# Designer Guide — Maritime Cyber Range

A dual-domain (surface **MASS/USV** + underwater **AUV**) simulation cyber range:
boot a vehicle, run cyber-attacks against it, and score rule-based detectors on
how well they catch those attacks. This guide is the front door — how to run it,
read results, and add your own vehicle.

## What's in the box

| Layer | Where | What it does |
|---|---|---|
| Vehicles | `profiles/*.json` + `sim_config/**` | WAM-V (surface, ArduRover) and BlueROV2 (underwater, ArduSub), each a self-describing profile pointing at a Gazebo model. |
| One-command sim | `tools/run_sim.sh` | Boots a whole domain's stack with real health checks: Gazebo world → FDM relay → ArduPilot SITL → MAVLink bridge → (surface) AIS emulator. |
| Attacks | `attacks/*.py` | `gps_spoof`, `ais_spoof` (ghost + impersonation), `c2_replay` (RC-override / command injection), `acoustic_spoof` (submerged position spoof). |
| Attack runner | `tools/run_attack_suite.py` | Runs the profile's applicable attacks, verifies each vs true Gazebo pose, reports PASS/FAIL/SKIP/N-A. |
| Detection | `detection/` | Blind rule-based detectors on live feeds + a live dashboard alert layer. |
| Scoring | `tools/score_detectors.py` | Replays blind detector alerts vs ground truth → precision/recall per attack. |
| Vehicle contract | `tools/validate_vehicle.py` | Checks a new vehicle meets the harness contract before you boot it. |

Deeper design notes live in `docs/ARCHITECTURE.md`; the full build history and
checkpoints in `docs/ROADMAP.md`; the live work cursor in
`docs/EXECUTION_STATE.md`.

## Quick start

Pick a profile: `wamv` (surface) or `bluerov2` (underwater).

**For a live/interactive demo**, use the one-command launcher (sim + the
operator-console dashboard together) and open the URL:

```bash
tools/run_demo.sh wamv up          # boots sim + dashboard -> http://localhost:8080
tools/view_3d.sh                   # optional: Gazebo 3D view (needs a GPU desktop)
tools/run_demo.sh wamv down
```

The dashboard is an **operator console**: set a destination (click the map, the
boat navigates there), launch attacks (GPS / AIS / C2 with a selectable injected
command / acoustic), watch true-vs-believed diverge, and hit **Report** for
precision/recall. See `docs/DEMO_GUIDE.md` for the full presentation runbook
(including the boot-fresh pre-flight step).

**For automated verification** (no dashboard), use the harness directly:

```bash
tools/run_sim.sh wamv up                       # health-checked stack
python3 tools/run_attack_suite.py --profile wamv   # attacks, pass/fail
tools/run_sim.sh wamv down
```

`run_sim.sh <profile> status` health-checks a running stack. A whole
attack run can also self-contain the boot/teardown:
`python3 tools/run_attack_suite.py --profile wamv --boot`.

> Agent/automation note: because the stack's processes are `setsid`-detached, a
> supervisor that redirects a boot command's stdout can lose that command's own
> output — redirect `run_sim.sh` / `--boot` output to a file and read it. The
> work still succeeds; a normal login shell is unaffected.

## Reading attack results

`run_attack_suite.py` prints one line per attack:

- **PASS** — the attack produced its expected, verified effect (e.g. GPS spoof
  jumped MAVLink position ≥ 20 m while the true Gazebo pose stayed put; C2 moved
  the true pose; acoustic spoof walked the AUV's believed position off its true
  position).
- **SKIP** — applicable in principle but not exercised here (e.g. underwater
  `gps_spoof`: GPS doesn't reach a submerged AUV; only meaningful in surfaced
  windows).
- **N/A** — physically inapplicable by design (e.g. underwater `ais_spoof`: no
  AIS underwater). *Not a gap.*
- **FAIL** — expected effect not observed. Investigate.

Attack semantics differ by domain **on purpose**: GPS and AIS are surface-RF
phenomena; a submerged AUV navigates by inertial + **acoustic** positioning, so
its position attack is `acoustic_spoof`. C2 is MAVLink-level and works in both
domains.

## Detection + scoring

Detectors consume **only live feeds** (the same telemetry the dashboard sees) and
never the private `attack_logs/*.csv` ground truth — that isolation is what makes
the score meaningful.

```bash
# with a stack up, run the blind detectors for a while (writes an alert log)
MCR_VEHICLE_PROFILE=wamv python3 detection/run_detectors.py --seconds 90 &
# ... run attacks (they log their own ground truth) ...
python3 tools/run_attack_suite.py --profile wamv
# then score the blind alerts against ground truth
python3 tools/score_detectors.py --alerts evidence/detector_alerts_wamv.jsonl
```

The scorer prints precision/recall per attack family. Reference results this
project has achieved: surface precision 1.00 / recall 1.00; underwater recall
1.00, precision ~0.82. The dashboard's **Attack Alerts** panel shows the same
detector output live (WO-24).

## Adding your own vehicle

1. **Model.** Provide a Gazebo SDF with an `ArduPilotPlugin` (its `<fdm_port_in>`
   = your profile's `fdm_gazebo_addr` port, so `attacks/gps_spoof.py` can relay
   in front on 9002), an IMU sensor, and one `<control>` channel per actuator.
   Surface vehicles also expose a navsat/GPS sensor; underwater vehicles rely on
   buoyancy + hydrodynamics (in the model or the world) and external-nav
   positioning. The BlueROV2 model is a worked underwater example
   (`sim_config/models/bluerov2/`).
2. **Profile.** Add `profiles/<name>.json` (copy an existing one): `domain`,
   `ardupilot_vehicle_type`, `home`, `attacks`, `ais` (null for underwater),
   `ports`, and `model_sdf` pointing at your SDF.
3. **Validate before booting:**
   ```bash
   python3 tools/validate_vehicle.py <name>
   ```
   Fix every `FAIL`. This checks the whole contract (ports, sensors, plugin,
   domain/AIS consistency, attack availability) so you catch mistakes before a
   confusing live boot.
4. **Boot + attack** with `run_sim.sh <name> up` and
   `run_attack_suite.py --profile <name>`. If it doesn't work first try, the
   contract (validator) is the thing to extend — fix it there, not just for this
   one vehicle.

## Ports (single source of truth: the active profile)

| Component | Port | Note |
|---|---|---|
| ArduPilot FDM | UDP 9002 | ArduPilot always sends here; the relay binds it. |
| Gazebo ArduPilotPlugin | UDP 9100 | model `<fdm_port_in>`; relay forwards here. |
| AIS broadcast | UDP 10110 | emulator + spoofer + dashboard + detectors. |
| MAVLink (dashboard / auto_mission / c2) | 14551 / 14552 / 14553 | fanned out by `tools/mav_bridge.py`. |
| ArduPilot spare serials | tcp 5762 / 5763 | acoustic_spoof feed / detector tap. |

One domain runs at a time (both share 9002/9100). Always `run_sim.sh <p> down`
before booting the other domain, or a stale relay/gz server breaks the boot.
