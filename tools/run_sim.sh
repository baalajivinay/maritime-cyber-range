#!/bin/bash
# WO-14: one-command, profile-parameterized full-stack boot with REAL health
# checks (port-bound / topic-publishing / heartbeat confirmation), replacing
# this project's earlier manual "sleep and hope" bring-up.
#
# Usage:
#   tools/run_sim.sh <profile> up       # boot the stack for that profile's domain
#   tools/run_sim.sh <profile> down     # tear the stack down
#   tools/run_sim.sh <profile> status   # health-check a running stack
#
#   <profile> is a name under profiles/ (e.g. wamv | bluerov2). The profile's
#   "domain" (surface|underwater) selects the world + SITL vehicle automatically.
#
# Boots, in order, with a health gate after each: Gazebo world -> FDM relay
# (attacks/gps_spoof.py in passthrough, on :9002) -> ArduPilot SITL (ardurover
# or ardusub, direct binary, no MAVProxy tty) -> MAVLink fan-out bridge
# (tools/mav_bridge.py) -> AIS emulator (surface only).
#
# Long-running children are started with setsid so they survive this script's
# exit; `down` kills them by recorded pattern. See docs/ARCHITECTURE.md.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="${1:?usage: run_sim.sh <profile> up|down|status}"
ACTION="${2:-up}"

export MCR_VEHICLE_PROFILE="$PROFILE"
RUN_DIR="${MCR_RUN_DIR:-/tmp/mcr_run/$PROFILE}"
mkdir -p "$RUN_DIR"
LOG_DIR="$RUN_DIR/logs"; mkdir -p "$LOG_DIR"
FIFO="$RUN_DIR/relay.fifo"

# --- read profile fields via constants.py (single source of truth) -----------
read_profile() {
  python3 - "$REPO" <<'PY'
import sys, os
sys.path.insert(0, sys.argv[1])
import constants
print(constants.DOMAIN)
print(constants.ARDUPILOT_VEHICLE_TYPE)
print(constants.HOME_LAT)
print(constants.HOME_LON)
print(constants.FDM_RELAY_BIND[1])
print(constants.MAVLINK_DASHBOARD_PORT)
PY
}
mapfile -t PF < <(read_profile) || { echo "FATAL: cannot load profile '$PROFILE'"; exit 1; }
DOMAIN="${PF[0]}"; VTYPE="${PF[1]}"; HOME_LAT="${PF[2]}"; HOME_LON="${PF[3]}"
RELAY_PORT="${PF[4]}"; HB_PORT="${PF[5]}"

# --- Gazebo environment ------------------------------------------------------
export GZ_SIM_SYSTEM_PLUGIN_PATH="$HOME/ardupilot_gazebo/build:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"
export GZ_SIM_RESOURCE_PATH="$REPO/sim_config/models:$HOME/ardupilot_gazebo/models:$HOME/SITL_Models/Gazebo/models:$HOME/SITL_Models/Gazebo/worlds:${GZ_SIM_RESOURCE_PATH:-}"

ARDU_PARAMS=""
if [[ "$DOMAIN" == "underwater" ]]; then
  MODEL_NAME="bluerov2"
  WORLD_TOPIC="/world/underwater_harbor/dynamic_pose/info"
  SITL_BIN="$HOME/ardupilot/build/sitl/bin/ardusub"
  ARDU_PARAMS="$HOME/auv_ws/src/dave/models/dave_robot_models/config/bluerov2/ardusub.parm"
else
  MODEL_NAME="wamv"
  WORLD_TOPIC="/world/sydney_regatta/dynamic_pose/info"
  SITL_BIN="$HOME/ardupilot/build/sitl/bin/ardurover"
fi

log()  { echo "[run_sim:$PROFILE] $*"; }
fail() { echo "[run_sim:$PROFILE] FAIL: $*" >&2; exit 1; }

spawn() { # spawn <logfile> <cmd...>  -> detached, PID echoed
  local lf="$1"; shift
  setsid bash -c "$*" >"$lf" 2>&1 < /dev/null &
  echo $!
}

