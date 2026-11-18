# Maritime Cyber Range — How to Run & Simulate Everything

Every command you need, in one place. For *what the project is* and *why*,
read [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) first.

There are a few ways to run it:

- **A. The operator application** (`tools/app.sh`) — the Godot 3D console, one
  window, pick a site + twin and go. Needs a graphical display. **The quickest
  way to see it live.**
- **B. From source** — natively on an Ubuntu box with the toolchain, or via
  the project's own Docker build (serves the browser dashboard at `:8080`).
- **C. A shareable package** — a single self-extracting Ubuntu `.run` / Windows
  `.zip` (Docker only, no toolchain). **Built on demand** by `deploy/docker_packaging/build-*.sh`;
  the repo no longer ships a prebuilt copy.

The browser dashboard opens at **http://localhost:8080** and defaults to the
**Kochi** test site; pick the twin from the header dropdown.

---

## A. The operator application (`tools/app.sh`)

The Godot 3D console — one window, no browser, no separate Gazebo window. It
auto-routes each vehicle to its best physics engine (the AUV-150 onto the tuned
Stonefish stack, the rest onto Gazebo + the site's real-data models).

```bash
tools/app.sh                 # Godot console (default); needs $DISPLAY
tools/app.sh stonefish       # force the Stonefish engine for all vehicles
tools/app.sh gazebo          # force the Gazebo engine for all vehicles
tools/app.sh pygame          # legacy pygame console (no GPU shaders)
```

Pick a site and twin in the window, watch it move, click the sea to set a
destination, and fire the attack buttons. The Godot modes need the Godot 4
binary (see `tools/godot_app.sh`); Stonefish needs its one-time `MCR` build
(see `stonefish/README.md`).

---

## B. Run from source (Docker build / browser dashboard)

From the repo root:

```bash
./launch.sh build      # build the mcr:latest image (first time, long)
./launch.sh up         # boot the default twin + dashboard
# open http://localhost:8080
./launch.sh gui        # (optional) attach the Gazebo 3D window (needs X/GPU)
./launch.sh down       # stop
```

### Scale-up preview image (`mcr:dev`)

The multi-site/scale-up features ride on an overlay image built on top of the
frozen `mcr:latest`:

```bash
docker build -f deploy/Dockerfile      -t mcr:latest .   # frozen base
docker build -f deploy/Dockerfile.dev  -t mcr:dev    .   # + scale-up overlay
docker run --rm -p 8080:8080 mcr:dev            # dashboard at :8080 (Kochi)
```

---

## C. Build a shareable package (optional)

For handing the range to someone with only Docker (no toolchain), build the
single-file package — the repo does not ship a prebuilt one:

```bash
deploy/docker_packaging/build-linux.sh       # -> dist/MaritimeCyberRange-linux.run (self-extracting)
deploy/docker_packaging/build-windows.sh     # -> dist/MaritimeCyberRange-windows.zip
```

The recipient runs `./MaritimeCyberRange-linux.run` (or, on Windows, unzips and
double-clicks `MaritimeCyberRange.exe`, keeping `mcr-image.tar.gz` beside it),
which loads the bundled image and serves the dashboard at
**http://localhost:8080**. Stop with `docker rm -f mcr`. Requires ~25 GB free
disk and CPU virtualization (Docker/WSL2).

---

## Selecting a twin and a site

The four twins are `interceptor_usv` and `survey_usv` (surface) and `auv150`
and `maya_auv` (underwater) — see `PROJECT_OVERVIEW.md §5`.

### From the browser (easiest)

The dashboard header has two dropdowns:

- **Twin** — the four Indian platforms above.
- **Site** — Kochi · Mumbai · Visakhapatnam.

Changing either **reboots the stack** with that vehicle at that water body
(the map, GPS origin, water density, ocean current, and sound-speed physics
all follow) and the page reloads itself (~60–120 s).

### From the command line (native / in-container)

The active vehicle is `MCR_VEHICLE_PROFILE` (or the twin folder path); the
active site is `MCR_SITE` (defaults to `kochi`):

```bash
# interceptor USV at Mumbai, with dashboard + ocean current:
MCR_SITE=mumbai tools/run_demo.sh vehicle_twins/interceptor_usv up

# AUV-150 at Visakhapatnam, headless (no dashboard):
MCR_SITE=visakhapatnam tools/run_vehicle.sh vehicle_twins/auv150 up
```

Inspect a site's computed physics any time:

```bash
tools/site_info.py kochi          # density, sound speed, current, USBL range
```

---

## Firing attacks

### From the dashboard

Click an attack button in the Attack Console: **GPS Spoof**, **AIS Spoof**,
**C2 Inject** (choose the forged command), **Acoustic Spoof** (AUV). Watch the
true (orange) vs believed (blue) markers diverge, the **Position Integrity**
deviation climb, and live detector alerts appear. **Stop Attacks** restores
course; **Report** produces a downloadable PDF.

### Headless — the resilience tester (primary deliverable)

Boot a twin, run its full enabled attack suite, read the verdict, tear down:

```bash
tools/run_vehicle.sh vehicle_twins/interceptor_usv up
python3 tools/test_target.py --target vehicle_twins/interceptor_usv/target.json
tools/run_vehicle.sh vehicle_twins/interceptor_usv down
```

Writes `target_runs/interceptor_usv/<timestamp>/verdicts.json` with a
four-outcome verdict per attack (VULNERABLE / RESILIENT / N/A / INCONCLUSIVE)
and a blind-detector alert count.

Point it at **any** ArduPilot SITL (not just this repo's twins) with a
connection-only `targets/*.json`:

```bash
python3 tools/validate_target.py targets/mytarget.json      # pre-flight check
python3 tools/test_target.py --target targets/mytarget.json
```

### Re-verify all four twins at once

```bash
python3 tools/test_all_4.py        # boot → attack → tear down each twin
```

---

## Reproduce the multi-site attack matrix

Run one vulnerable twin's attacks at each site and collect the verdicts
(this is how the §5 table in the overview was produced):

```bash
for SITE in kochi mumbai visakhapatnam; do
  MCR_SITE=$SITE tools/run_vehicle.sh vehicle_twins/interceptor_usv up
  python3 tools/test_target.py --target vehicle_twins/interceptor_usv/target.json
  MCR_SITE=$SITE tools/run_vehicle.sh vehicle_twins/interceptor_usv down
done
# verdicts land in target_runs/interceptor_usv/<timestamp>/verdicts.json
```

(`tools/test_all_sites.py` automates this twin × site matrix and the
cross-site invariance check.)

In the Docker image the app's Python deps live in a venv — prefix with
`export PATH=/opt/mcr-venv/bin:$PATH` (and source ROS) if you run these
by hand inside the container.

---

## Scripted scenarios (site-aware)

```bash
python3 tools/run_scenario.py scenarios/harbor_transit_gps_walkoff.json --site kochi --out report.html
```

Emits a markdown/HTML report with a tactical map, position-divergence chart,
and the site's sound-speed profile. Consequences (position divergence, no-go
breach, grounding, CPA violation) map to IACS UR E26/E27 and IMO MSC.428(98).

---

## Native first-time setup (Ubuntu, from scratch)

Only needed if you are **not** using Docker. The upstream build trees live
under `external/` (consolidated from `$HOME`, with compat symlinks at `$HOME`
so these scripts run unchanged):

```bash
git clone --recurse-submodules <this repo>
sim_config/install_ros2.sh          # ROS 2 Jazzy
sim_config/install_gazebo.sh        # Gazebo Harmonic
sim_config/install_ardupilot.sh     # ArduPilot SITL prerequisites
sim_config/build_ardupilot.sh       # builds ardurover + ardusub
sim_config/install_sim_assets.sh    # ardupilot_gazebo, SITL_Models, DAVE AUV
cd ros2_ws && colcon build && cd .. # vendored VRX (WAM-V) workspace
```

No GPU is needed for the CLI tester or the web dashboard; a GPU desktop is
only required for the Gazebo 3D window (`tools/view_3d.sh`).

---

## Teardown & troubleshooting

```bash
tools/run_demo.sh <profile> down     # stop a native stack
docker rm -f mcr                     # stop the packaged/container app
```

- **Dashboard shows "Offline".** The browser loads Leaflet/Socket.IO from a
  CDN — the viewing machine needs internet even though the sim is local.
- **A verdict comes back INCONCLUSIVE.** The tester refuses to over-claim: if a
  precondition isn't met (e.g. the vehicle never confirmed armed) it reports
  INCONCLUSIVE rather than guessing. If a twin resists an attack with its fused
  state unmoved, that's RESILIENT — see `PROJECT_OVERVIEW.md §7`.
- **One run lands INCONCLUSIVE on an AUV RC-override.** ArduSub's ~1 s
  auto-disarm race; just re-run.
- **`wamv` won't boot in Docker.** Known VRX-in-container limitation; use the
  4 primary twins, or boot `wamv` natively.
