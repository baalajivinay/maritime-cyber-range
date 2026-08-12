# Architecture

Dual-domain by design: surface (MASS/USV, ArduRover) and underwater (AUV,
ArduSub) share the same attack/detection/dashboard/testing code paths, not
separate implementations. Everything below applies to both unless a section
says otherwise.

## Component map

**Surface (ArduRover):**
```
ArduPilot SITL (ardurover, JSON FDM backend)
        |  UDP :9002 (FDM request/reply, ArduPilot's fixed send port)
        v
attacks/gps_spoof.py  --(relay, transparent unless spoofing is ON)-->  Gazebo (:9100)
        |
        |  MAVLink (via tools/mav_bridge.py's fan-out)
        v
nodes/monitor/src/dashboard_server.py  <-- also legit_gps_feeder (GPS_INPUT, own port)
        |
        v
Browser dashboard (Leaflet + Socket.IO, localhost:8080)
```

**Underwater (ArduSub):**
```
ArduPilot SITL (ardusub, JSON FDM backend)
        |  UDP :9002 / :9100 (same relay pattern, reused unchanged)
        v
Gazebo (buoyancy + hydrodynamics plugins)
        |
        |  gz topic -e (true pose)          MAVLink (via mav_bridge.py)
        v                                            v
attacks/acoustic_spoof.py's read_true_ned()  ---> legit_vision_feeder
        |  (VISION_POSITION_ESTIMATE: true position + true yaw, always-on)
        v
nodes/monitor/src/dashboard_server.py  ---> Browser dashboard
```

