# Building and running a new AUV digital twin (self-serve, no dependencies on this session)

This is a from-scratch, step-by-step path to: build a new underwater vehicle
(a genuinely different digital twin from the project's existing BlueROV2),
boot it yourself with one command, and run the resilience tester against it
-- everything you need to prepare and run a live demo on your own.

It assumes no prior context beyond what's in this repo. Every command below
is something you type and run yourself.

## What you're actually building

Three files, all under version control like everything else in this repo:

1. **A Gazebo SDF model** (`sim_config/models/<name>/model.sdf`) -- the
   physical AUV: hull mesh, mass/buoyancy, thrusters, an IMU sensor, and an
   `ArduPilotPlugin` block wiring simulated thruster joints to MAVLink
   control channels. This is what makes it "real physics," not a stub.
2. **A vehicle profile** (`profiles/<name>.json`) -- metadata connecting
   that model to ArduSub (home coordinates, ports, which world file to
   boot it in). This is what `tools/run_sim.sh <name> up` reads.
3. **A resilience-tester target** (`targets/<name>_local.json`) -- tells
   `tools/test_target.py` how to reach and attack the booted vehicle. This
   is the file that actually drives your demo's GPS/AIS/C2 test run.

None of this requires touching Python code. If you follow the steps below
and something doesn't validate, the fix is almost always in the SDF or the
JSON, not in the tooling.

## Fastest real path: clone BlueROV2, then make it genuinely different

Building underwater hydrodynamics from a blank file is a multi-week
undertaking (this project already did that work once, for BlueROV2 -- see
`docs/ROADMAP.md` WO-11/WO-12/WO-13). The tractable, still-legitimate way to
get a *new* digital twin is what this project did for its second surface
vehicle (BlueBoat, WO-21): clone an existing model and retune it until it's
a physically distinct vehicle, not a renamed copy. A demo audience cares
that the numbers (mass, buoyancy, thrust) are real and internally
consistent, not that the mesh is bespoke.

### 1. Copy the model

```bash
cd /home/vinay/maritime-cyber-range
cp -r sim_config/models/bluerov2 sim_config/models/myauv
```

Fastest correct way to rename everything at once (verified against a live
clone while writing this guide -- a plain find-and-replace by hand misses
the thruster `<cmd_topic>` entries, which are easy to overlook and will
silently break thrust if left pointing at `bluerov2`):

```bash
sed -i \
  -e 's/model name="bluerov2"/model name="myauv"/' \
  -e 's#model://bluerov2/#model://myauv/#g' \
  -e 's#/model/bluerov2/#/model/myauv/#g' \
  sim_config/models/myauv/model.sdf
```

That one command covers: the `<model name>` declaration, every mesh
`<uri>` (hull + 6 thruster prop meshes -- the meshes themselves can stay
Blue Robotics' geometry for now, unless you have your own to drop in
`meshes/`), the camera `<topic>`, and all 6 thrusters' `<cmd_topic>`
entries. Confirm nothing was missed:

```bash
grep -n "bluerov2" sim_config/models/myauv/model.sdf   # should print nothing
```

### 2. Make it a genuinely different vehicle, not a reskin

The base_link `<inertial>` and `<collision>` blocks are your two real
tuning knobs. BlueROV2 is trimmed to near-neutral buoyancy at 10.0 kg mass /
0.457x0.338x0.0632 m collision box (displaced mass = box volume x fluid
density 1025 kg/m^3 ~= 10.0 kg, matching vehicle mass -- see the comment
right above that block in the file for the exact math). To make a
meaningfully different AUV:

- **Change the mass** (`<inertial><mass>`) -- a heavier or lighter vehicle.
- **Re-solve the collision box for neutral buoyancy** at the new mass:
  `box_volume = mass / 1025`, then pick length x width x height that
  multiply to that volume (keep it roughly hull-shaped, not a cube). Do this
  even if you don't care about depth-hold precision for the demo --
  wildly non-neutral buoyancy fights ArduSub's controller and looks broken
  on stage.
- **Recompute `<inertia>` (ixx/iyy/izz)** for the new mass/dimensions. For a
  box approximation: `ixx = mass/12 * (h^2 + d^2)`, `iyy = mass/12 * (l^2 +
  d^2)`, `izz = mass/12 * (l^2 + h^2)` where l/w/h are your collision box
  dimensions. Doesn't need to be exact -- needs to be in the right ballpark
  so the vehicle doesn't spin unrealistically.
- Optionally reposition the 6 `thruster1`..`thruster6` links' `<pose>`
  values if your hull is a different size/shape (keep the SAME 6-thruster
  vectored-frame topology and their `<joint>` parent/child wiring unless
  you're prepared to also change ArduSub's `FRAME_CONFIG` param and
  re-derive the thruster mixing -- that's a much bigger, riskier change and
  not necessary for a legitimate "different AUV" demo).

### 3. Give it its own world (or reuse the existing one)

Simplest: copy the underwater world and point it at your new model.

```bash
cp sim_config/underwater_world.sdf sim_config/myauv_world.sdf
```

Edit `sim_config/myauv_world.sdf`:
- `<world name="underwater_harbor">` -> `<world name="myauv_harbor">`
  (must be unique -- this is the Gazebo topic namespace)
- `<uri>model://bluerov2</uri>` -> `<uri>model://myauv</uri>` (the AUV
  `<include>` block, currently spawned at `<pose>0 0 -2 0 0 0</pose>` --
  ~2m submerged; leave as-is unless your hull needs more clearance)

### 4. Write the profile

Create `profiles/myauv.json`:

```json
{
  "name": "myauv",
  "domain": "underwater",
  "ardupilot_vehicle_type": "Sub",
  "home": { "lat": -33.724223, "lon": 150.679736 },
  "attacks": ["gps_spoof", "acoustic_spoof", "c2_replay"],
  "ais": null,
  "ports": {
    "fdm_relay_bind": ["127.0.0.1", 9002],
    "fdm_gazebo_addr": ["127.0.0.1", 9100],
    "mavlink": { "dashboard": 14551, "auto_mission": 14552, "c2_replay": 14553 }
  },
  "model_sdf": "sim_config/models/myauv/model.sdf",
  "world": {
    "method": "gz",
    "sdf": "sim_config/myauv_world.sdf",
    "model_name": "myauv",
    "world_name": "myauv_harbor"
  }
}
```

`ais: null` and `gps_spoof` in the attack list is correct and intentional
for underwater -- see `docs/DESIGNER_GUIDE.md`'s "Reading attack results"
section for why (AIS is N/A submerged by design; GPS spoof is included but
will legitimately report SKIP/N-A unless you also arrange a surfaced GPS
window, which is out of scope for a first demo).

### 5. Validate before you ever try to boot it

```bash
python3 tools/validate_vehicle.py myauv
```

Fix every `FAIL` before continuing -- it checks the SDF has the
ArduPilotPlugin, the `<fdm_port_in>` matches your profile's
`fdm_gazebo_addr` port, there's an IMU sensor, and buoyancy is declared.
This catches copy-paste mistakes (a stale `bluerov2` reference you missed)
before a confusing live boot.

### 6. Boot it

```bash
tools/run_sim.sh myauv up
```

Watch for `[OK]` after each stage (world, relay, SITL, MAVLink bridge). If
it hangs on "world up, model 'myauv' present" -- your `<include><uri>` in
the world file doesn't match the model directory name, or the model
directory isn't under `sim_config/models/`.

```bash
tools/run_sim.sh myauv status    # health-check without rebooting
tools/run_sim.sh myauv down      # tear down when done
```

### 7. Smoke-test it manually before trusting it for a demo

Don't skip this -- confirm the vehicle actually arms and moves before
building your presentation around it:

```bash
python3 - <<'PY'
from pymavlink import mavutil
import time

conn = mavutil.mavlink_connection("tcp:127.0.0.1:5763", source_system=255)
conn.wait_heartbeat(timeout=15)
print("connected, modes:", conn.mode_mapping())
conn.set_mode(conn.mode_mapping()["MANUAL"])
time.sleep(1.5)

# Retry arming for up to 15s, not a single attempt -- ArduSub can arm then
# immediately auto-disarm again within ~1s (a known GCS/RC-failsafe race,
# nothing to do with your model), so a single arm-then-check misreads a
# perfectly healthy vehicle as broken. Keep re-arming until a heartbeat
# actually confirms it, same pattern tools/test_target.py's C2 check uses.
armed = False
end = time.time() + 15
last_arm = 0
while time.time() < end and not armed:
    if time.time() - last_arm > 1.0:
        conn.mav.command_long_send(conn.target_system, conn.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
        last_arm = time.time()
    m = conn.recv_match(type="HEARTBEAT", blocking=True, timeout=0.5)
    if m and bool(m.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
        armed = True
print("armed:", armed)

# Push throttle (chan3) up and watch servo5/6 (the vertical-thruster pair
# for a 6-thruster vectored frame cloned from BlueROV2 -- NOT servo3, see
# the troubleshooting section below).
moved = False
end = time.time() + 4
while time.time() < end:
    conn.mav.rc_channels_override_send(conn.target_system, conn.target_component, 1500, 0, 1700, 0, 0, 0, 0, 0)
    m = conn.recv_match(type="SERVO_OUTPUT_RAW", blocking=False)
    if m and abs(m.servo5_raw - 1500) > 100:
        moved = True
    time.sleep(0.1)
print("thrusters responded to override:", moved)
conn.mav.rc_channels_override_send(conn.target_system, conn.target_component, 0,0,0,0,0,0,0,0)
PY
```

You should see `armed: True` and `thrusters responded to override: True`.
If `armed` takes several seconds/retries to go True, that's expected and
fine -- the retry loop is there because a single attempt can catch the
vehicle mid-auto-disarm and misreport a healthy vehicle as broken (this is
exactly what happened validating this guide against a live clone: one
single-shot arm check said `False`, the retry-loop version against the
same running vehicle said `True` half a second later).

## Run the actual resilience-test demo

This is the deliverable: point the tool at your new AUV and get a
vulnerability + detectability + deployment-readiness report, exactly like
it does for BlueROV2.

### 8. Write the target config

Create `targets/myauv_local.json`:

```json
{
  "name": "myauv_local",
  "description": "New AUV digital twin, booted via tools/run_sim.sh myauv up.",
  "domain": "underwater",
  "authorized": true,
  "mavlink": { "connection": "tcp:127.0.0.1:5763", "source_system": 255 },
  "attacks": {
    "gps_spoof": { "enabled": false, "reason": "N/A while submerged -- see docs/TARGET_TESTING.md" },
    "ais_spoof": { "enabled": false, "reason": "N/A -- submerged, no AIS" },
    "c2_replay": {
      "target_mode_for_injection": "ALT_HOLD",
      "enabled": true,
      "allow_arm_and_actuate": true,
      "rc_throttle_pwm": 1700,
      "rc_steering_pwm": 1500,
      "duration_s": 8.0
    }
  },
  "timing": { "settle_s": 5.0, "window_s": 20.0 }
}
```

(`gps_spoof`/`ais_spoof` disabled+N/A matches BlueROV2's own config for the
same, already-established reason -- see `targets/bluerov2_local.json`. If
your AUV has a different EK3_SRC1_POSXY config or you've wired a surfaced
GPS path, you can enable `gps_spoof` -- see `docs/TARGET_TESTING.md`'s
"Onboarding a new target" section for the method choice.)

### 9. Validate, then run

```bash
python3 tools/validate_target.py myauv_local
python3 tools/test_target.py --target myauv_local
```

This baselines the vehicle, runs the enabled attacks, taps the live feed
with the same blind detectors used everywhere else in this project, and
writes `target_runs/myauv_local/<timestamp>/verdicts.json`.

### 10. Generate the report

```bash
python3 tools/generate_target_report.py
```

Opens as `target_runs/resilience_report.html` in a browser -- one page,
every target this repo has ever tested (yours included), each with a
vulnerability table, a detectability table, per-VULNERABLE-finding
recommendations, and one synthesized deployment-readiness verdict. This is
the actual thing to put on a screen during your presentation.

### 11. Tear down

```bash
tools/run_sim.sh myauv down
```

## Optional: put it on the live dashboard too

The resilience-test report above is the core deliverable and needs nothing
further. If you also want the interactive visual dashboard (map, live
attack buttons, real-time alerts -- good for a more theatrical demo moment)
pointed at your new vehicle:

```bash
tools/run_demo.sh myauv up      # boots sim + dashboard together
```

This works immediately with no code changes -- `run_demo.sh`/`run_sim.sh`
read everything from your profile. The only thing that's hardcoded is the
dashboard's own **in-page** "switch vehicle" dropdown (three lines: an
`if prof not in (...)` check in
`nodes/monitor/src/dashboard_server.py`, and three `<option>` lines in
`nodes/monitor/src/templates/index.html`) -- add `"myauv"` to both if you
want the dropdown itself to offer it; not required if you're fine launching
it from the terminal, which is simpler and less to go wrong live.

