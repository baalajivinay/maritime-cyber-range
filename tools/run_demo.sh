#!/bin/bash
# One command to bring up the whole demo: the simulator stack AND the live
# dashboard, together. Wraps tools/run_sim.sh and adds the ROS2-sourced
# dashboard so a presenter runs a single command and opens one URL.
#
#   tools/run_demo.sh <profile> up      # boot sim + dashboard  (default)
#   tools/run_demo.sh <profile> down    # tear both down
#   tools/run_demo.sh <profile> status
#
# <profile> = a profiles/<name>.json name, OR (more usually) a path to a
# self-contained vehicle_twins/<name>/ folder -- see tools/run_vehicle.sh's
# header for that mechanism. The dashboard's true-position map feed is
# richest for the VRX WAM-V (ROS GPS); other vehicles still show believed
# position, AIS, alerts, and telemetry.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE_ARG="${1:?usage: run_demo.sh <profile-name-or-vehicle_twins-folder> up|down|status}"
ACTION="${2:-up}"

# Accept either a plain profile name (wamv | blueboat | bluerov2, ...) or a
# path to a self-contained vehicle_twins/<name>/ folder -- same trick as
# tools/run_vehicle.sh: symlink that folder's profile.json into profiles/
# so the rest of this script (and run_sim.sh underneath it) just sees an
# ordinary profile name, unchanged.
if [[ -f "$PROFILE_ARG/profile.json" ]]; then
  PROFILE="$(python3 -c "import json; print(json.load(open('$PROFILE_ARG/profile.json'))['name'])")"
  ln -sf "$(cd "$PROFILE_ARG" && pwd)/profile.json" "$REPO/profiles/$PROFILE.json"
  echo "[run_demo] $PROFILE_ARG -> profile '$PROFILE'"
else
  PROFILE="$PROFILE_ARG"
fi
RUN_DIR="${MCR_RUN_DIR:-/tmp/mcr_run/$PROFILE}"; mkdir -p "$RUN_DIR"

log(){ echo "[run_demo:$PROFILE] $*"; }

# Kill ANY running demo (any profile) + free its ports, so `up` can switch
# vehicles cleanly in one command. Never matches run_demo.sh/run_sim.sh
# themselves, so the launcher survives.
killall_demo(){
  pkill -9 -f "dashboard_server.py" 2>/dev/null
  for pat in "gz sim" "ardurover" "ardusub" "mav_bridge.py" "gps_spoof.py" \
             "ais_emulator.py" "acoustic_spoof.py" "competition.launch" \
             "parameter_bridge" "pose_tf_broadcaster" "robot_state_publisher" \
             "sitl_stdin.fifo" "relay.fifo"; do
    pkill -9 -f "$pat" 2>/dev/null
  done
  fuser -k 9002/udp 8080/tcp 5760/tcp 2>/dev/null
  # wait for the shared ports to free (up to ~10s)
  for _ in $(seq 10); do
    ss -tuln 2>/dev/null | grep -qE ":9002 |:8080 |:5760 " || break
    sleep 1
  done
}

start_dashboard(){
  log "starting dashboard (http://localhost:8080) ..."
  # dashboard needs rclpy -> ROS2 env sourced; profile selects ports/identity
  setsid bash -c "
    source /opt/ros/jazzy/setup.bash 2>/dev/null
    source '$REPO/ros2_ws/install/setup.bash' 2>/dev/null
    export MCR_VEHICLE_PROFILE='$PROFILE'
    cd '$REPO'
    exec python3 -u nodes/monitor/src/dashboard_server.py
  " >"$RUN_DIR/dashboard.log" 2>&1 < /dev/null &
  echo $! > "$RUN_DIR/dashboard.pid"
  for _ in $(seq 25); do
    curl -s -o /dev/null http://localhost:8080/ 2>/dev/null && { log "  dashboard up [OK]"; return 0; }
    sleep 1
  done
  log "  dashboard did NOT come up -- see $RUN_DIR/dashboard.log"; return 1
}

case "$ACTION" in
  up)
    log "clearing any running demo (so switching vehicles is one command) ..."
    killall_demo
    "$REPO/tools/run_sim.sh" "$PROFILE" up || { log "sim boot failed"; exit 1; }
    start_dashboard
    log "DEMO UP.  Open  ->  http://localhost:8080"
    log "Fire attacks with tools/run_attack_suite.py --profile $PROFILE, or the relay FIFO $RUN_DIR/relay.fifo"
    # Best-effort: open the dashboard automatically so the terminal command
    # alone is enough. Silently does nothing if there's no desktop/browser
    # available (e.g. a headless SSH session) -- the URL above still works
    # if you open it yourself.
    (xdg-open http://localhost:8080 >/dev/null 2>&1 &) || true
    ;;
  down)
    pkill -9 -f "dashboard_server.py" 2>/dev/null
    "$REPO/tools/run_sim.sh" "$PROFILE" down
    log "demo down."
    ;;
  status)
    "$REPO/tools/run_sim.sh" "$PROFILE" status
    curl -s -o /dev/null -w "[run_demo:$PROFILE] dashboard http %{http_code}\n" http://localhost:8080/ 2>/dev/null
    ;;
  *) echo "unknown action '$ACTION'"; exit 2 ;;
esac
