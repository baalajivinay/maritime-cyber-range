#!/bin/bash
# One command to bring up the whole demo: the simulator stack AND the live
# dashboard, together. Wraps tools/run_sim.sh and adds the ROS2-sourced
# dashboard so a presenter runs a single command and opens one URL.
#
#   tools/run_demo.sh <profile> up      # boot sim + dashboard  (default)
#   tools/run_demo.sh <profile> down    # tear both down
#   tools/run_demo.sh <profile> status
#
# <profile> = wamv | blueboat | bluerov2. The dashboard's true-position map
# feed is richest for the VRX WAM-V (ROS GPS); other vehicles still show
# believed position, AIS, alerts, and telemetry.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="${1:?usage: run_demo.sh <profile> up|down|status}"
ACTION="${2:-up}"
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
