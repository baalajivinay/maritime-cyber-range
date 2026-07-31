# Deploy Guide — the Maritime Cyber Range as a Docker package

Everything the simulator needs — ROS 2 Jazzy, Gazebo Harmonic, ArduPilot SITL
(rover + sub), the ArduPilotPlugin, VRX, the BlueROV2 (dave) model, and this
project — is baked into **one Docker image**. A recipient installs Docker, builds
(or loads) the image once, and runs the launcher.

```
download → extract → ./launch.sh build → ./launch.sh up → open http://localhost:8080
```

## Requirements on the recipient's machine

| Want | Needs |
|---|---|
| The **web dashboard** (set vehicle, navigate, launch attacks, alerts, report) | Docker. No GPU. Any OS that runs Docker. |
| The **Gazebo 3D window** too | A **Linux** host with an X server and a GPU (Intel/AMD via `/dev/dri`, or NVIDIA via the nvidia-container-toolkit). |

Disk: ~15 GB for the image. First build pulls ROS desktop and **compiles ArduPilot
and VRX**, so it takes a while (tens of minutes) — subsequent builds are cached.

## One-time build

```bash
./launch.sh build
# equivalently: docker build --network=host -f deploy/Dockerfile -t mcr:latest .
```

> `--network=host` lets apt/git/pip in the build use the host's DNS. Some Docker
> setups otherwise can't resolve `archive.ubuntu.com` inside build containers;
> the launcher adds this flag for you.

Pin a different upstream if needed, e.g.
`./launch.sh build --build-arg ARDUPILOT_COMMIT=<sha>`.

### Sharing without rebuilding
Build once, then hand the image to others as a file:
```bash
docker save mcr:latest | gzip > mcr-image.tar.gz     # producer
# recipient:
gunzip -c mcr-image.tar.gz | docker load
./launch.sh up
```

## Running

```bash
./launch.sh up               # boot the underwater BlueROV2 (sim + dashboard), opens the browser
./launch.sh gui              # attach the Gazebo 3D window (Linux + X + GPU)
./launch.sh status           # health of the running stack
./launch.sh attack --profile bluerov2   # run the attack suite
./launch.sh logs             # follow the dashboard log
./launch.sh shell            # a shell inside the container (env pre-sourced)
./launch.sh down             # stop everything
```

> **Which vehicle runs in the container.** The default and the validated headless
> path is **`bluerov2`** (underwater) — it boots the sim, serves the dashboard,
> and runs the full attack/detection loop entirely inside Docker. The surface
> **`wamv` (VRX)** profile does **not** yet boot headless in a container: the VRX
> `sydney_regatta` world stalls during load in the containerized Gazebo server
> (the `ros_gz` spawn node loops "Requesting list of world names"; not caused by
> networking, GPU/X, or Fuel — the models are local). Run the surface vehicle
> **natively on your GPU workstation** (the repo's `tools/run_demo.sh wamv up`),
> where VRX works as designed. Making `wamv` boot headless in Docker (likely an
> `xvfb`/offscreen-rendering setup for VRX) is a known follow-up.

Then open **http://localhost:8080** — set a destination, launch GPS / AIS / C2 /
acoustic attacks, watch true-vs-believed diverge and the live detector alerts,
and hit **Report** for precision/recall. (Full presentation script:
`docs/DEMO_GUIDE.md`.)

## The 3D GUI (X11)

`./launch.sh up` runs the simulation **headless** inside the container; the
dashboard is served on port 8080. `./launch.sh gui` attaches the Gazebo 3D
*client* inside the same container and renders it to your host's X server.

The launcher wires this up automatically on Linux: `--net=host`, forwards
`$DISPLAY`, mounts `/tmp/.X11-unix`, runs `xhost +local:root`, and passes
`/dev/dri` for GPU rendering. If the window doesn't appear:

- **Permission denied on X:** run `xhost +local:root` in your host shell.
- **NVIDIA:** install the
  [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html);
  the launcher then adds `--gpus all` automatically.
- **No GPU / black window:** the launcher falls back to software GL
  (`LIBGL_ALWAYS_SOFTWARE=1`) — slow but functional. The dashboard is the
  reliable visual; the 3D view is the bonus.
- **macOS / Windows:** there's no native X server, so `up` runs dashboard-only
  (published on `localhost:8080`). For the 3D GUI you'd need XQuartz (mac) or
  VcXsrv (Windows) plus `-e DISPLAY=host.docker.internal:0` — Linux is the
  supported path for the GUI.

## What's inside (image layout)

The image reproduces the reference machine's `$HOME` so the repo's own
launchers run unmodified:

```
/root/ardupilot            ArduPilot SITL (ardurover + ardusub)      @ pinned commit
/root/ardupilot_gazebo     ArduPilotPlugin (libArduPilotPlugin.so)   @ pinned commit
/root/SITL_Models          shared Gazebo models / worlds
/root/auv_ws/src/dave      BlueROV2 model + ardusub.parm
/root/maritime-cyber-range this repo, with ros2_ws/ (VRX) rebuilt inside
/opt/ros/jazzy             ROS 2 Jazzy (desktop) + Gazebo Harmonic (ros_gz)
```

Build recipe: `deploy/Dockerfile` (mirrors `sim_config/install_*.sh` +
`build_*.sh`). Container entrypoint: `deploy/entrypoint.sh`. Host launcher:
`launch.sh`.

## Troubleshooting

- **`image 'mcr:latest' not found`** — run `./launch.sh build` first.
- **Port 8080 busy** — something else holds it on the host; free it, or edit the
  publish/port in `launch.sh`.
- **Rebuild after editing project code** — only the final layers rebuild (the
  repo COPY + VRX), so it's fast; the heavy ROS/ArduPilot layers stay cached.
- **Profile/sim mismatch warning in the dashboard** — the guard is telling you
  the running vehicle doesn't match the profile; `./launch.sh switch <vehicle>`
  to realign.
