#!/bin/bash
# Maritime Cyber Range — operator console launcher.
#
#   tools/app.sh              Godot 4 game-quality renderer (DEFAULT), with ALL
#                             the physics integrated: each vehicle runs on its
#                             best engine automatically -- the tuned Stonefish
#                             6-DOF hydrodynamics for the AUV-150 (headless, so
#                             Godot stays the only window) and the Gazebo +
#                             real-data models (site sea-state/acoustics/sensors/
#                             tides/bathymetry) for the USVs and other twins.
#                             One window: pick a site + vehicle, watch it move,
#                             set a destination, launch attacks.
#
#   tools/app.sh stonefish    Force the Stonefish engine for everything.
#   tools/app.sh gazebo       Force the Gazebo engine for everything.
#   tools/app.sh pygame       The legacy pygame renderer (fallback, no GPU shaders).
#
# Needs a display ($DISPLAY). The Godot modes need the Godot 4 binary
# (see tools/godot_app.sh / $GODOT). Authorized lab/range use only.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-godot}"

if [[ -z "${DISPLAY:-}" ]]; then
  echo "[app] no \$DISPLAY -- the application needs a graphical display." >&2
  exit 1
fi

case "$MODE" in
  godot|unified|"")
    echo "[app] launching Godot with ALL physics integrated -- each vehicle on its"
    echo "[app] best engine (Stonefish hydro for the AUV-150, Gazebo + real-data"
    echo "[app] models for the rest). One window; the legacy app is: tools/app.sh pygame"
    exec bash "$REPO/tools/godot_app.sh"            # relay defaults to the unified router
    ;;
  stonefish)
    echo "[app] launching Godot, forcing the Stonefish engine for all vehicles."
    exec bash "$REPO/tools/godot_app.sh" stonefish
    ;;
  gazebo)
    echo "[app] launching Godot, forcing the Gazebo engine for all vehicles."
    exec bash "$REPO/tools/godot_app.sh" gazebo
    ;;
  pygame|legacy)
    echo "[app] launching the legacy pygame renderer."
    exec python3 "$REPO/nodes/app/mcr_app.py" "${@:2}"
    ;;
  *)
    echo "[app] unknown mode '$MODE'. Use: (default) | stonefish | gazebo | pygame" >&2
    exit 2
    ;;
esac
