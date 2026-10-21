#!/bin/bash
# Lean C2-HIL target: ArduPilot SITL (native physics, NO Gazebo) + mav_bridge.
#
# The C2 attack vector is pure MAVLink -- it does not depend on Gazebo physics
# (that only matters for the GPS/position/acoustic vectors). So for a hardware
# C2 test (an ESP32 rogue MAVLink node, see hardware/esp32_mavlink_node/) this
# boots a real, armable SITL target with the profile's defaults and the fan-out
# bridge, skipping the heavyweight Gazebo world for speed and robustness.
#
# For the FULL physics stack (GPS spoof, acoustic, etc.) use tools/run_sim.sh
# instead -- this script is deliberately the minimal MAVLink-only target.
#
# Usage:
#   hardware/c2_hil/boot_c2_target.sh                 # defaults: interceptor_usv @ kochi
#   MCR_VEHICLE_PROFILE=maya_auv MCR_SITE=mumbai hardware/c2_hil/boot_c2_target.sh
#   hardware/c2_hil/boot_c2_target.sh down            # tear down
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ACTION="${1:-up}"
export MCR_SITE="${MCR_SITE:-kochi}"
export MCR_VEHICLE_PROFILE="${MCR_VEHICLE_PROFILE:-interceptor_usv}"
RUN="${MCR_HIL_RUN:-/tmp/mcr_c2_hil/$MCR_VEHICLE_PROFILE}"
LOG="$RUN/logs"; WD="$RUN/sitl_wd"; FIFO="$RUN/sitl_stdin.fifo"

do_down() {
  for n in sitl bridge keepalive; do
    p=$(cat "$RUN/$n.pid" 2>/dev/null); [[ -n "${p:-}" ]] && kill -9 "$p" 2>/dev/null
  done
  pkill -9 -f "tools/mav_bridge.py" 2>/dev/null
  rm -f "$FIFO"
  echo "[c2-hil] down."
}
[[ "$ACTION" == "down" ]] && { do_down; exit 0; }

mkdir -p "$LOG" "$WD"

# --- read profile fields via constants.py (single source of truth) -----------
mapfile -t PF < <(python3 - "$REPO" <<'PY'
import sys, os, json
sys.path.insert(0, sys.argv[1])
import constants
print(constants.ARDUPILOT_VEHICLE_TYPE)   # Rover | Sub
print(constants.HOME_LAT)
print(constants.HOME_LON)
prof = json.load(open(os.path.join(sys.argv[1], "profiles", constants.PROFILE_NAME + ".json")))
print(prof.get("ardu_defaults", ""))
PY
) || { echo "[c2-hil] FATAL: cannot load profile '$MCR_VEHICLE_PROFILE'"; exit 1; }
VTYPE="${PF[0]}"; HLAT="${PF[1]}"; HLON="${PF[2]}"; ADEF="${PF[3]:-}"

if [[ "$VTYPE" == "Sub" ]]; then
  SITL="$HOME/ardupilot/build/sitl/bin/ardusub";  MODEL="vectored_6dof"
else
  SITL="$HOME/ardupilot/build/sitl/bin/ardurover"; MODEL="rover"
fi
[[ -x "$SITL" ]] || { echo "[c2-hil] FATAL: SITL binary not found: $SITL"; exit 1; }
DEFARG=""; [[ -n "$ADEF" ]] && DEFARG="--defaults '$REPO/$ADEF'"

echo "[c2-hil] profile=$MCR_VEHICLE_PROFILE site=$MCR_SITE vehicle=$VTYPE home=$HLAT,$HLON"
# SITL exits on stdin EOF -> feed from a FIFO held open by a keepalive writer.
rm -f "$FIFO"; mkfifo "$FIFO"
setsid bash -c "exec 9>'$FIFO'; sleep infinity" >/dev/null 2>&1 < /dev/null & echo $! > "$RUN/keepalive.pid"
setsid bash -c "cd '$WD'; '$SITL' --model $MODEL --speedup 1 -I0 --home $HLAT,$HLON,0,0 $DEFARG < '$FIFO'" >"$LOG/sitl.log" 2>&1 &
echo $! > "$RUN/sitl.pid"
for _ in $(seq 40); do ss -tln 2>/dev/null | grep -q ":5760 " && break; sleep 1; done
ss -tln 2>/dev/null | grep -q ":5760 " || { echo "[c2-hil] FAIL: SITL never bound tcp:5760"; tail -20 "$LOG/sitl.log"; exit 1; }
echo "[c2-hil]   SITL tcp:5760 [OK]"

setsid bash -c "cd '$REPO'; MCR_SITE='$MCR_SITE' MCR_VEHICLE_PROFILE='$MCR_VEHICLE_PROFILE' python3 -u tools/mav_bridge.py" >"$LOG/bridge.log" 2>&1 &
echo $! > "$RUN/bridge.pid"
python3 - "$REPO" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
import constants
from pymavlink import mavutil
c = mavutil.mavlink_connection(f"udpin:127.0.0.1:{constants.MAVLINK_DASHBOARD_PORT}")
hb = c.wait_heartbeat(timeout=30)
sys.exit(0 if (hb is not None and c.target_system not in (0,255)) else 1)
PY
[[ $? -eq 0 ]] || { echo "[c2-hil] FAIL: no heartbeat via bridge"; tail -20 "$LOG/bridge.log"; exit 1; }
echo "[c2-hil]   heartbeat via mav_bridge [OK]"
echo "[c2-hil] TARGET UP. Next: hardware/c2_hil/esp32_ingress.py  (run dir: $RUN)"
