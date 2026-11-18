/*
 * Maritime Cyber Range -- ESP32 NMEA 0183 sensor-spoofer (HIL role #2).
 *
 * Turns an ESP32-WROOM DevKit into a hardware GNSS/sounder that emits forged
 * NMEA 0183 sentences on its UART (Serial2). Wire TX2 -> the RX of a REAL
 * autopilot / chart-plotter / ECDIS (through an RS-422 level shifter for a real
 * bridge; direct 3.3 V TTL for a dev autopilot). The target then navigates on a
 * position YOU control -- true hardware-in-the-loop GPS spoofing, over wire,
 * with NO RF emission (so it is lawful on a bench, unlike an SDR GPS simulator).
 *
 * This is the firmware sibling of scaleup/protocols/nmea0183.py: identical
 * sentence format and XOR checksum, so the Python range and the ESP32 speak the
 * same bus. A tiny WiFi control endpoint lets the dashboard/operator switch
 * modes live (off / step / ramp).
 *
 * Fully self-contained -- no external Arduino libraries required.
 *
 * AUTHORIZED TESTING ONLY. Feeding forged navigation data to equipment you do
 * not own, or on any live/operational vessel, is unlawful. Bench use only.
 */
#include <WiFi.h>
#include <WiFiUdp.h>
#include <math.h>

// ---- config ---------------------------------------------------------------
static const char* AP_SSID = "mcr-nmea-node";   // ESP32 hosts its own AP
static const char* AP_PASS = "range-test-only";
static const int   NMEA_BAUD = 38400;           // 4800 for legacy, 38400 common
static const int   UART_TX_PIN = 17;            // Serial2 TX2
static const int   UART_RX_PIN = 16;
static const uint16_t CTRL_PORT = 10111;        // UDP control
#define USB_ECHO 0   // set 1 to also mirror forged sentences to USB serial (bench test/verify)

// start position (overwrite for your site; default = Kochi)
double lat0 = 9.90, lon0 = 76.20, bearingDeg = 90.0;

// spoof state
enum Mode { OFF, STEP, RAMP };
volatile Mode mode = OFF;
double stepOffsetM = 50.0, rampRateMps = 0.5;
unsigned long tStart = 0;

WiFiUDP udp;
const double M_PER_DEG_LAT = 111320.0;

// ---- NMEA helpers (mirror scaleup/protocols/nmea0183.py) ------------------
String nmeaWrap(const String& body) {
  uint8_t c = 0;
  for (size_t i = 0; i < body.length(); i++) c ^= (uint8_t)body[i];
  char cs[4]; snprintf(cs, sizeof(cs), "%02X", c);
  return "$" + body + "*" + String(cs) + "\r\n";
}

String ddmm(double v, bool isLat) {
  char hemi = isLat ? (v >= 0 ? 'N' : 'S') : (v >= 0 ? 'E' : 'W');
  v = fabs(v);
  int deg = (int)v;
  double minutes = (v - deg) * 60.0;
  char buf[20];
  if (isLat) snprintf(buf, sizeof(buf), "%02d%07.4f,%c", deg, minutes, hemi);
  else       snprintf(buf, sizeof(buf), "%03d%07.4f,%c", deg, minutes, hemi);
  return String(buf);
}

double offsetM() {
  if (mode == STEP) return stepOffsetM;
  if (mode == RAMP) return rampRateMps * ((millis() - tStart) / 1000.0);
  return 0.0;
}

void currentPos(double& lat, double& lon) {
  double mag = offsetM();
  double br = bearingDeg * M_PI / 180.0;
  double dn = mag * cos(br), de = mag * sin(br);
  lat = lat0 + dn / M_PER_DEG_LAT;
  lon = lon0 + de / (M_PER_DEG_LAT * cos(lat0 * M_PI / 180.0));
}

void emitFix() {
  double lat, lon; currentPos(lat, lon);
  String gga = "GPGGA,000000.00," + ddmm(lat, true) + "," + ddmm(lon, false) +
               ",1,09,0.8,0.0,M,0.0,M,,";
  String rmc = "GPRMC,000000.00,A," + ddmm(lat, true) + "," + ddmm(lon, false) +
               ",0.0," + String(bearingDeg, 1) + ",010100,,,A";
  Serial2.print(nmeaWrap(gga));
  Serial2.print(nmeaWrap(rmc));
#if USB_ECHO
  Serial.print(nmeaWrap(gga));   // mirror to USB so a bench test can read them
  Serial.print(nmeaWrap(rmc));   // over the one cable without wiring TX2->RX
#endif
}

// ---- control --------------------------------------------------------------
void handleControl() {
  int n = udp.parsePacket();
  if (!n) return;
  char buf[64]; int len = udp.read(buf, sizeof(buf) - 1); buf[len > 0 ? len : 0] = 0;
  String cmd = String(buf); cmd.trim(); cmd.toLowerCase();
  if (cmd == "off")        mode = OFF;
  else if (cmd == "step")  { mode = STEP; tStart = millis(); }
  else if (cmd == "ramp")  { mode = RAMP; tStart = millis(); }
  Serial.printf("[nmea] mode -> %d\n", (int)mode);
}

void setup() {
  Serial.begin(115200);
  Serial2.begin(NMEA_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);
  WiFi.softAP(AP_SSID, AP_PASS);
  udp.begin(CTRL_PORT);
  Serial.printf("[nmea] AP '%s' up; UDP ctrl %d; NMEA on TX%d @ %d baud\n",
                AP_SSID, CTRL_PORT, UART_TX_PIN, NMEA_BAUD);
}

void loop() {
  handleControl();
  emitFix();          // ~1 Hz fix like a real receiver
  delay(1000);
}
