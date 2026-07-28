# Architecture

## Component map

```
ArduPilot SITL (ardurover, JSON backend)
        |  UDP :9002 (FDM request/reply)
        v
attacks/gps_spoof.py  --(relay, optionally forges position[0]/[1])-->  Gazebo/VRX (:9100)
        |
        |  telemetry (MAVLink)
        v
nodes/monitor/src/dashboard_server.py  <-- ROS2 NavSatFix, MAVLink GLOBAL_POSITION_INT, AIS UDP
        |
        v
Browser dashboard (Leaflet + Socket.IO, localhost:8080)
```

`nodes/ais_emulator/ais_emulator.py` reads the vessel's true Gazebo pose
directly (`gz topic -e`) and broadcasts standards-compliant AIVDM sentences
over UDP :10110. `attacks/ais_spoof.py` broadcasts forged sentences onto the
same UDP channel -- no interception needed, since AIS has no message-level
authentication in this project (or in reality).

## Port map (single source of truth: `constants.py`)

| Component | Protocol | Port | Notes |
|---|---|---|---|
| ArduPilot FDM (fixed) | UDP | 9002 | ArduPilot always sends/expects FDM traffic here. `attacks/gps_spoof.py` binds this to sit in front of Gazebo. |
| Gazebo ArduPilotPlugin | UDP | 9100 | `sim_config/wamv_ardupilot.sdf`'s `<fdm_port_in>` **must** be 9100 so the relay above can occupy 9002 instead of Gazebo talking to ArduPilot directly. |
| AIS broadcast | UDP | 10110 | Shared by the emulator, the spoofer, and the dashboard's AIS listener. |
| Dashboard MAVLink | MAVLink/UDP | 14551 | `output add 127.0.0.1:14551` in MAVProxy. |
| `attacks/auto_mission.py` | MAVLink/UDP | 14552 | `output add 127.0.0.1:14552` in MAVProxy. |
| `attacks/c2_replay.py` | MAVLink/UDP | 14553 | `output add 127.0.0.1:14553` in MAVProxy. |

These three MAVLink endpoints must stay distinct -- two components both
declaring `udpin:127.0.0.1:<same port>` will fail to bind (or silently
steal each other's packets) when run together. Add a new port to
`constants.py` before adding a new MAVLink-consuming script.

## Ground-truth log isolation

Each attack module (`gps_spoof.py`, `ais_spoof.py`, `c2_replay.py`) writes
its own CSV to `attack_logs/`, recording exactly what it forged and when.

**This is a private evaluation record.** No detection/monitoring code
(`nodes/monitor/src/dashboard_server.py`, or any future detector) should
ever read these files during normal operation -- the whole point is that
they exist independently of whatever a detector observes, so a detector's
performance can be scored against them after the fact without the
detector having had access to ground truth while running.

## Running order

1. `sim_config/start_gz.sh` or `sim_config/start_vrx.sh` (Gazebo/VRX)
2. `sim_config/start_sitl.sh` (ArduPilot SITL)
3. In the MAVProxy console spawned by step 2, `output add` the ports any
   attack scripts you intend to run need (see table above)
4. `nodes/ais_emulator/ais_emulator.py` and
   `nodes/monitor/src/dashboard_server.py`
5. Any of `attacks/gps_spoof.py`, `attacks/ais_spoof.py`,
   `attacks/c2_replay.py`, `attacks/auto_mission.py`

If you regenerate `sim_config/wamv_ardupilot.sdf` via `sim_config/modify_sdf.py`,
re-check the FDM port (see table above) -- it's written by that script,
not hand-maintained.
