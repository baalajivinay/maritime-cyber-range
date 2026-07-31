#!/bin/bash
# ============================================================================
#  Maritime Cyber Range -- one-command launcher (Docker)
#
#  Download -> extract -> ./launch.sh up  -> open http://localhost:8080
#
#  Verbs:
#    ./launch.sh build            build the image (first time, ~long: compiles
#                                 ArduPilot + VRX; needs internet + ~15 GB disk)
#    ./launch.sh up [vehicle]     boot sim + dashboard (default: bluerov2), open browser
#    ./launch.sh gui              attach the Gazebo 3D window  (needs X + GPU)
#    ./launch.sh switch <vehicle> change vehicle live         (wamv|blueboat|bluerov2)
#    ./launch.sh status           health of the running stack
#    ./launch.sh attack [args]    run the attack suite in the container
#    ./launch.sh shell            a shell inside the container (env pre-sourced)
#    ./launch.sh down             stop + remove the container
#    ./launch.sh logs             follow the dashboard log
#
#  The 3D GUI needs a Linux host with an X server and a GPU (Intel/AMD via
#  /dev/dri, or NVIDIA via nvidia-container-toolkit -- see docs/DEPLOY.md). The
#  web dashboard works everywhere with no GPU.
# ============================================================================
set -euo pipefail

IMAGE="${MCR_IMAGE:-mcr:latest}"
NAME="${MCR_CONTAINER:-mcr}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# bluerov2 (underwater) is the validated headless-container demo. The surface
# wamv/VRX world does not yet boot headless in Docker (see docs/DEPLOY.md); run
# that one natively on a GPU host. `up` with no arg uses this default.
DEFAULT_VEHICLE="bluerov2"

die(){ echo "Error: $*" >&2; exit 1; }
have(){ command -v "$1" >/dev/null 2>&1; }

have docker || die "Docker is not installed. See https://docs.docker.com/get-docker/"

image_exists(){ docker image inspect "$IMAGE" >/dev/null 2>&1; }
container_running(){ [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" = "true" ]; }

open_browser(){
  local url="$1"
  if   have xdg-open; then xdg-open "$url" >/dev/null 2>&1 &
  elif have open;     then open "$url" >/dev/null 2>&1 &
  fi
}

# Assemble the docker run flags for GUI (X11) + dashboard (port 8080).
run_flags(){
  local flags=(--name "$NAME" --hostname mcr -d --rm)
  if [ "$(uname -s)" = "Linux" ]; then
    # host networking = dashboard on localhost:8080 + simplest X/gz-transport
    flags+=(--net=host)
    # X server access for the 3D GUI
    if [ -n "${DISPLAY:-}" ] && [ -S /tmp/.X11-unix/X0 -o -d /tmp/.X11-unix ]; then
      flags+=(-e "DISPLAY=$DISPLAY" -e QT_X11_NO_MITSHM=1 -v /tmp/.X11-unix:/tmp/.X11-unix:rw)
      xhost +local:root >/dev/null 2>&1 || true
    fi
    # GPU: Intel/AMD via /dev/dri; software-GL fallback if absent
    if [ -d /dev/dri ]; then flags+=(--device /dev/dri); else flags+=(-e LIBGL_ALWAYS_SOFTWARE=1); fi
    # NVIDIA (if the container toolkit is installed)
    if have nvidia-smi && docker info 2>/dev/null | grep -qi nvidia; then
      flags+=(--gpus all -e NVIDIA_DRIVER_CAPABILITIES=all -e NVIDIA_VISIBLE_DEVICES=all)
    fi
  else
    # macOS/Windows: dashboard only (no native X); publish the port
    echo "[launch] non-Linux host: the 3D GUI needs extra X setup (docs/DEPLOY.md);" >&2
    echo "[launch] booting dashboard-only on http://localhost:8080" >&2
    flags+=(-p 8080:8080)
  fi
  printf '%s\n' "${flags[@]}"
}

cmd_build(){
  echo "[launch] building $IMAGE  (first build compiles ArduPilot + VRX -- grab a coffee)"
  # --network=host: apt/git/pip in the build reach the mirrors via the HOST's
  # DNS/network. Without it, some Docker setups can't resolve archive.ubuntu.com
  # inside build containers ('Temporary failure resolving ...'). Harmless where
  # build DNS already works.
  docker build --network=host -f "$REPO_DIR/deploy/Dockerfile" -t "$IMAGE" "$REPO_DIR" "$@"
  echo "[launch] built $IMAGE"
}

cmd_up(){
  local vehicle="${1:-$DEFAULT_VEHICLE}"
  image_exists || die "image '$IMAGE' not found -- run './launch.sh build' first."
  if container_running; then
    echo "[launch] container already running; switching to '$vehicle' instead."
    docker exec "$NAME" mcr-entrypoint switch "$vehicle"
  else
    mapfile -t FLAGS < <(run_flags)
    docker run "${FLAGS[@]}" "$IMAGE" up "$vehicle"
    echo "[launch] booting '$vehicle' ... (sim + dashboard)"
  fi
  echo "[launch] dashboard -> http://localhost:8080"
  open_browser "http://localhost:8080"
}

need_container(){ container_running || die "no running container -- run './launch.sh up' first."; }

cmd_gui(){    need_container; docker exec -it "$NAME" mcr-entrypoint gui; }
cmd_switch(){ need_container; docker exec "$NAME" mcr-entrypoint switch "${1:?usage: switch <wamv|blueboat|bluerov2>}"; open_browser "http://localhost:8080"; }
cmd_status(){ need_container; docker exec "$NAME" mcr-entrypoint status; }
cmd_attack(){ need_container; docker exec -it "$NAME" mcr-entrypoint attack "$@"; }
cmd_shell(){  need_container; docker exec -it "$NAME" mcr-entrypoint shell; }
cmd_logs(){   need_container; docker logs -f "$NAME"; }
cmd_down(){   docker rm -f "$NAME" >/dev/null 2>&1 && echo "[launch] stopped." || echo "[launch] nothing running."; }

VERB="${1:-help}"; shift || true
case "$VERB" in
  build)  cmd_build "$@";;
  up)     cmd_up "$@";;
  gui)    cmd_gui;;
  switch) cmd_switch "$@";;
  status) cmd_status;;
  attack|suite) cmd_attack "$@";;
  shell|bash)   cmd_shell;;
  logs)   cmd_logs;;
  down|stop)    cmd_down;;
  help|-h|--help)
    sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//';;
  *) die "unknown verb '$VERB' (try: ./launch.sh help)";;
esac
