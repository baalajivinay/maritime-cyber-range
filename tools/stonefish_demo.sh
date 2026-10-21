#!/bin/bash
# Run Stonefish's high-fidelity underwater demo (Girona 500 AUV, realistic
# ocean + sonar/DVL/camera) on the discrete NVIDIA GPU.
#   tools/stonefish_demo.sh
set -u
BIN="${STONEFISH_BIN:-$HOME/stonefish_src/build/Tests/UnderwaterTest}"
[[ -x "$BIN" ]] || { echo "[stonefish] binary not found at $BIN (build Stonefish first)"; exit 1; }
[[ -n "${DISPLAY:-}" ]] || { echo "[stonefish] no \$DISPLAY"; exit 1; }
exec env __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia "$BIN"
