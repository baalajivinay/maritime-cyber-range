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
export PYTHONPATH="$REPO:$REPO/application:$REPO/communication:$REPO/attacks:$REPO/application/external/venv-ardupilot/lib/python3.12/site-packages:${PYTHONPATH:-}"
PROFILE="${1:?usage: run_sim.sh <profile> up|down|status}"

ACTION="${2:-up}"

# Scale-up: the stack defaults to the Kochi test site (the old Sydney Regatta
# origin was retired as the default). Exporting it here -- before read_profile
# imports constants.py -- keeps the geometry (constants HOME) and the physics
# (the world-patch block in do_up) in agreement. Override with MCR_SITE=... .
export MCR_SITE="${MCR_SITE:-kochi}"

export MCR_VEHICLE_PROFILE="$PROFILE"
RUN_DIR="${MCR_RUN_DIR:-/tmp/mcr_run/$PROFILE}"
mkdir -p "$RUN_DIR"
LOG_DIR="$RUN_DIR/logs"; mkdir -p "$LOG_DIR"
FIFO="$RUN_DIR/relay.fifo"

# --- read profile fields via constants.py (single source of truth) -----------
read_profile() {
  python3 - "$REPO" <<'PY'
import sys, os, json
sys.path.insert(0, sys.argv[1])
import constants
print(constants.DOMAIN)
print(constants.ARDUPILOT_VEHICLE_TYPE)
print(constants.HOME_LAT)
print(constants.HOME_LON)
print(constants.FDM_RELAY_BIND[1])
print(constants.MAVLINK_DASHBOARD_PORT)
# world config makes each profile self-describing about HOW it boots
p_path = os.path.join(sys.argv[1], "application", "profiles", constants.PROFILE_NAME + ".json")
if not os.path.exists(p_path):
    p_path = os.path.join(sys.argv[1], "profiles", constants.PROFILE_NAME + ".json")
prof = json.load(open(p_path))
w = prof.get("world", {})
print(w.get("method", "vrx" if constants.DOMAIN == "surface" else "gz"))
print(w.get("model_name", constants.PROFILE_NAME))
print(w.get("sdf", ""))
print(w.get("world", ""))
print(w.get("urdf", ""))
# optional per-vehicle ArduPilot SITL defaults (.parm) -- e.g. a hardened
# SYSID_MYGCS -- overrides the domain's usual default when set. Path is
# relative to the repo root, so a self-contained vehicle folder can ship
# its own alongside its model.sdf.
print(prof.get("ardu_defaults", ""))
PY
}
mapfile -t PF < <(read_profile) || { echo "FATAL: cannot load profile '$PROFILE'"; exit 1; }
DOMAIN="${PF[0]}"; VTYPE="${PF[1]}"; HOME_LAT="${PF[2]}"; HOME_LON="${PF[3]}"
RELAY_PORT="${PF[4]}"; HB_PORT="${PF[5]}"
WORLD_METHOD="${PF[6]}"; MODEL_NAME="${PF[7]}"; WORLD_SDF="${PF[8]}"; WORLD_NAME="${PF[9]}"; WORLD_URDF="${PF[10]}"
PROFILE_ARDU_DEFAULTS="${PF[11]:-}"

# --- Gazebo environment ------------------------------------------------------
EXT="$REPO/external"
GZ_PLUGIN="$EXT/ardupilot_gazebo/build"
[[ -d "$GZ_PLUGIN" ]] || GZ_PLUGIN="$HOME/ardupilot_gazebo/build"
export GZ_SIM_SYSTEM_PLUGIN_PATH="$GZ_PLUGIN:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"

GZ_MODELS="$REPO/sim_config/models:$EXT/ardupilot_gazebo/models:$EXT/SITL_Models/Gazebo/models:$EXT/SITL_Models/Gazebo/worlds"
[[ -d "$EXT/ardupilot_gazebo/models" ]] || GZ_MODELS="$REPO/sim_config/models:$HOME/ardupilot_gazebo/models:$HOME/SITL_Models/Gazebo/models:$HOME/SITL_Models/Gazebo/worlds"
export GZ_SIM_RESOURCE_PATH="$GZ_MODELS:${GZ_SIM_RESOURCE_PATH:-}"

ARDU_PARAMS=""
if [[ "$VTYPE" == "Sub" ]]; then
  SITL_BIN="$EXT/ardupilot/build/sitl/bin/ardusub"
  [[ -x "$SITL_BIN" ]] || SITL_BIN="$HOME/ardupilot/build/sitl/bin/ardusub"
  ARDU_PARAMS="$EXT/auv_ws/src/dave/models/dave_robot_models/config/bluerov2/ardusub.parm"
  [[ -f "$ARDU_PARAMS" ]] || ARDU_PARAMS="$HOME/auv_ws/src/dave/models/dave_robot_models/config/bluerov2/ardusub.parm"
