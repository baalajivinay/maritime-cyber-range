#!/bin/bash
# Full Stonefish-backed AUV cyber-range stack:
#   Stonefish (physics + render on the RTX)  <--JSON FDM-->  ArduSub SITL  <--MAVLink 5760-->  mav_bridge fan-out
# Then attacks / tools/test_target.py / the Godot app can drive it exactly like the Gazebo stack.
#
#   tools/stonefish_bridge.sh up    (boot)   |   down (teardown)
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCR="${MCR_BIN:-$HOME/stonefish_src/build/Tests/MCR}"
ARDUSUB="${ARDUSUB_BIN:-$HOME/ardupilot/build/sitl/bin/ardusub}"
SCN="${MCR_SCN:-$REPO/stonefish/auv150.scn}"
SITE_LAT="${MCR_LAT:-9.9}"; SITE_LON="${MCR_LON:-76.2}"
RUN=/tmp/mcr_stonefish; mkdir -p "$RUN"; FIFO="$RUN/sub_stdin.fifo"
ACTION="${1:-up}"

do_down() {
  pkill -x MCR 2>/dev/null; pkill -x ardusub 2>/dev/null
  pkill -9 -f "tools/mav_bridg[e].py" 2>/dev/null
  pkill -9 -f "stonefish_extna[v].py" 2>/dev/null
  rm -f "$FIFO"; echo "[stonefish] down."
}
[[ "$ACTION" == "down" ]] && { do_down; exit 0; }
[[ -x "$MCR" && -x "$ARDUSUB" ]] || { echo "[stonefish] MCR or ardusub binary missing"; exit 1; }

# MCR_HEADLESS=1 runs Stonefish as pure physics (no window) so Godot can be the
# single renderer (the integrated app.sh path). Otherwise Stonefish opens its own
# high-fidelity render window on the RTX (needs a display).
# stdbuf -oL -eL: force line-buffered stdout/stderr. Without it, output
# redirected to a file (not a TTY) is fully block-buffered, so if MCR exits or
# crashes early (e.g. a port bind failure) its diagnostic lines never flush and
# mcr.log is left empty -- a real failure then looks indistinguishable from
# "still starting up" to anything tailing the log.
if [[ "${MCR_HEADLESS:-0}" == "1" ]]; then
  echo "[stonefish] 1) Stonefish physics (headless), FDM on :9002 ..."
  setsid stdbuf -oL -eL "$MCR" "$SCN" --fdm 9002 --headless >"$RUN/mcr.log" 2>&1 &
else
  [[ -n "${DISPLAY:-}" ]] || { echo "[stonefish] no \$DISPLAY (Stonefish render needs a display; or set MCR_HEADLESS=1)"; exit 1; }
  echo "[stonefish] 1) Stonefish physics+render (RTX), FDM on :9002 ..."
  __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia setsid stdbuf -oL -eL "$MCR" "$SCN" --fdm 9002 >"$RUN/mcr.log" 2>&1 &
fi
sleep 6
echo "[stonefish] 2) ArduSub SITL on the JSON FDM (home $SITE_LAT,$SITE_LON, ExternalNav) ..."
PARM="$REPO/stonefish/auv150_ardusub.parm"
rm -f "$FIFO"; mkfifo "$FIFO"; setsid bash -c "exec 9>'$FIFO'; sleep infinity" >/dev/null 2>&1 &
setsid bash -c "cd '$RUN'; '$ARDUSUB' --model JSON:127.0.0.1 --speedup 1 -I0 --home $SITE_LAT,$SITE_LON,0,0 --defaults '$PARM' < '$FIFO'" >"$RUN/sub.log" 2>&1 &
sleep 3
echo "[stonefish] 3) mav_bridge (GCS on 5760 -> fan-out 14551+) ..."
setsid bash -c "cd '$REPO'; MCR_VEHICLE_PROFILE=auv150 python3 -u tools/mav_bridge.py" >"$RUN/bridge.log" 2>&1 &
sleep 4
echo "[stonefish] 4) ExternalNav/USBL feed (acoustic positioning; spoof toggle on :10120) ..."
setsid bash -c "cd '$REPO'; python3 -u tools/stonefish_extnav.py tcp:127.0.0.1:5762" >"$RUN/extnav.log" 2>&1 &
sleep 3
echo "[stonefish] STACK UP. ArduSub flies on Stonefish physics with USBL ExternalNav."
echo "  acoustic spoof ON:  echo step | nc -u -w1 127.0.0.1 10120   (OFF: echo off | ...)"
echo "  watch believed pos: python3 tools/test_target.py --target vehicle_twins/auv150/target.json --attacks acoustic_spoof"
echo "  teardown:           tools/stonefish_bridge.sh down"