## Troubleshooting checklist (things this project has actually hit)

- **`validate_vehicle.py` FAILs on `<fdm_port_in>` mismatch** -- your
  model's ArduPilotPlugin `<fdm_port_in>` must equal the profile's
  `ports.fdm_gazebo_addr` port (9100 by convention; don't change it unless
  you also change the profile).
- **World boots but "model present" check hangs** -- the `<include><uri>`
  model name in your world SDF doesn't match your model directory name
  exactly (case-sensitive).
- **Vehicle arms then immediately disarms** -- known ArduSub failsafe race,
  not your model. Re-arm; `test_target.py`'s C2 check already handles this.
- **RC override sent but nothing visibly moves** -- confirm you're watching
  the right SERVO_OUTPUT_RAW channel. For a 6-thruster vectored frame
  cloned from BlueROV2, vertical thrust (chan3/throttle) drives
  servo5+servo6, NOT servo3 (servo3 is the Rover-surface convention) --
  see the smoke-test script above and `docs/EXECUTION_STATE.md`'s
  2026-08-08 entry for how this was determined.
- **Depth drifts on its own in ALT_HOLD** -- your buoyancy trim isn't
  neutral. Re-check the `box_volume x 1025 == mass` math in step 2.
- **Always tear down (`tools/run_sim.sh <name> down`) before booting a
  different profile** -- only one domain's stack can run at a time (they
  share ports 9002/9100).

## Before you present

Do a full dry run of steps 6-11 at least once, start to finish, timed. The
`settle_s`/`window_s` in your target config plus the C2 check's own
stabilization pass mean one full attack run is on the order of a minute --
know that number before you're on stage.
