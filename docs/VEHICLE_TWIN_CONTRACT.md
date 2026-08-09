# Vehicle Twin Contract — package your own vehicle to run in this environment

You have a vehicle (an ArduPilot Gazebo model, or a Rover/Sub you're
developing) and want it to boot, get attacked, and score a resilience
verdict inside *this* repo's environment — the same way
`vehicle_twins/mass_vulnerable_cusv` or `auv_vulnerable_remus100` do. This
doc is the contract: what a `vehicle_twins/<name>/` folder must contain,
what your Gazebo model must expose, and the exact commands to validate,
boot, attack, and read a verdict once it's in place.

**This is a different scenario from the other two vehicle-related guides —
pick the right one:**

| You have... | Use |
|---|---|
| A Gazebo SDF model (or are willing to build/adapt one) that boots **inside this repo** | **This doc.** |
| No Gazebo model at all, just ArduPilot physics you want built from scratch | [`docs/NEW_AUV_QUICKSTART.md`](NEW_AUV_QUICKSTART.md) first (builds the SDF), then come back here to package it. |
| A vehicle's ArduPilot SITL **already running somewhere else** (you don't want it living in this repo at all) | [`docs/TARGET_TESTING.md`](TARGET_TESTING.md) instead — point `tools/test_target.py` at it directly via a `targets/<name>.json`, no `vehicle_twins/` folder needed. |

## The contract, in one sentence

A `vehicle_twins/<name>/` folder is a `profile.json` (how to boot it) plus a
`target.json` (how to attack and score it) plus a `README.md` — self-
contained, so `tools/run_vehicle.sh vehicle_twins/<name> up` and
`python3 tools/test_target.py --target vehicle_twins/<name>/target.json`
work without touching anything else in the repo.

## 1. Your Gazebo model

Your `model.sdf` (referenced by `profile.json`'s `model_sdf` field, anywhere
under `sim_config/models/` by convention) must have:

- An **`ArduPilotPlugin`** (`filename="libArduPilotPlugin.so"` or
  `filename="ArduPilotPlugin"`) with a `<fdm_port_in>` matching your
  profile's `ports.fdm_gazebo_addr` port (see §2) — this is how ArduPilot
  SITL and Gazebo talk to each other.
- An **IMU sensor** (`type="imu"`).
- At least one **`<control>` channel** inside the `ArduPilotPlugin` block
  (servo/thruster output wiring).
- **Surface vehicles**: a navsat/GPS sensor (its position is what
  `attacks/gps_spoof.py` perturbs).
- **Underwater vehicles**: buoyancy + hydrodynamics plugins, either in the
  model itself or its world file (`gz-sim-buoyancy-system` +
  `gz-sim-hydrodynamics-system`).

`tools/validate_vehicle.py` (§4) checks every one of these mechanically —
that script's own docstring is the authoritative, always-current version of
this list if it and this doc ever drift.

You'll also need a **world file** (`sim_config/<name>_world.sdf` by
convention) that includes your model — clone `sim_config/cusv_world.sdf`
(surface) or `sim_config/remus100_world.sdf` (underwater) as a starting
point; both are minimal, self-contained, and already proven.

**Gazebo pose-parsing gotcha, learned the hard way (2026-08-09):** Gazebo's
protobuf text format omits any pose field that equals its default (0.0) —
a level vehicle doing pure-yaw rotation has quaternion x=0/z=0, which is
the *normal* resting case, not rare. If you write your own pose-reading
code (most people won't need to — the AIS emulator and dashboard already
handle this correctly), don't require every field to literally appear as
text; default missing ones to 0.0.

## 2. `profile.json` — how to boot it

```jsonc
{
  "name": "your_vehicle_name",              // must match the folder name
  "domain": "surface",                      // "surface" | "underwater"
  "ardupilot_vehicle_type": "Rover",         // "Rover" (surface) | "Sub" (underwater) --
                                             // these two fields must agree
  "home": { "lat": -33.724223, "lon": 150.679736 },
  "attacks": ["gps_spoof", "ais_spoof", "c2_replay"],   // omit gps_spoof/ais_spoof
                                                          // for underwater (see below)
  "ais": {                                  // null for underwater (AIS is N/A submerged)
    "mmsi": "367999555",
    "vessel_name": "YOUR-VESSEL",
    "udp_addr": ["127.0.0.1", 10110]
  },
  "ports": {
    "fdm_relay_bind": ["127.0.0.1", 9002],  // always 9002 -- ArduPilot's fixed FDM send port
    "fdm_gazebo_addr": ["127.0.0.1", 9100], // must match your model.sdf's <fdm_port_in>
    "mavlink": { "dashboard": 14551, "auto_mission": 14552, "c2_replay": 14553 }
  },
  "model_sdf": "sim_config/models/your_vehicle/model.sdf",
  "world": {
    "method": "gz",                          // "gz" (plain Gazebo world) or "vrx" (VRX-specific)
    "sdf": "sim_config/your_vehicle_world.sdf",
    "model_name": "your_vehicle",            // the <model name="..."> in your SDF
    "world_name": "your_vehicle_harbor"      // the <world name="..."> in your world SDF
  }
}
```

