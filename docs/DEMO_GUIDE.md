# Demo Guide — presenting the Maritime Cyber Range

> This guide predates and still works with the original, generic
> `profiles/{wamv,blueboat,bluerov2}.json` boot path used below. For the
> current primary demo set — real, individually-named Navy/research
> vehicles (Textron CUSV, REMUS-100), plus the CLI resilience tester and
> cross-target report — see `docs/TWIN_DEMO_GUIDE.md` instead.

A hybrid presentation: **Gazebo 3D** for physical immersion + the **live dashboard**
for the cyber story. Each shows what the other can't.

> Why both: the perception attacks (GPS/AIS spoof) are **invisible in Gazebo** —
> during a GPS spoof the boat doesn't physically move, only ArduPilot's *belief*
> does. The dashboard makes that visible (true vs. believed diverging, AIS
> contacts, live detector alerts). Gazebo shows the physical world and the C2
> attack / AUV diving, which the map can't convey.

## One-command launch

```bash
tools/run_demo.sh wamv up          # boots sim + dashboard together
#  -> open http://localhost:8080
tools/view_3d.sh                   # optional: attach the Gazebo 3D GUI (needs a GPU desktop)
...
tools/run_demo.sh wamv down        # tear everything down
```

`run_demo.sh <profile> status` health-checks the whole demo.
**Switching vehicle** is one command (it auto-clears whatever is running):
`tools/run_demo.sh bluerov2 up` (or `wamv` / `blueboat`), then reload the page.
 Profiles:
`wamv` (surface, richest), `blueboat` (2nd surface vehicle), `bluerov2` (AUV).

**GPU note:** the dashboard is GPU-free and works anywhere. The Gazebo 3D GUI
needs working OpenGL/GPU acceleration — run it on your real laptop desktop
(NVIDIA/Intel driver active), not a headless/remote display.

## Pre-flight (do this right before you present)

- **Boot fresh.** A long-running session lets the vehicle drift and its
  navigation state degrade, so click-to-navigate starts wandering instead of
  converging. Always start clean:
  `tools/run_demo.sh wamv down && tools/run_demo.sh wamv up` — then open the
  dashboard. On a fresh boot the boat converges cleanly (e.g. 59 m → ARRIVED).
- **Confirm health:** `tools/run_demo.sh wamv status` should show 4 sim checks
  [OK] + dashboard http 200.
- **Sanity-click** a destination once and watch "metres to go" tick down to
  ARRIVED before the audience is watching.
- Have the backup screencast open in another tab in case of a live hiccup.

## Suggested flow (~7 min)

1. **Open (Gazebo 3D, if GPU available)** — "This is a full-physics maritime
   simulator: a real USV hull on water, driven by real ArduPilot autopilot
   firmware. Same stack scales to an underwater AUV." Optionally dive the AUV
   (`bluerov2`) — visually striking.

2. **Switch to the dashboard** — point out the two dots on top of each other:
   blue = **true** position (ground truth), red = **believed** (what ArduPilot
   thinks). "Spoof error: ~0 m. The vehicle knows where it is."

3. **GPS spoof** — `echo step > /tmp/mcr_run/wamv/relay.fifo`
   - The **red trail peels away from blue**; the amber line stretches; the big
     **spoof-error number jumps to ~50 m and turns red**; a **GPS_SPOOF alert**
     fires. "The boat is now confidently 50 m wrong — and a detector that never
     saw the attack caught it from the telemetry alone." Then `echo off > …fifo`
     and watch it recover.

4. **AIS spoof** — run the ghost + impersonation (see `run_attack_suite.py` or
   `attacks/ais_spoof.py`). A **phantom vessel** and a **second "us" in the wrong
   place** appear; **AIS_SPOOF alerts** fire. "Fake traffic picture — collision
   risk and identity confusion."

5. **C2 injection** — forged RC override (see `attacks/c2_replay.py`). The **blue
   (true) marker itself moves** — visible in Gazebo too. "No sensor lied; the
   attacker seized the actuators directly." **C2_REPLAY alert** fires.

6. **Quantify** — stop the dashboard, then:
   ```bash
   tools/run_attack_suite.py --profile wamv     # PASS/FAIL per attack
   tools/score_detectors.py --alerts …          # precision / recall
   ```
   Reference numbers: surface precision 1.00 / recall 1.00; underwater recall
   1.00. "The blue team is graded against ground truth it never had access to."

7. **Depth story (optional)** — `run_demo.sh bluerov2 up`: the AUV uses acoustic
   positioning (not GPS); `acoustic_spoof` walks its believed position off while
   it sits still — the submerged analog. Shows the dual-domain design.

## Backups (never skip)

- Record a screencast of steps 2–6 as a safety net.
- The committed `evidence/*.log` files are the written record of every result.
- If Wi-Fi is unreliable, the dashboard's map tiles/JS come from CDNs — vendor
  them locally beforehand (or present where internet is reliable).
