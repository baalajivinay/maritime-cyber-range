# Running the 4 vehicle twins yourself — step by step

Four self-contained digital twins live under `vehicle_twins/`: 2 MASS
(surface) vehicles and 2 AUVs, one vulnerable and one resilient in each
pair. Every result below was run live against the real ArduPilot/Gazebo
stack while building this, not assumed — see each twin's own `README.md`
for the exact evidence.

**These are copies of real, individually-named vehicles, not generic
hobbyist platforms**: the MASS pair is the Textron Fleet-class CUSV (a real,
currently-active US Navy mine-countermeasures/ASW USV), and the AUV pair is
the REMUS-100 (a real US Navy shallow-water mine-countermeasures AUV, and
the single most-cited AUV in academic hydrodynamics literature). Hull mass,
dimensions, and hydrodynamics are sourced and cited in each twin's own
`README.md` and `model.sdf` header — see those for the full provenance
trail and any disclosed simplifications (REMUS-100's actuation in
particular: see below).

```
vehicle_twins/
  mass_vulnerable_cusv/              real Textron Fleet-class CUSV, out-of-the-box config
  mass_resilient_cusv/               same real CUSV hull, hardened GCS-link + GPS fusion
  auv_vulnerable_remus100/           real REMUS-100, out-of-the-box config
  auv_resilient_remus100_hardened/   same real REMUS-100 hull, hardened GCS-link config
```

This project's original reference twins (WAM-V, BlueBoat, BlueROV2) were
retired and removed once this real-vehicle set replaced them as the
primary (and now only) demo set — see `docs/EXECUTION_STATE.md`'s dated
removal entry. Their underlying hull models
(`sim_config/models/blueboat/`, `sim_config/models/bluerov2/`, plus the
VRX-based WAM-V) are still on disk and still boot via `profiles/wamv.json`
/ `blueboat.json` / `bluerov2.json` directly — `docs/NEW_AUV_QUICKSTART.md`
still uses BlueROV2 as a clone base for building a brand-new AUV twin from
scratch — but they no longer have their own `vehicle_twins/` packages.

Each folder contains everything specific to that twin: `profile.json` (+
`hardened.parm` for the resilient ones), `target.json` (for the resilience
tester), and a `README.md` with its exact expected result and why.

**What "resilient" means here, honestly**: not a placeholder label. The
hardened twins have real, current ArduPilot security mechanisms turned on
and verified live, mechanism by mechanism, before being combined into these
twins. On the surface (MASS) twins that's two mechanisms: `GPS1_TYPE=14`
for GPS/EKF fusion plus `MAV_GCS_SYSID`+`MAV_OPTIONS=1` for GCS-link
enforcement. On the underwater (AUV) twins GPS is structurally N/A (RF
doesn't penetrate water, real physics, not a config choice) — only the
GCS-link mechanism applies there. See
`vehicle_twins/mass_resilient_cusv/hardened.parm` for the full
GPS1_TYPE=14 verification notes and
`vehicle_twins/auv_resilient_remus100_hardened/hardened.parm` for the
underwater-specific trim (deliberately NOT the BlueROV2 DAVE defaults file
verbatim — see its header for what was kept vs. dropped and why).

**REMUS-100's disclosed actuation simplification**: the real REMUS-100 is
fin-steered (one propeller plus rudder/stern-plane control fins). No
ArduPilot firmware supports that scheme for an underwater vehicle — this
twin uses a 6-thruster vectored frame instead (the same proven architecture
BlueROV2 already uses on ArduSub). Real hull physics, disclosed simplified
actuation. Full investigation trail (including a genuine attempt via
ArduPlane firmware that hit a firmware-level dead end) is in
`vehicle_twins/auv_vulnerable_remus100/README.md` and
`docs/EXECUTION_STATE.md`'s dated entries.

## 0. One-time check

```bash
cd /home/vinay/maritime-cyber-range
ps aux | grep -E "ardurover|ardusub|gz sim|dashboard_server" | grep -v grep
```

Should print nothing. If it does, tear down whatever's running first (see
step 5) before starting a twin.

