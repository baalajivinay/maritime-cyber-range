#!/bin/bash
# Run the simulation WITH the product's own integrated 3D view -- the specified
# vehicle running over the real water physics, in a chase / first-person follow
# camera. This is the Gazebo GUI attached to the sim, NOT the browser dashboard.
#
# Usage:
#   tools/view.sh vehicle_twins/<twin>            # boot the twin + open the 3D view
#   MCR_SITE=mumbai tools/view.sh vehicle_twins/<twin>
#   tools/view.sh attach [<model_name>]           # attach a view to an ALREADY-running sim
#   tools/view.sh vehicle_twins/<twin> down       # tear down
#
# Needs an X display ($DISPLAY). The view follows the vehicle; scroll to zoom,
# drag to look around, or right-click the hull -> Follow/Track to re-lock.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${DISPLAY:-}" ]]; then
  echo "[view] no \$DISPLAY set -- the 3D view needs a graphical display." >&2
  exit 1
fi

# attach mode: add the follow-cam GUI to a sim that is already up
if [[ "${1:-}" == "attach" ]]; then
  MODEL="${2:-}"
  if [[ -z "$MODEL" ]]; then
    # best-effort: first model that is publishing odometry
    MODEL=$(gz topic -l 2>/dev/null | sed -n 's#^/model/\([^/]*\)/odometry$#\1#p' | head -1)
  fi
  [[ -z "$MODEL" ]] && { echo "[view] could not find a running model; pass one: tools/view.sh attach <model>"; exit 1; }
  echo "[view] attaching 3D view, following '$MODEL' ..."
  gz sim -g >/tmp/mcr_view_gui.log 2>&1 &
  for _ in $(seq 25); do
    gz service -s /gui/follow --reqtype gz.msgs.StringMsg --reptype gz.msgs.Boolean \
      --timeout 1000 --req "data: \"$MODEL\"" >/dev/null 2>&1 && break
    sleep 1
  done
  gz service -s /gui/follow/offset --reqtype gz.msgs.Vector3d --reptype gz.msgs.Boolean \
    --timeout 2000 --req "x: -3.0 y: 0.0 z: 1.2" >/dev/null 2>&1
  echo "[view] 3D view up (follow '$MODEL')."
  exit 0
fi

# boot-with-view: hand off to run_vehicle.sh with the view enabled
FOLDER="${1:?usage: tools/view.sh vehicle_twins/<twin> [up|down]}"
ACTION="${2:-up}"
export MCR_VIEW=1
exec "$REPO/tools/run_vehicle.sh" "$FOLDER" "$ACTION"
