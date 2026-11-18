#!/usr/bin/env bash
# =============================================================================
# Maritime Cyber Range — Primary Application Launcher
#
# Launches the Professional 2D Tactical Conning & Cyber Resilience Console
# (Conforming to IEC 62288, IEC 61174, and IACS UR E26/E27).
#
# Usage:
#   ./run_app.sh            # Launch Professional Tactical Console (default)
#   ./run_app.sh pygame     # Fallback 2D Pygame console (headless/lightweight)
# =============================================================================
set -e
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$REPO_DIR:$REPO_DIR/application:$REPO_DIR/communication:$REPO_DIR/attacks:$REPO_DIR/application/external/venv-ardupilot/lib/python3.12/site-packages:${PYTHONPATH:-}"


MODE="${1:-console}"

if [[ -z "${DISPLAY:-}" ]]; then
  echo "[app] no \$DISPLAY -- the application needs a graphical display." >&2
  exit 1
fi

case "$MODE" in
  console|"")
    exec python3 "$REPO_DIR/application/console/app.py" "${@:2}"
    ;;
  pygame|legacy)
    exec python3 "$REPO_DIR/communication/mcr_app.py" "${@:2}"
    ;;
  *)
    exec python3 "$REPO_DIR/application/console/app.py" "$@"
    ;;
esac