## 1. Pick a twin and boot it

These are two different demo modes, not two options for the same thing —
pick based on what you're about to do next.

**Headless** (just the simulator — for running the CLI resilience tester,
step 2 below):

```bash
tools/run_vehicle.sh vehicle_twins/mass_vulnerable_cusv up
```

**With the live dashboard** (simulator + browser UI, for clicking through
attacks live — step 4 below):

```bash
tools/run_demo.sh vehicle_twins/mass_vulnerable_cusv up
```

Both accept any of the 4 folder paths above. Wait for `STACK UP` / `DEMO UP`
before continuing — takes about 30-60s. The dashboard boot tries to open
your web browser to `http://localhost:8080` automatically; if nothing pops
up (e.g. no desktop available), open a browser yourself and go to that
address — the server is running either way, only the auto-open can fail.

## 2. Run the resilience test

Do this against a **headless** boot (previous step). ArduPilot SITL only
exposes 3 raw MAVLink ports, and the dashboard's own background threads
already hold 2 of them from the moment it starts — `test_target.py` now
routes around that conflict automatically (verified during a full dry run,
2026-08-08) so it won't hang or silently misreport if you do run it while
the dashboard is up, but its AIS detectability score specifically can't be
trusted in that case (the dashboard and the tester both want exclusive
control of the same AIS UDP port; whichever one loses the race gets a clear
`[test_target] WARNING: ... ais_spoof recall below is not a real
measurement` instead of a wrong number). Headless avoids this entirely.

```bash
python3 tools/test_target.py --target vehicle_twins/mass_vulnerable_cusv/target.json
```

Prints a verdict per attack as it runs, then writes
`target_runs/mass_vulnerable_cusv/<timestamp>/verdicts.json`.

## 3. Generate the CROSS-TARGET report (terminal, from step 2's data)

```bash
python3 tools/generate_target_report.py
```

