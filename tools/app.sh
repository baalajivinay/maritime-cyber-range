#!/bin/bash
# Maritime Cyber Range — operator console launcher.
#
#   tools/app.sh              Godot 4 game-quality renderer (DEFAULT).
#                             Physics runs headless underneath (Gazebo), one
#                             window: pick a site + vehicle, watch it move over
#                             real water, set a destination, launch attacks.
#
#   tools/app.sh stonefish    Godot renderer on STONEFISH high-fidelity physics
#                             (the two engines combined). Boots the Stonefish
#                             bridge automatically if it is not already up.
#
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
  godot|"")
    echo "[app] launching the Godot game-quality renderer (physics: headless Gazebo)."
    echo "[app]   (for the legacy renderer: tools/app.sh pygame)"
    exec bash "$REPO/tools/godot_app.sh"
    ;;
  stonefish)
    if ! pgrep -x MCR >/dev/null; then
      echo "[app] Stonefish not running -- bringing up the bridge first ..."
      DISPLAY="$DISPLAY" bash "$REPO/tools/stonefish_bridge.sh" up || {
        echo "[app] failed to start the Stonefish bridge." >&2; exit 1; }
      sleep 2
    fi
    echo "[app] launching Godot on Stonefish physics (both engines combined)."
    exec bash "$REPO/tools/godot_app.sh" stonefish
    ;;
  pygame|legacy)
    echo "[app] launching the legacy pygame renderer."
    exec python3 "$REPO/nodes/app/mcr_app.py" "${@:2}"
    ;;
  *)
    echo "[app] unknown mode '$MODE'. Use: godot (default) | stonefish | pygame" >&2
    exit 2
    ;;
esac