A submerged AUV has no GPS (RF doesn't penetrate water) and no AIS
consumption on any ArduPilot vehicle (transmit-only) — its position source is
`EK3_SRC1_POSXY=6` (ExternalNav), fed via MAVLink `VISION_POSITION_ESTIMATE`.
`attacks/acoustic_spoof.py` is the underwater analog of `gps_spoof.py`: it
plays both the legitimate position provider (spoof off) and the attacker
(spoof on) on the same channel. **Both REMUS-100 twins also use this feed as
their YAW source** (`EK3_SRC1_YAW=6`), so the feed must carry the vehicle's
real heading, not a placeholder — see `attacks/acoustic_spoof.py`'s
`read_true_ned()` docstring for the ENU→NED conversion and why a hardcoded
`yaw=0.0` here silently corrupts the EKF's heading belief (found and fixed
2026-08-10; a second, deeper navigation issue this surfaced is still open,
see `docs/EXECUTION_STATE.md`'s 2026-08-10 entry).

`nodes/ais_emulator/ais_emulator.py` reads the vessel's true Gazebo pose
directly (`gz topic -e`) and broadcasts standards-compliant AIVDM sentences
over UDP :10110 (surface only). `attacks/ais_spoof.py` broadcasts forged
sentences onto the same UDP channel — no interception needed, since AIS has
no message-level authentication in this project (or in reality).

## Three config layers — don't confuse them

| Layer | Files | Purpose |
|---|---|---|
| **Vehicle profile** | `profiles/<name>.json` | How to *boot* a vehicle: domain, ArduPilot type, home coords, ports, model/world SDF paths. Loaded by `constants.py` via `MCR_VEHICLE_PROFILE` (default `wamv`). |
| **Vehicle twin** | `vehicle_twins/<name>/` | A self-contained package around one profile: `profile.json` + optional `hardened.parm` + `target.json` + `README.md`. `tools/run_vehicle.sh`/`run_demo.sh` symlink its `profile.json` into `profiles/` so the loader above sees it with zero code changes. **This is the primary way to boot something today** — the 4 current twins (`mass_vulnerable_cusv`, `mass_resilient_cusv`, `auv_vulnerable_remus100`, `auv_resilient_remus100_hardened`) all work this way. |
| **Target** | `targets/<name>.json` | How to *attack and score* a vehicle already reachable over MAVLink — this repo's own (twin or legacy profile) or a genuinely external ArduPilot instance this repo never boots. Loaded by `targets/loader.py`, consumed by `tools/test_target.py`. Requires `authorized: true`. |

A `vehicle_twins/<name>/target.json` and a bare `targets/<name>.json` use the
*same schema* — a twin's `target.json` just also has a corresponding
`profile.json` so this repo can boot it, where a bare `targets/*.json` only
describes how to *reach* something already running elsewhere.

## Vehicle profile schema

```json
{
  "name": "mass_vulnerable_cusv",
  "domain": "surface",                  // "surface" | "underwater"
  "ardupilot_vehicle_type": "Rover",    // "Rover" (surface) | "Sub" (underwater)
  "home": {"lat": -33.724223, "lon": 150.679736},
  "attacks": ["gps_spoof", "ais_spoof", "c2_replay"],   // omit gps_spoof/ais_spoof underwater
  "ais": {"mmsi": "123456789", "vessel_name": "CUSV-CYBER", "udp_addr": ["127.0.0.1", 10110]},
  "ports": {
    "fdm_relay_bind": ["127.0.0.1", 9002],
    "fdm_gazebo_addr": ["127.0.0.1", 9100],
    "mavlink": {"dashboard": 14551, "auto_mission": 14552, "c2_replay": 14553}
  },
  "model_sdf": "sim_config/models/cusv/model.sdf",
  "world": {"method": "gz", "sdf": "sim_config/cusv_world.sdf",
            "model_name": "cusv", "world_name": "cusv_harbor"}
}
```
`ais` is `null` for underwater (structurally N/A, not a gap — see
`docs/DESIGNER_GUIDE.md`'s "Reading attack results"). A **hardened** twin
additionally sets `"ardu_defaults": "vehicle_twins/<name>/hardened.parm"` and
optionally `"gcs_source_system"` — see `docs/VEHICLE_TWIN_CONTRACT.md`.
`constants.py` validates required keys on load and raises a `ValueError`
naming the specific missing key.

## Port map (single source of truth: `constants.py`, computed from the active profile)

| Component | Protocol | Port (default) | Notes |
|---|---|---|---|
| ArduPilot FDM (fixed) | UDP | 9002 | ArduPilot always sends/expects FDM traffic here. `attacks/gps_spoof.py` binds this to sit in front of Gazebo (surface and underwater both). |
| Gazebo ArduPilotPlugin | UDP | 9100 | The model's `<fdm_port_in>` **must** match, so the relay above can occupy 9002 instead of Gazebo talking to ArduPilot directly. |
| AIS broadcast | UDP | 10110 | Shared by the emulator, the spoofer, the dashboard's AIS listener, and detectors. Surface only. |
| Dashboard MAVLink | MAVLink/UDP | 14551 | `tools/mav_bridge.py`'s fan-out target #1. |
| `tools/test_target.py` auto-mission port (also the dashboard's `goto()`) | MAVLink/UDP | 14552 | Fan-out #2. |
| `attacks/c2_replay.py` | MAVLink/UDP | 14553 | Fan-out #3. |
| `tools/test_target.py`'s own connection | MAVLink/UDP | 14554 (`c2_replay`+1) | Lets the CLI tester run concurrently with a live dashboard without stealing its port. |
| `legit_gps_feeder` (dashboard, surface only) | MAVLink/UDP | 14555 (`test_target`+1) | Always-on `GPS_INPUT` feed of the vehicle's own true position — see "Resilient-twin position feeders" below. |
| `legit_vision_feeder` (dashboard, underwater only) | MAVLink/UDP | 14556 (`gps_feeder`+1) | Always-on `VISION_POSITION_ESTIMATE` feed (true position **and** true yaw). |
| ArduPilot spare serial (`SERIAL1`) | TCP | 5762 | `attacks/acoustic_spoof.py`'s feed connection; the dashboard's attacker-simulating `cmd_conn()`. |
| ArduPilot spare serial (`SERIAL2`) | TCP | 5763 | `detection/run_detectors.py`'s live tap; the dashboard's own detector loop. |

All MAVLink ports must stay distinct — two components both declaring
`udpin:127.0.0.1:<same port>` will fail to bind (or silently steal each
other's packets) when run together. `tools/mav_bridge.py`'s `OUT_PORTS` list
is the fan-out authority; add a new port there (and to `constants.py`) before
adding a new MAVLink-consuming script.

## Resilient-twin position feeders (why they exist)

Both hardened mechanisms below make GPS/vision an *external, filterable*
input instead of something baked into the shared physics ground truth — but
that means a hardened twin has **zero ambient position source** unless
something feeds it continuously:

- **Surface**: `GPS1_TYPE=14` (`AP_GPS_MAV` driver) needs `GPS_INPUT`
  messages. `legit_gps_feeder()` in `dashboard_server.py` sends the
  vehicle's own true position at 5Hz the entire time the dashboard is up —
  harmless no-op for a vulnerable twin (its default GPS driver isn't
  listening for `GPS_INPUT` at all).
- **Underwater**: `EK3_SRC1_POSXY=6` **and** `EK3_SRC1_YAW=6` (ExternalNav)
  need continuous `VISION_POSITION_ESTIMATE`. `legit_vision_feeder()` reuses
  `attacks/acoustic_spoof.py`'s `read_true_ned()` (true position + true yaw
  from Gazebo) rather than re-deriving pose parsing a second time, but
  deliberately does **not** touch that module's own `state`/`_lock` (the
  attack's forged-offset toggle) — this feeder always sends the untouched
  truth, so a later Acoustic Spoof attack has to compete with a real signal
  still running, not be the only signal the vehicle ever sees.

Without these, a `goto()` click on a resilient twin arms fine but silently
never enters AUTO (underwater) or never passes the EKF-health arming gate
(surface) — see `docs/EXECUTION_STATE.md`'s 2026-08-09 entries for the live
failure signatures this was root-caused from.

## Ground-truth log isolation

Each attack module (`gps_spoof.py`, `ais_spoof.py`, `c2_replay.py`,
`acoustic_spoof.py`, `gps_input_inject.py`) writes its own CSV to
`attack_logs/`, recording exactly what it forged and when.

**This is a private evaluation record.** No detection/monitoring code
(`detection/detectors.py`, `nodes/monitor/src/dashboard_server.py`) should
ever read these files during normal operation — the whole point is that they
exist independently of whatever a detector observes, so a detector's
performance can be scored against them after the fact without the detector
having had access to ground truth while running. Only `tools/score_detectors.py`
(offline) and `tools/test_target.py` (which writes its own target-scoped
copies under `target_runs/`, never touching `attack_logs/` for anything but
`fdm_relay`-method GPS spoofing) read them.

## Running order

In practice, use `tools/run_sim.sh <profile> up` (or `tools/run_vehicle.sh
vehicle_twins/<name> up` / `tools/run_demo.sh <profile-or-twin-path> up` for
the dashboard too) — one command, real health checks, both domains. What
follows is what that script actually does, for anyone extending it:

1. Boot Gazebo with the profile's world SDF.
2. Start `attacks/gps_spoof.py`'s relay — **not optional**. ArduPilot's FDM
   output is hardcoded to `127.0.0.1:9002` with no flag to change it; since
   Gazebo's ArduPilotPlugin listens on 9100, nothing connects at all unless
   this relay bridges 9002↔9100 (transparent passthrough with spoofing off).
3. Start ArduPilot SITL as a direct binary (`ardurover`/`ardusub`), stdin fed
   via a FIFO+keepalive — SITL reads stdin as a console and exits on EOF, so
   it must never be launched with `< /dev/null` or a closed pipe.
4. Start `tools/mav_bridge.py` — replaces MAVProxy's `output add` for a
   headless boot (MAVProxy needs an interactive tty).
5. (Surface) start `nodes/ais_emulator/ais_emulator.py`.
6. Start `nodes/monitor/src/dashboard_server.py` (if using `run_demo.sh`) —
   its own background threads include `legit_gps_feeder`/`legit_vision_feeder`
   (above), the detector tap, and the true/believed-position pollers.

Always `tools/run_sim.sh <p> down` (or the twin/demo equivalent) before
re-`up`, or a stale relay on :9002 / stale Gazebo server breaks the boot —
`run_sim.sh down` kills the full process tree, including VRX grandchildren
for the legacy `wamv` profile.

## Legacy vs. current vehicle set

`profiles/{wamv,blueboat,bluerov2}.json` are the **original three reference
vehicles** (generic hobbyist/research hulls, not individually-named
hardware) — retired as the primary demo set but still fully bootable
directly (`tools/run_sim.sh wamv up`), still used by `docs/DESIGNER_GUIDE.md`
and `docs/NEW_AUV_QUICKSTART.md` as the generic/from-scratch teaching path,
and still the clone base for building an entirely new AUV twin. The current
primary set — `vehicle_twins/{mass_vulnerable_cusv,mass_resilient_cusv,
auv_vulnerable_remus100,auv_resilient_remus100_hardened}` — is real, named
Navy/research hardware (Textron Fleet-class CUSV, REMUS-100) built on the
exact same underlying mechanism (`profiles/*.json` + `sim_config/**`), just
packaged as self-contained folders. See `docs/TWIN_DEMO_GUIDE.md` for the
current set and `docs/EXECUTION_STATE.md` for the full pivot history (dual-
domain demo → vehicle-agnostic resilience tester → real-named-hardware
twins).