# --- health-check primitives -------------------------------------------------
wait_udp_port() { # wait until a UDP port is bound (relay on :9002)
  local port="$1" tries="${2:-30}"
  for _ in $(seq "$tries"); do
    ss -uln 2>/dev/null | grep -q ":$port " && return 0
    sleep 1
  done
  return 1
}
wait_tcp_port() {
  local port="$1" tries="${2:-40}"
  for _ in $(seq "$tries"); do
    ss -tln 2>/dev/null | grep -q ":$port " && return 0
    sleep 1
  done
  return 1
}
wait_gz_model() { # wait until the vehicle model's topics exist in Gazebo
  local model="$1" tries="${2:-40}"
  for _ in $(seq "$tries"); do
    gz topic -l 2>/dev/null | grep -q "/model/$model/" && return 0
    sleep 1
  done
  return 1
}
wait_heartbeat() { # wait for a MAVLink heartbeat on a UDP port
  local port="$1" timeout="${2:-30}"
  python3 - "$port" "$timeout" <<'PY'
import sys
from pymavlink import mavutil
port, to = int(sys.argv[1]), float(sys.argv[2])
c = mavutil.mavlink_connection(f"udpin:127.0.0.1:{port}")
hb = c.wait_heartbeat(timeout=to)
sys.exit(0 if (hb is not None and c.target_system not in (0, 255)) else 1)
PY
}

# --- teardown ----------------------------------------------------------------
do_down() {
  log "tearing down..."
  for pat in "mav_bridge.py" "gps_spoof.py" "$SITL_BIN" "ais_emulator.py"; do
    pkill -9 -f "$pat" 2>/dev/null
  done
  if [[ "$DOMAIN" == "underwater" ]]; then
    pkill -9 -f "underwater_world.sdf" 2>/dev/null
  else
    pkill -9 -f "competition.launch" 2>/dev/null
    pkill -9 -f "start_vrx.sh" 2>/dev/null
  fi
  pkill -9 -f "gz sim" 2>/dev/null
  pkill -9 -f "$FIFO" 2>/dev/null
  pkill -9 -f "$RUN_DIR/sitl_stdin.fifo" 2>/dev/null
  rm -f "$FIFO" "$RUN_DIR/sitl_stdin.fifo"
  sleep 2
  log "down."
}

do_status() {
  local ok=0
  ss -uln 2>/dev/null | grep -q ":$RELAY_PORT " && log "relay :$RELAY_PORT bound     [OK]"   || { log "relay :$RELAY_PORT           [DOWN]"; ok=1; }
  gz topic -l 2>/dev/null | grep -q "/model/$MODEL_NAME/" && log "gz model $MODEL_NAME       [OK]" || { log "gz model $MODEL_NAME       [DOWN]"; ok=1; }
  ss -tln 2>/dev/null | grep -q ":5760 " && log "SITL tcp:5760             [OK]"   || { log "SITL tcp:5760             [DOWN]"; ok=1; }
  wait_heartbeat "$HB_PORT" 6 && log "MAVLink heartbeat :$HB_PORT [OK]" || { log "MAVLink heartbeat :$HB_PORT [DOWN]"; ok=1; }
  return $ok
}

