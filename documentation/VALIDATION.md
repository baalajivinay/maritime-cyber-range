# Validation — fidelity comparison & attack-class validation

How much should you trust a result from this range? Two independent questions,
answered honestly, with the gaps marked:

1. **Fidelity** — do our digital twins *represent* the real Indian vehicles?
   (Compared against the vehicles' published specs and real **sea-trial** data.)
2. **Attack-class validation** — are the vulnerabilities we report *real*?
   (Compared against real-world **field demonstrations** of the same attacks.)

> **Up front, the honest limit:** no one has publicly run a cyber/spoofing
> attack on a real Maya, AUV-150, or Indian USV, so there is **no real-vehicle
> attack result to compare our verdicts against for these exact hulls**. The
> real testbed data that *does* exist for them is **operational** (navigation /
> control sea trials). Our attack verdicts are instead validated against real
> field demonstrations on **comparable platforms** (a real yacht, real UAVs).

---

## 1. Fidelity comparison — twin vs real vehicle

Each twin runs the **real autopilot firmware** (ArduPilot/ArduSub) over the real
**MAVLink** protocol, so the *command/logic* layer is high-fidelity. The **hull
body** is a representative Gazebo model (Tier-A), so *hydrodynamic* behaviour is
approximate. The table marks each attribute **exact / encoded / representative**.

### 1a. AUV-150 (CSIR-CMERI + IIT-Kharagpur) → twin `auv150`
| Attribute | Real (published) | Twin `auv150` | Status |
|---|---|---|---|
| Domain | underwater AUV | underwater (ArduSub) | exact |
| Length / dia | 4.8 m / 0.5 m | body: BlueROV2 (~0.46 m) | representative |
| Mass | ~490 kg | body: BlueROV2-class | representative |
| Depth rating | 150 m | EK3 depth control (no hard cap) | encoded (domain) |
| Max speed | ~3 kn (~1.5 m/s) | not hull-accurate (Tier-A body) | representative |
| Propulsion | **5 thrusters / 5-DOF** | BlueROV2 multi-thruster vectored (6) | representative (multi-thruster class) |
| Nav suite | GPS, INS, DVL, altimeter | EK3 ExternalNav (acoustic/DVL) src | encoded |
| **Sea-trial behaviour** | 150 m reached (Chennai, 17 Jul 2011); 20 m in ~100 s; ~0.2 m/s heave; ~1.5 m/s (3 kn) forward | **measured in Gazebo:** forward **1.25 m/s**, descent **1.11 m/s** | forward ✅ ~ (1.25 vs 1.5); descent ✗ 5× fast (light body) |

### 1b. Maya (CSIR-NIO, Goa) → twin `maya_auv`
| Attribute | Real (published) | Twin `maya_auv` | Status |
|---|---|---|---|
| Domain | underwater AUV | underwater (ArduSub) | exact |
| Length / dia | ~1.7 m / 0.234 m | body: REMUS-100 (~1.6 m / 0.19 m) | representative (close class) |
| Mass | ~55 kg | body: REMUS-100-class | representative |
| Depth rating | 200 m | EK3 depth control | encoded (domain) |
| Speed | ~1.2–1.5 m/s | not hull-accurate | representative |
| Propulsion | 1 aft thruster + 2 stern planes + 2 rudders | REMUS-100 torpedo (single screw) | **good class match** |
| **Trial behaviour** | depth/heading autopilots; ~1.2–1.5 m/s | **measured, after hull calibration:** forward **1.65 m/s**, descent **0.75 m/s** (was 3.28 / 1.79 before) | ✅ forward now ~real; descent 2.4× better |

### 1c. Fast interceptor USV (A2NCS, BEL/WESEE) → twin `interceptor_usv`
| Attribute | Real (published) | Twin `interceptor_usv` | Status |
|---|---|---|---|
| Domain | surface USV | surface (ArduRover) | exact |
| Length | ~16.3 m LOA | body: CUSV | representative |
| Top speed | ~45 kn (~23 m/s) | **measured in Gazebo: 1.05 m/s** | ✗ huge gap — CUSV body is a slow displacement hull, not a planing interceptor |
| Hull | planing monohull | body: CUSV (differential) | representative |
| Autonomy | A2NCS (retrofit) | ArduRover stand-in | representative (logic layer faithful) |
| Sensors | GPS, AIS, IMU, radar | GPS + AIS + MAVLink present | encoded |

### 1d. Small coastal-survey USV → twin `survey_usv`
| Attribute | Representative class | Twin `survey_usv` | Status |
|---|---|---|---|
| Domain | surface survey USV | surface (ArduRover) | exact |
| Length | ~4–6 m catamaran | body: BlueBoat (~1.2 m catamaran) | representative (scaled) |
| Speed | ~1–2 kn (~0.5–1.0 m/s) | Gazebo run did not produce clean forward motion (skid-steer/model detail) | not cleanly measured |
| Hull | twin-hull differential | BlueBoat (twin-hull differential) | **good class match** |
| Sensors | GPS, AIS, MBES | GPS + AIS present | encoded |

**Reading the fidelity table:** *exact* = identical to the real vehicle;
*encoded* = the real property is represented in the autopilot config/EKF;
*representative* = a stand-in body of the right class, not the real geometry/
hydrodynamics. **A security verdict depends on the *encoded/exact* rows (domain,
firmware, protocol, sensor-source, command link) — not on the representative
hull.** The hull only affects *how far/fast* a position walks off, not *whether*
the vehicle accepts the forged input.

### 1e. Measured dynamic fidelity (Gazebo runs, Kochi site, 2026-10-20)
Each twin was booted in the full Gazebo stack, armed, and driven (MANUAL + RC
override); behaviour measured from telemetry and compared to the real figures.

**Root cause of the first-pass gaps.** The twins reuse stock Gazebo demo bodies
whose **thruster force, mass and drag are the demo vehicle's, not the real
Indian vehicle's.** Terminal speed is `v = √(T / drag)`, so a body carrying too
much thrust (or too little drag) for its real counterpart runs too fast:
- `maya_auv` ran on the REMUS body's **6 BlueROV2-derived vectored thrusters** —
  the real Maya has **one** — so it over-thrust to 3.28 m/s (real ~1.5), and the
  same strong vertical thrusters on a light, low-heave-drag body dived too fast.
- `interceptor_usv`'s CUSV body is a **7700 kg displacement hull whose model
  explicitly states "no planing-lift term — it cannot plane"** → it cannot reach
  45 kn by *any* parameter tuning.

**Fix applied — hull calibration (drag).** For the twin-exclusive `remus100`
body (`maya_auv`), surge drag was calibrated so full-throttle terminal speed
matches the real vehicle and heave drag raised to slow the descent. Tuning
*drag* (not thrust) keeps full control authority and changes **no** security
verdict (those depend on servo/command response, not top speed).

| Twin | Metric | Real | Before | **After fix** | Verdict |
|---|---|---|---|---|---|
| `maya_auv` | forward | ~1.2–1.5 m/s | 3.28 | **1.65 m/s** | ✅ now ~real |
| `maya_auv` | descent | ~0.2 m/s | 1.79 | **0.75 m/s** | ✅ 2.4× closer |
| `auv150` | forward | ~1.5 m/s | 1.25 | 1.25 m/s | ✅ already close (~17% low) |
| `auv150` | descent | ~0.2 m/s | 1.11 | 1.11 m/s | ⚠️ same drag fix applies, but its `bluerov2` body is shared with the generic profile → needs a per-twin copy to tune safely |
| `interceptor_usv` | top speed | ~23 m/s (45 kn) | 1.05 | 1.05 m/s | ✗ **body-class limit** — displacement hull can't plane; needs a planing-hull model, not a parameter |
| `survey_usv` | survey speed | ~0.5–1.0 m/s | — | not cleanly measured | arming precheck in the quick harness; the slow displacement `blueboat` body is the right class for this regime |

**What this means.** Where the body was twin-exclusive and editable (`maya_auv`),
calibration brought it to the real vehicle's speed. The remaining gaps are two
honest kinds: **shared-body** (`auv150`, `survey_usv`) — fixable by the same drag
calibration in a per-twin model copy; and **body-class** (`interceptor_usv`) —
not a tuning problem at all, a 45 kn planing interceptor needs a planing-hull
model. **None of it changes a security verdict:** attacks succeed/fail at the
command/protocol/EKF layer (real); hull speed only sets *how far* a spoof walks
the vehicle, never *whether* it accepts the spoof. Full dynamic fidelity = Tier-B
= per-twin models with each real vehicle's measured mass/thrust/hydrodynamics.

---

## 2. Attack-class validation — our verdicts vs real field tests

For each vector we report a verdict in simulation. Here is the **real-world
evidence that the same class of attack genuinely works** on comparable vehicles.

| Our vector (sim verdict) | Real-world field demonstration | What it proved | Match |
|---|---|---|---|
| **GPS spoof** → VULNERABLE (surface twins) | **UT Austin spoofed a real 65 m yacht** in the Mediterranean (Humphreys et al., "Hostile Control of Ships via False GPS Signals") | an unauthenticated GNSS spoof silently drove a real vessel off course (disguised as current) — hostile control | ✅ same mechanism, real vessel |
| **GPS spoof** → VULNERABLE | **Real UAVs spoofed over-the-air** (USENIX Security 2022, Sathaye et al.) | live GPS spoofing achieved position takeover on real autonomous vehicles | ✅ real-vehicle class |
| **C2 replay** (SET_MODE / RC override) → VULNERABLE | **Our own ESP32 HIL** (real hardware over real WiFi) + public MAVLink-has-no-auth research | unauthenticated MAVLink command injection seizes mode/actuators — we demonstrated it from *real hardware*, not just sim | ✅ reproduced on real hardware here |
| **AIS spoof** → N/A-to-autopilot / detectability-only | AIS spoofing demonstrated repeatedly **in the wild** (fake tracks, identity spoofing — documented real incidents) | AIS is trivially forgeable and is an operator/ECDIS-layer risk — exactly how our range treats it | ✅ our classification matches reality |
| **Acoustic / ExternalNav spoof** → VULNERABLE (AUV twins) | **No real AUV acoustic-spoof field test exists** (gap). Nearest: external-vision/mocap spoofing research + the GPS-spoof principle applied to the acoustic positioning channel; USV position-spoofing (simulation, MDPI *JMSE* 2025) | class-plausible and consistent with how ArduSub fuses ExternalNav, but **not** yet field-proven on a real AUV | ⚠️ honest gap — sim/analogue only |

**Interpretation:** three of our four vectors (GPS, C2, AIS) reproduce
vulnerabilities that have been **demonstrated on real vehicles or in the real
world**; the C2 vector we additionally reproduced on **real ESP32 hardware** in
this project. The acoustic vector is the one honest gap — no real AUV has been
publicly acoustic-spoofed, so that verdict rests on protocol logic + analogues,
not a field test.

---

## 3. What this means for trusting a result
- **Vulnerability findings (VULNERABLE/RESILIENT):** high confidence — real
  firmware + real protocol, and the vector classes are field-confirmed on
  comparable platforms (and on our own hardware for C2).
- **Divergence magnitudes / dynamics:** representative — the hull bodies are
  Tier-A stand-ins; climb to Tier-B with the site dataset binding
  (`scaleup/physics/environment.py`) and a measured hull if exact numbers matter.
- **Acoustic vector:** treat as a credible *hypothesis* pending a real
  acoustic-modem/tank test.

## Sources
- Maya control/field trials — Maurya, Desa & Sebastião, *Control of the Maya AUV
  in the vertical and horizontal planes*; "The small Maya AUV — initial field
  results".
- AUV-150 sea trials — "AUV for 150 m Depth — Development Phases"; NISCPR IJMS
  43(1) 106-110; navaldrones.com AUV-150.
- Interceptor / A2NCS — Indian Navy USV / BEL-WESEE A2NCS reporting; Solas Marine
  fast interceptor class (16.33 m, 45 kn).
- Yacht GPS spoof — Humphreys et al., *Hostile Control of Ships via False GPS
  Signals: Demonstration and Detection* (UT Austin Radionavigation Lab).
- Real-UAV GPS spoof — Sathaye et al., USENIX Security 2022.
- USV position spoofing (simulation) — *JMSE* 13(12):2269, 2025.
