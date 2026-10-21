#!/bin/bash
# Launch the Maritime Cyber Range native application (pygame).
# One window: pick a site + vehicle, watch it move over the water, set a
# destination, launch attacks. Physics runs headless underneath; no Gazebo
# window, no browser. Needs a display ($DISPLAY) and pygame.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${DISPLAY:-}" ]]; then
  echo "[app] no \$DISPLAY -- the application needs a graphical display." >&2
  exit 1
fi
exec python3 "$REPO/nodes/app/mcr_app.py" "$@"
