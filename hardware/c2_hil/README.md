# C2 hardware-in-the-loop (HIL) harness

Boots a **minimal MAVLink-only target** and bridges a real ESP32 rogue C2 node
(`hardware/esp32_mavlink_node/`) into it, so the C2 attack runs from genuine
hardware over WiFi instead of a localhost script. Validated on real hardware
(ESP32-WROOM) on 2026-10-20.

Two pieces:

| file | role |
|---|---|
| `boot_c2_target.sh` | ArduPilot SITL (native physics, **no Gazebo**) + `tools/mav_bridge.py` |
| `esp32_ingress.py`  | `udpin 0.0.0.0:14550` ↔ `tcp:5762` (SITL), running the same blind `DetectorSuite` as `tools/test_target.py` |

The C2 vector is pure MAVLink and does not need Gazebo physics (that only
matters for GPS/position/acoustic vectors), so this harness skips the heavy
world for speed and robustness. For the full physics stack use
`tools/run_sim.sh <profile> up`.

## Run

```bash
# 1) target (defaults: mass_vulnerable_cusv @ kochi; override via env)
hardware/c2_hil/boot_c2_target.sh
#    e.g. MCR_VEHICLE_PROFILE=mass_resilient_cusv MCR_SITE=mumbai hardware/c2_hil/boot_c2_target.sh

# 2) ESP32 ingress + live detector (leave running)
python3 hardware/c2_hil/esp32_ingress.py

# 3) flash + power the board (set WIFI_SSID/WIFI_PASS/TARGET_IP in the sketch first)
arduino-cli compile --clean --fqbn esp32:esp32:esp32 hardware/esp32_mavlink_node
arduino-cli upload  -p /dev/ttyUSB0 --fqbn esp32:esp32:esp32 hardware/esp32_mavlink_node

# teardown
hardware/c2_hil/boot_c2_target.sh down
```

When the board joins the network and reaches the host, the ingress prints
`*** first ESP32 packet from <ip> ***` and then the C2 alerts as they fire
(`forged mode change`, `RC_CHANNELS_OVERRIDE — actuator authority seized`).

## Notes
- `TARGET_IP` in the sketch must be the **host's LAN IP** (the machine running
  this harness), and the board and host must share a 2.4 GHz network with no
  AP client-isolation. If the board shows frames leaving (set `USB_FRAME_DUMP 1`)
  but the ingress sees nothing, suspect client-isolation or a host firewall on
  the UDP port.
- The sketch's WiFi credentials are bench-specific and are intentionally **not**
  committed with real values — set them locally before flashing.
