#!/bin/bash
# In-container entrypoint. Re-entrant: PID 1 runs `up`; the host launcher calls
# the other verbs via `docker exec`. Sources ROS + the VRX workspace so the
# repo's own $HOME-relative launchers run unchanged.
REPO="$HOME/maritime-cyber-range"

# app Python deps live in this venv (see deploy/Dockerfile); put it first so the
# repo launchers' bare `python3 ...` calls resolve to it.
[ -d /opt/mcr-venv/bin ] && export PATH="/opt/mcr-venv/bin:$PATH"

# NOTE: no `set -u` here -- ROS/colcon setup.bash reference unbound vars while
# sourcing, which under `set -u` aborts the shell instantly (the container then
# exits 1 with no output). The repo's own launchers guard their own scripts.
source /opt/ros/jazzy/setup.bash 2>/dev/null || true
source "$REPO/ros2_ws/install/setup.bash" 2>/dev/null || true
cd "$REPO"

VERB="${1:-up}"; shift || true

case "$VERB" in
  up)
    # Accepts a twin folder path (vehicle_twins/<name>) OR a legacy profile name
    # (bluerov2|blueboat|wamv). Default = the CUSV twin (verified headless demo).
    PROFILE="${1:-vehicle_twins/mass_vulnerable_cusv}"
    echo "[mcr] booting '$PROFILE' (headless sim + dashboard) ..."
    tools/run_demo.sh "$PROFILE" up || echo "[mcr] boot reported an error -- see logs below"
    echo "[mcr] ---------------------------------------------------------------"
    echo "[mcr] Dashboard -> http://localhost:8080   (profile: $PROFILE)"
    echo "[mcr] 3D view   -> run './launch.sh gui' on the host (needs X/GPU)"
    echo "[mcr] ---------------------------------------------------------------"
    # keep PID 1 alive and surface the dashboard log; container stays up even if
    # a component dies mid-demo (so you can inspect it), until explicitly stopped.
    # PROFILE may be a twin PATH (vehicle_twins/<name>), whose run dir is keyed by
    # the RESOLVED profile name -- so discover the newest dashboard.log rather than
    # assuming /tmp/mcr_run/$PROFILE/.
    LOG="$(ls -1dt /tmp/mcr_run/*/dashboard.log 2>/dev/null | head -1)"
    exec tail -F "${LOG:-/tmp/mcr_run/$PROFILE/dashboard.log}" 2>/dev/null || exec sleep infinity
    ;;
  gui)
    # attach the Gazebo 3D client to the already-running headless server, inside
    # this container (shares gz-transport with the server), rendering to the
    # host X server via the forwarded DISPLAY.
    echo "[mcr] launching Gazebo 3D GUI (DISPLAY=${DISPLAY:-unset}) ..."
    exec tools/view_3d.sh
    ;;
  switch)
    PROFILE="${1:?usage: switch <bluerov2|blueboat|wamv | vehicle_twins/<name>>}"
    echo "[mcr] switching to '$PROFILE' (self-cleaning reboot) ..."
    exec tools/run_demo.sh "$PROFILE" up
    ;;
  status)
    # iterate whatever has actually been booted (legacy profile OR twin)
    for d in /tmp/mcr_run/*/; do
      [ -d "$d" ] || continue
      tools/run_demo.sh "$(basename "$d")" status 2>/dev/null
    done
    ;;
  down)
    # run_demo.sh's teardown kills ANY running stack, so one call suffices;
    # loop anyway so status dirs for every booted vehicle get cleaned.
    for d in /tmp/mcr_run/*/; do
      [ -d "$d" ] || continue
      tools/run_demo.sh "$(basename "$d")" down 2>/dev/null
    done
    ;;
  attack|suite)
    exec python3 tools/run_attack_suite.py "$@"
    ;;
  shell|bash)
    exec bash
    ;;
  *)
    # passthrough: run whatever was asked with the env already sourced
    exec "$VERB" "$@"
    ;;
esac