Writes `target_runs/resilience_report.html` — open it in a browser. It
compiles **every** target this repo has ever tested (all 4 twins once
you've run each), each with a vulnerability table, a detectability table,
a recommendation next to every VULNERABLE finding, and one synthesized
deployment-readiness verdict.

**This is one of two separate report mechanisms in this project — they
don't depend on each other, and mixing them up is an easy mistake:**

| | This one (steps 2-3) | The dashboard's own (step 4 below) |
|---|---|---|
| How you run it | terminal, `test_target.py` then `generate_target_report.py` | click "📊 Report" in the browser |
| Needs a headless boot? | yes (see step 2's port-sharing note) | no — works anytime the dashboard is up |
| Covers | every target ever tested, all 4 twins side by side | only the current session's own attacks |
| Output | `target_runs/resilience_report.html` (open manually) | PDF, one click to download |

If all you want is a PDF of what you just demoed, skip straight to step 4
— you never need to touch this CLI path at all.

## 4. The dashboard (if you booted with `run_demo.sh`)

Open **http://localhost:8080**. A few things are true by design, and are
re-verified live as of the 2026-08-08 dry run (real numbers below, not
placeholders):

- **Shows only the vehicle you booted.** No vehicle-switcher, no dropdown
  listing other twins — the header reads exactly the profile you launched.
- **Nothing happens automatically.** Every attack (GPS spoof / AIS spoof /
  C2 inject) only runs after you click its button. Nothing is scheduled or
  triggered on a timer.
- **GPS spoof** (vulnerable twins): click it, the "GPS / POSITION SPOOF
  ERROR" panel jumps to ~50m and flags "believed position DIVERGED from
  true"; the alert panel logs `GPS_SPOOF ... believed position moved at
  ~400+ m/s (> 15) -- implausible` within about 0.1s of the jump.
- **AIS spoof** (any twin): click it, alerts for both a ghost-vessel MMSI
  and an impersonation of the real vessel's MMSI appear within ~0.01-2s.
- **C2 inject** (any twin): on a **vulnerable** twin it actually arms and
  seizes the vehicle (speed jumps off zero, `Armed` flips to ARMED),
  detected in a few seconds. On a **resilient** twin, click the same
  button and watch it *fail* — mode stays MANUAL, stays disarmed, speed
  stays 0.00 — that side-by-side contrast is the strongest live moment in
  this whole demo, worth doing both twins back to back if you have time.
  **Let it finish before clicking Stop** (its own arm-sequence + override
  cycle takes ~15s): the RC-override variant logs its ground-truth row only
  at the end of that cycle (confirmed live, 2026-08-09), so cutting it off
  early with "Stop Attacks" can leave the live detector's alert(s) with no
  matching ground truth to score against — the on-screen alert is still
  real, but the session report's `c2_replay` row can show a spurious false
  positive for that run. Not a bug, just a report-scoring artifact of
  interrupting a post-hoc-logged action mid-flight.
- **Closing the dashboard stops any running attack.** Close the tab (or the
  last tab if you have more than one open) and the server detects the
  disconnect and stops whatever attack was active — you don't have to
  remember to click "Stop attacks" first.
- **Report → Download PDF.** Click "📊 Report", then "⬇ Download PDF" for a
  file you can hand off or drop into slides, not just an on-screen view.
  This is the dashboard's own report (see the table in step 3 above) — it
  works live, right now, no terminal needed.

**One real limitation to know about for the resilient twins specifically**:
their `GPS1_TYPE=14` config means GPS position only exists while something
is actively feeding `GPS_INPUT` — that's `tools/test_target.py`'s own job
during a test run (step 2), not something the dashboard does in the
background. So on the dashboard, the resilient twins' "GPS spoof" button
and the true-vs-believed GPS panel won't show a live position the way the
vulnerable twins' do. The GPS resilience result itself is real and
verified (see each resilient twin's `README.md`) — it's just demonstrated
through `test_target.py` + the report, not the dashboard's GPS panel. C2
(mode-change / RC-override) demonstrates fully live on the dashboard for
every twin, vulnerable and resilient alike — that's the one worth clicking
through live on stage.

## 5. Tear down

```bash
tools/run_vehicle.sh vehicle_twins/mass_vulnerable_cusv down
# or, if you booted with the dashboard:
tools/run_demo.sh vehicle_twins/mass_vulnerable_cusv down
```

Always tear down before booting a different twin — only one vehicle's
stack can run at a time (they share ports).

## Reading the verdicts

Four outcomes, not a binary pass/fail — see `docs/TARGET_TESTING.md` for
the full methodology. What you'll actually see across the 4 twins:

| Twin | mode-change | RC-override | GPS spoof | AIS spoof | Deployment verdict |
|---|---|---|---|---|---|
| `mass_vulnerable_cusv` | VULNERABLE | VULNERABLE | VULNERABLE | N/A | **NOT READY TO DEPLOY** |
| `mass_resilient_cusv` | RESILIENT | INCONCLUSIVE | N/A | N/A | **CONDITIONALLY READY** |
| `auv_vulnerable_remus100` | VULNERABLE | VULNERABLE | N/A (real physics) | N/A | **NOT READY TO DEPLOY** |
| `auv_resilient_remus100_hardened` | RESILIENT | INCONCLUSIVE | N/A (real physics) | N/A | **CONDITIONALLY READY** |

The resilient twins' RC-override shows INCONCLUSIVE, not a clean
RESILIENT — because the attacker can't even **arm** the hardened vehicle,
so the check correctly declines to claim more than it actually observed
(its own rule: "nothing moved" only counts as resilience if armed was
confirmed first). Being unable to arm at all is arguably *stronger*
evidence than a clean RESILIENT verdict, but the tool reports it honestly
rather than assuming that -- that conservative honesty is the whole point
of a testing tool you can trust the output of. Each resilient twin's
`README.md` explains this in full.

## If something doesn't match this table

Re-run step 2 once more before assuming something's wrong -- the C2
RC-override check has one known source of run-to-run variance documented
in `docs/TARGET_TESTING.md`'s "Known limitations" (a real ArduPilot
GCS/RC-failsafe race, not a bug in the check). Everything else in the
table above was reproduced multiple times while building this and was
stable.