For a **hardened** twin (the resilient half of a vulnerable/resilient
pair), add `"ardu_defaults": "vehicle_twins/<name>/hardened.parm"` and
optionally `"gcs_source_system": 77` (or any id other than ArduPilot's
default 255) — see any existing `*_resilient_*/hardened.parm` for the
mechanism (`MAV_GCS_SYSID` + `MAV_OPTIONS=1` for GCS-link enforcement,
`GPS1_TYPE=14` for surface GPS/EKF fusion). Don't copy a `hardened.parm`
verbatim from an unrelated hull — the DAVE BlueROV2 defaults file this
project's own BlueROV2 twin uses is loaded with that hardware's specific
calibration/joystick/camera junk; write your own, trimmed to what your
model actually needs (`vehicle_twins/auv_vulnerable_remus100/remus100.parm`
is a worked example of doing this correctly, with its own header comment
explaining exactly what was kept vs. dropped and why).

## 3. `target.json` — how to attack and score it

```jsonc
{
  "name": "your_vehicle_name",
  "description": "One paragraph: what this is, what config it's running, how to boot it.",
  "domain": "surface",
  "authorized": true,                        // REQUIRED true -- explicit attestation you're
                                              // authorized to attack this target. The loader
                                              // refuses to run otherwise -- this isn't a
                                              // technical control, it's a deliberate-not-
                                              // accidental gate.
  "mavlink": {
    "connection": "udpin:127.0.0.1:14554",   // any pymavlink connection string
    "source_system": 255                     // the attacker's simulated sysid -- 255 (ArduPilot's
                                              // default expected GCS id) is the correct choice
                                              // for testing an unhardened config; a target that
                                              // changed its own SYSID_MYGCS away from 255 would
                                              // legitimately show RESILIENT here
  },
  "attacks": {
    "gps_spoof": {
      "enabled": true,
      "method": "fdm_relay",                 // "fdm_relay" (this repo's own booted vehicles --
                                              // intercepts ArduPilot's JSON SITL protocol) or
                                              // "gps_input" (any MAVLink autopilot, incl. real
                                              // hardware later -- injects GPS_INPUT #232)
      "bind": ["127.0.0.1", 9002],           // fdm_relay only
      "gazebo_addr": ["127.0.0.1", 9100],    // fdm_relay only
      "profile": "step",                     // "step" | "ramp"
      "step_offset_m": 50.0,
      "direction_deg": 90.0
    },
    "ais_spoof": {                           // omit/false for underwater -- N/A, RF doesn't
                                              // penetrate water and ArduPilot never consumes
                                              // AIS on any vehicle (transmit-only)
      "enabled": true,
      "udp_addr": ["127.0.0.1", 10110],
      "own_mmsi": "367999555",
      "modes": ["ghost", "impersonate"]
    },
    "c2_replay": {
      "enabled": true,
      "target_mode_for_injection": "HOLD",   // "ALT_HOLD" for underwater
      "allow_arm_and_actuate": true,         // default false -- arming/actuating a vehicle you
                                              // don't fully control needs explicit opt-in
      "rc_throttle_pwm": 1700,
      "rc_steering_pwm": 1500,
      "duration_s": 8.0
    }
  },
  "timing": { "settle_s": 5.0, "window_s": 20.0 }
}
```

Full field-by-field reasoning lives in `targets/loader.py`'s own docstring
and `docs/TARGET_TESTING.md` — this is the same schema `test_target.py`
uses for *any* target, twin or not.

## 4. Validate, boot, attack, read the verdict

```bash
# 1. Contract check -- catches a broken profile/model BEFORE a confusing live boot
python3 tools/validate_vehicle.py your_vehicle_name
# fix every [FAIL] before continuing

# 2. Boot it (headless -- for the CLI tester below)
tools/run_vehicle.sh vehicle_twins/your_vehicle_name up
# or, with the live dashboard instead:
#   tools/run_demo.sh vehicle_twins/your_vehicle_name up

# 3. Run the full resilience test
python3 tools/test_target.py --target vehicle_twins/your_vehicle_name/target.json
# prints a verdict per attack, writes
# target_runs/your_vehicle_name/<timestamp>/verdicts.json

# 4. Tear down
tools/run_vehicle.sh vehicle_twins/your_vehicle_name down
```

`validate_vehicle.py` will print `[FAIL]` next to the specific thing that's
wrong (missing plugin, port mismatch, wrong vehicle type, etc.) — fix that
one thing and re-run rather than guessing. Step 2's boot log itself has a
`[OK]`/`[DOWN]` line per stage (world up, relay bound, SITL port, MAVLink
heartbeat) if something fails to come up.

## 5. What a real result looks like

Read `vehicle_twins/mass_vulnerable_cusv/README.md` and
`vehicle_twins/auv_resilient_remus100_hardened/README.md` for two worked,
live-verified examples of the four possible verdicts (`VULNERABLE` /
`RESILIENT` / `N/A` / `INCONCLUSIVE`) and how each is reasoned about — your
own twin's `README.md` should follow the same shape once you have live
results: an expected-result table, then a "Verified live result" section
with the actual `test_target.py` output, not a claim that wasn't run.

Once your twin passes its own attack suite, add it to the table in
`docs/TWIN_DEMO_GUIDE.md` if you want it discoverable alongside the
existing 4.