# --- boot --------------------------------------------------------------------
do_up() {
  log "domain=$DOMAIN vehicle=$VTYPE home=$HOME_LAT,$HOME_LON  run_dir=$RUN_DIR"

  # 1) Gazebo world
  if [[ "$DOMAIN" == "underwater" ]]; then
    log "starting underwater world..."
    spawn "$LOG_DIR/world.log" "gz sim -v4 -s -r '$REPO/sim_config/underwater_world.sdf'" > "$RUN_DIR/world.pid"
  else
    log "starting VRX surface world..."
    spawn "$LOG_DIR/world.log" "source /opt/ros/jazzy/setup.bash; source '$REPO/ros2_ws/install/setup.bash'; ros2 launch vrx_gz competition.launch.py world:=sydney_regatta headless:=True urdf:='$REPO/sim_config/wamv_ardupilot.sdf'" > "$RUN_DIR/world.pid"
  fi
  wait_gz_model "$MODEL_NAME" 60 || fail "Gazebo model '$MODEL_NAME' never appeared (world didn't boot)"
  log "  world up, model '$MODEL_NAME' present [OK]"

  # 2) FDM relay (passthrough) with FIFO-fed stdin
  rm -f "$FIFO"; mkfifo "$FIFO"
  setsid bash -c "exec 9>'$FIFO'; sleep infinity" >/dev/null 2>&1 < /dev/null &
  echo $! > "$RUN_DIR/fifo_keepalive.pid"
  spawn "$LOG_DIR/relay.log" "cd '$REPO'; MCR_VEHICLE_PROFILE='$PROFILE' python3 -u attacks/gps_spoof.py < '$FIFO'" > "$RUN_DIR/relay.pid"
  wait_udp_port "$RELAY_PORT" 20 || fail "FDM relay never bound UDP :$RELAY_PORT"
  log "  relay bound :$RELAY_PORT [OK]"

  # 3) ArduPilot SITL (direct binary). Two lessons the hard way:
  #  - Run from a dedicated writable working dir (SITL writes eeprom.bin /
  #    storage into CWD).
  #  - SITL reads stdin as a console and EXITS on stdin EOF. A plain `< /dev/null`
  #    (what nohup/detach defaults to) kills it within seconds. So feed stdin
  #    from a FIFO held open by a keepalive writer -- a never-closing, blocking
  #    stdin -- exactly the trick the FDM relay uses.
  local sitl_wd="$RUN_DIR/sitl_wd"; mkdir -p "$sitl_wd"
  local sitl_fifo="$RUN_DIR/sitl_stdin.fifo"
  rm -f "$sitl_fifo"; mkfifo "$sitl_fifo"
  setsid bash -c "exec 9>'$sitl_fifo'; sleep infinity" >/dev/null 2>&1 < /dev/null &
  echo $! > "$RUN_DIR/sitl_stdin_keepalive.pid"
  local homearg="$HOME_LAT,$HOME_LON,0,0"
  local parmarg=""; [[ -n "$ARDU_PARAMS" ]] && parmarg="--defaults '$ARDU_PARAMS'"
  log "starting SITL ($VTYPE)..."
  setsid bash -c "cd '$sitl_wd'; '$SITL_BIN' --model JSON --speedup 1 --slave 0 --sim-address=127.0.0.1 -I0 --home $homearg $parmarg < '$sitl_fifo'" >"$LOG_DIR/sitl.log" 2>&1 &
  echo $! > "$RUN_DIR/sitl.pid"
  wait_tcp_port 5760 40 || fail "SITL never bound tcp:5760"
  log "  SITL tcp:5760 [OK]"

  # 4) MAVLink fan-out bridge
  log "starting MAVLink bridge..."
  spawn "$LOG_DIR/bridge.log" "cd '$REPO'; MCR_VEHICLE_PROFILE='$PROFILE' python3 -u tools/mav_bridge.py" > "$RUN_DIR/bridge.pid"
  wait_heartbeat "$HB_PORT" 30 || fail "no MAVLink heartbeat on :$HB_PORT (bridge/SITL link)"
  log "  heartbeat on :$HB_PORT [OK]"

  # 5) AIS emulator (surface only -- AIS is N/A submerged)
  if [[ "$DOMAIN" == "surface" ]]; then
    log "starting AIS emulator..."
    spawn "$LOG_DIR/ais.log" "cd '$REPO'; MCR_VEHICLE_PROFILE='$PROFILE' python3 -u nodes/ais_emulator/ais_emulator.py" > "$RUN_DIR/ais.pid"
    sleep 2
    log "  AIS emulator started (broadcasting on UDP 10110)"
  fi

  log "STACK UP. Send spoof commands to the relay via:  echo step > $FIFO"
  log "Teardown:  tools/run_sim.sh $PROFILE down"
}

case "$ACTION" in
  up)     do_up ;;
  down)   do_down ;;
  status) do_status ;;
  *)      echo "unknown action '$ACTION' (up|down|status)"; exit 2 ;;
esac
