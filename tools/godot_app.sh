#!/bin/bash
# Launch the Godot 4 front-end + the Python relay (physics backend).
# Godot renders on the NVIDIA GPU; the relay bridges MAVLink<->Godot over UDP.
#
#   tools/godot_app.sh              # Gazebo physics (relay boots its own world)
#   tools/godot_app.sh stonefish    # render a running Stonefish stack (both
#                                   # softwares combined; needs stonefish_bridge.sh up)
#
# Needs: Godot 4 binary at $GODOT (or ~/godot/Godot_v4.3-stable_linux.x86_64),
# a display, and the cyber-range repo. Authorized lab/range use only.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GODOT="${GODOT:-$HOME/godot/Godot_v4.3-stable_linux.x86_64}"
PROJ="$REPO/godot_app"
SOURCE="${1:-gazebo}"

[[ -x "$GODOT" ]] || { echo "[godot_app] Godot binary not found at $GODOT (set \$GODOT)"; exit 1; }
[[ -n "${DISPLAY:-}" ]] || { echo "[godot_app] no \$DISPLAY"; exit 1; }

RELAY_ARGS=""
if [[ "$SOURCE" == "stonefish" ]]; then
  RELAY_ARGS="--source stonefish"
  echo "[godot_app] source=stonefish -- Godot will render the running Stonefish physics."
  pgrep -x MCR >/dev/null || echo "[godot_app] WARNING: MCR (Stonefish) not running; start tools/stonefish_bridge.sh up first."
fi

echo "[godot_app] starting relay (physics bridge) ..."
python3 "$REPO/tools/godot_relay.py" $RELAY_ARGS &
RELAY=$!
trap 'kill $RELAY 2>/dev/null' EXIT

echo "[godot_app] launching Godot on the NVIDIA GPU ..."
# Force the discrete NVIDIA GPU (PRIME offload) for Vulkan rendering.
__NV_PRIME_RENDER_OFFLOAD=1 __VK_LAYER_NV_optimus=NVIDIA_only __GLX_VENDOR_LIBRARY_NAME=nvidia \
  "$GODOT" --path "$PROJ"

kill $RELAY 2>/dev/null