else
  SITL_BIN="$EXT/ardupilot/build/sitl/bin/ardurover"
  [[ -x "$SITL_BIN" ]] || SITL_BIN="$HOME/ardupilot/build/sitl/bin/ardurover"
fi
# A profile's own "ardu_defaults" (e.g. a hardened SYSID_MYGCS for a
# resilient digital twin) overrides the domain's usual default entirely --
# SITL only accepts one --defaults file, so a vehicle that needs BOTH the
# Sub-domain buoyancy/EKF params AND its own security hardening must ship
# a defaults file that includes both (see vehicle_twins/*/ardusub.parm).
if [[ -n "$PROFILE_ARDU_DEFAULTS" ]]; then
  ARDU_PARAMS="$REPO/$PROFILE_ARDU_DEFAULTS"
fi

log()  { echo "[run_sim:$PROFILE] $*"; }
fail() { echo "[run_sim:$PROFILE] FAIL: $*" >&2; exit 1; }

spawn() { # spawn <logfile> <cmd...>  -> detached, PID echoed
  local lf="$1"; shift
  # stdbuf -oL -eL: force line-buffered output. Without it, output redirected
  # to a file (not a TTY) is fully block-buffered, so a process that crashes
  # early (e.g. gz sim failing to resolve a model:// URI) can exit with its
  # diagnostic lines still sitting in the buffer -- the log is left empty and
  # a real, fast failure looks identical to "still starting up" to anything
  # tailing it (observed live: gz sim's "Unable to find uri[model://cusv]"
  # error was completely invisible in world.log until this fix).
  setsid stdbuf -oL -eL bash -c "$*" >"$lf" 2>&1 < /dev/null &
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
  if [[ "$WORLD_METHOD" == "vrx" ]]; then
    # VRX's competition.launch.py spawns grandchildren that DON'T die with the
    # launch process -- leaving them (and a stale gz server serving /wamv
    # topics) behind poisons the next boot. Kill them explicitly.
    pkill -9 -f "competition.launch" 2>/dev/null
    pkill -9 -f "start_vrx.sh" 2>/dev/null
    pkill -9 -f "parameter_bridge" 2>/dev/null
    pkill -9 -f "pose_tf_broadcaster" 2>/dev/null
    pkill -9 -f "robot_state_publisher" 2>/dev/null
  elif [[ -n "$WORLD_SDF" ]]; then
    pkill -9 -f "$(basename "$WORLD_SDF")" 2>/dev/null
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

  # Scale-up (default OFF): if MCR_SITE names an Indian test site, patch the
  # world buoyancy <default_density> to that water body's EOS-80 density, so
  # buoyant force uses the real site density. Guarded -- unset MCR_SITE leaves
  # the shipped behaviour byte-identical.
  WORLD_LAUNCH="$REPO/$WORLD_SDF"
  if [[ -n "${MCR_SITE:-}" && -n "$WORLD_SDF" && "$WORLD_METHOD" != "vrx" ]]; then
    local senv sden slat slon
    senv=$(python3 -c "import sys;sys.path.insert(0,'$REPO');from scaleup.sites import load_site;s=load_site('$MCR_SITE');print(round(s.density(),1), s.position[0], s.position[1])" 2>/dev/null)
    if [[ -n "$senv" ]]; then
      read -r sden slat slon <<< "$senv"
      HOME_LAT="$slat"; HOME_LON="$slon"
      # relocate the Gazebo GPS origin to the site AND set the water density.
      # (SITL --home already follows, via constants.HOME_LAT/LON override.)
      WORLD_LAUNCH="$RUN_DIR/world_site.sdf"
      sed -e "s|<default_density>[0-9.]*</default_density>|<default_density>$sden</default_density>|" \
          -e "s|<latitude_deg>[-0-9.]*</latitude_deg>|<latitude_deg>$slat</latitude_deg>|" \
          -e "s|<longitude_deg>[-0-9.]*</longitude_deg>|<longitude_deg>$slon</longitude_deg>|" \
          "$REPO/$WORLD_SDF" > "$WORLD_LAUNCH"
      log "site '$MCR_SITE': relocate to $slat,$slon; buoyancy density -> $sden kg/m^3"
    fi
  fi

  # 1) Gazebo world -- boot method comes from the profile's "world" config, so a
  #    new vehicle just declares how it boots (VRX launch, or a plain gz world).
  if [[ "$WORLD_METHOD" == "vrx" ]]; then
    log "starting VRX world '$WORLD_NAME'..."
    spawn "$LOG_DIR/world.log" "source /opt/ros/jazzy/setup.bash; source '$REPO/ros2_ws/install/setup.bash'; ros2 launch vrx_gz competition.launch.py world:=$WORLD_NAME headless:=True urdf:='$REPO/$WORLD_URDF'" > "$RUN_DIR/world.pid"
  else
    log "starting gz world '$WORLD_SDF' (density source: $(basename "$WORLD_LAUNCH"))..."
    spawn "$LOG_DIR/world.log" "gz sim -v4 -s -r '$WORLD_LAUNCH'" > "$RUN_DIR/world.pid"
  fi
  # 100s, not 60: gz-transport's pub/sub discovery (what `gz topic -l` reads)
  # can take noticeably longer to register a freshly-started world's topics
  # right after a PREVIOUS world was torn down with SIGKILL (no graceful
  # deregistration, so peers' discovery caches take a beat to catch up) --
  # observed live, back-to-back Gazebo twin boots (e.g. interceptor_usv then
  # survey_usv) intermittently needed more than 60s even though the world
  # process itself was healthy and well under 60s on a cold start.
  wait_gz_model "$MODEL_NAME" 100 || fail "Gazebo model '$MODEL_NAME' never appeared (world didn't boot)"
  log "  world up, model '$MODEL_NAME' present [OK]"

  # The VRX world can't <include> our ground-station model, so spawn it at
  # runtime (the gz worlds include it directly). It's the shore GCS landmark.
  if [[ "$WORLD_METHOD" == "vrx" ]]; then
    local gs; gs=$(tr '\n' ' ' < "$REPO/sim_config/models/ground_station/model.sdf" | sed 's/"/\\"/g')
    gz service -s "/world/$WORLD_NAME/create" --reqtype gz.msgs.EntityFactory \
      --reptype gz.msgs.Boolean --timeout 6000 \
      --req "sdf: \"$gs\" name: \"ground_station\" pose: {position: {x: -470 y: 250 z: 0}}" >/dev/null 2>&1 \
      && log "  ground station spawned [OK]"
  fi

  # 2) FDM relay (passthrough) with FIFO-fed stdin
  rm -f "$FIFO"; mkfifo "$FIFO"
  setsid bash -c "exec 9>'$FIFO'; sleep infinity" >/dev/null 2>&1 < /dev/null &
  echo $! > "$RUN_DIR/fifo_keepalive.pid"
  spawn "$LOG_DIR/relay.log" "cd '$REPO'; MCR_VEHICLE_PROFILE='$PROFILE' MCR_GPS_LOG_PATH='$RUN_DIR/gps_spoof_ground_truth.csv' python3 -u attacks/gps_spoof.py < '$FIFO'" > "$RUN_DIR/relay.pid"
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
  spawn "$LOG_DIR/bridge.log" "cd '$REPO'; MCR_VEHICLE_PROFILE='$PROFILE' python3 -u communication/mav_bridge.py" > "$RUN_DIR/bridge.pid"
  wait_heartbeat "$HB_PORT" 30 || fail "no MAVLink heartbeat on :$HB_PORT (bridge/SITL link)"

  log "  heartbeat on :$HB_PORT [OK]"

  # 5) AIS emulator (DISABLED)
  # if [[ "$DOMAIN" == "surface" ]]; then
  #   log "starting AIS emulator..."
  #   spawn "$LOG_DIR/ais.log" "cd '$REPO'; MCR_VEHICLE_PROFILE='$PROFILE' python3 -u nodes/ais_emulator/ais_emulator.py" > "$RUN_DIR/ais.pid"
  #   sleep 2
  #   log "  AIS emulator started (broadcasting on UDP 10110)"
  # fi

  # 6) Integrated 3D view (default OFF -> headless boot byte-unchanged). With
  #    MCR_VIEW=1 and a display, launch the Gazebo GUI attached to the running
  #    server and make its camera FOLLOW the vehicle (a chase / first-person
  #    view over the real water world) -- the product's OWN display, no browser.
  if [[ "${MCR_VIEW:-0}" == "1" ]]; then
    if [[ -z "${DISPLAY:-}" ]]; then
      log "MCR_VIEW=1 but \$DISPLAY is unset -- skipping 3D view (needs an X display)."
    else
      log "launching integrated 3D view (follow-cam on '$MODEL_NAME')..."
      spawn "$LOG_DIR/gui.log" "gz sim -g" > "$RUN_DIR/gui.pid"
      # The GUI takes a few seconds to connect to the server scene; then ask its
      # camera to follow the vehicle and sit just behind+above it (chase/FPV).
      ( for _ in $(seq 25); do
          gz service -s /gui/follow --reqtype gz.msgs.StringMsg --reptype gz.msgs.Boolean \
            --timeout 1000 --req "data: \"$MODEL_NAME\"" >/dev/null 2>&1 && break
          sleep 1
        done
        gz service -s /gui/follow/offset --reqtype gz.msgs.Vector3d --reptype gz.msgs.Boolean \
          --timeout 2000 --req "x: -3.0 y: 0.0 z: 1.2" >/dev/null 2>&1 ) &
      log "  3D view up: the window follows '$MODEL_NAME'. Scroll to zoom, drag to look around;"
      log "  right-click the vehicle -> Follow/Track to re-lock, or close the window to stop viewing."
    fi
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
