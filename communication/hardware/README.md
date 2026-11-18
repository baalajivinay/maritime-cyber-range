# Hardware-in-the-loop (HIL) — ESP32 attacker nodes

This tree holds firmware that brings **real hardware** into the range's attack
path — the first rung of the founding brief's "later funded HIL range". Two
roles are implemented for an **ESP32-WROOM DevKit (WiFi + BT)**; the limits of
that board are called out honestly below.

## What the ESP32-WROOM can and cannot do

| Role | ESP32 fit | Firmware |
|---|---|---|
| **Rogue MAVLink C2 node** (WiFi) — a real external device on the telemetry network injecting SET_MODE / RC_CHANNELS_OVERRIDE | ✅ ideal — WiFi UDP to `mav_bridge`/SITL or a real Pixhawk on the same net | `esp32_mavlink_node/` |
| **NMEA 0183 sensor spoofer** (UART) — feeds a real autopilot/ECDIS forged GPS/depth over wire, no RF | ✅ ideal — Serial2 → RS-422 shifter → target bridge | `esp32_nmea_injector/` |
| **Comms-link attacker** — WiFi deauth / rogue-AP / BT against the telemetry link | ✅ possible (ESP-IDF) — not shipped here | — |
| **GNSS/AIS RF spoofing** (over the air) | ❌ **no** — needs an SDR (HackRF/USRP/bladeRF) + a shielded enclosure; the ESP32 has no GPS L1 radio | use an SDR, not the ESP32 |
| **Flight controller / autopilot** | ❌ **no** — use a Pixhawk/CubePilot running the same firmware the twins model | — |

So: the ESP32 **does help** — it is a genuine hardware attacker node for the C2
and serial-sensor vectors, and it is the cheapest way to move those two attacks
from "software injection" to "a real device on the wire". It is **not** the RF
GNSS spoofer and **not** the vehicle autopilot.

## How it plugs into the range

- **MAVLink node** → set `TARGET_IP`/`TARGET_PORT` to the host running
  `tools/mav_bridge.py` (a fan-out port from `constants.py`) or a SITL UDP out.
  The injected commands are detected by the same blind `C2CommandDetector` the
  software path uses, so detectability results stay comparable.
- **NMEA injector** → wire `TX2` to the target's GNSS serial input. It emits the
  same sentence format/checksum as `scaleup/protocols/nmea0183.py`, so the
  Python detectors tap the identical bus.

## Full-HIL roadmap (beyond the ESP32)

1. **Real autopilot in the loop** — Pixhawk/Cube running ArduPilot, Gazebo as the
   physics, HIL over USB/serial.
2. **RF layer (authorized, shielded only)** — SDR GNSS/AIS signal generation
   inside a Faraday cage / anechoic chamber; this is the Tier-C validation path
   and is lawful **only** under authorized test in a sealed enclosure.
3. **Real acoustic modem / USBL** for the underwater ExternalNav vector.

## Validated on real hardware (2026-10-20, ESP32-WROOM / CP210x on /dev/ttyUSB0)

Both images were built, flashed and verified end-to-end over the USB cable with
`arduino-cli` (ESP32 core 3.3.12, MAVLink lib 2.0.34):

- **NMEA injector** — flashed; with `USB_ECHO 1` it emitted `$GPGGA/$GPRMC`
  that `scaleup/protocols/nmea0183.py` parsed **13/13 checksum-valid**, decoded
  to Kochi (9.90000, 76.20000), and the adapter turned into `believed_pos`
  detector events. The firmware and the range share one NMEA bus.
- **MAVLink C2 node** — flashed; with `USB_FRAME_DUMP 1` it emitted 83 MAVLink
  v2 frames, **0 unparseable** (pymavlink), containing a GCS `HEARTBEAT`,
  `SET_MODE` (custom_mode=4) and `RC_CHANNELS_OVERRIDE` (chan1=1500, chan3=1700).
  Fed to the range's blind `C2CommandDetector`, they raised **27 alerts**.

Reproduce (board on `/dev/ttyUSB0`):
```bash
arduino-cli compile --fqbn esp32:esp32:esp32 hardware/esp32_nmea_injector
arduino-cli upload  -p /dev/ttyUSB0 --fqbn esp32:esp32:esp32 hardware/esp32_nmea_injector
# set USB_ECHO 1 (NMEA) or USB_FRAME_DUMP 1 (MAVLink) first to verify over USB.
```
The MAVLink node's **live** C2 test additionally needs a bench WiFi the ESP32
can join (`WIFI_SSID`) and a host running SITL/`mav_bridge` at `TARGET_IP:PORT`.

## Legal / safety

All firmware here is for **authorized testing on equipment you own**, on a bench
or in a shielded lab. Injecting navigation data or commands onto any live vessel,
shared RF spectrum, or equipment you are not authorized to test is unlawful. The
RF rung in particular must never radiate outside a sealed enclosure.
