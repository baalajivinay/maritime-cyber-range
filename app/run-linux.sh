#!/usr/bin/env bash
# =============================================================================
#  Maritime Cyber Range -- self-extracting Linux application (one file).
#
#  This script is the HEADER of the shipped ".run" file: the 6 GB Docker image
#  (mcr-image.tar.gz) is appended RAW after the __MCR_PAYLOAD_BELOW__ marker at
#  the very end. Running the .run:
#     1. ensures Docker is installed + running (offers to install it),
#     2. streams the appended image straight into `docker load` (no temp copy),
#     3. starts the container and opens the dashboard in your browser.
#
#  Re-running is cheap: the image load is skipped if it is already present, so
#  the second run just (re)starts the container.
#
#  Build:   app/build-linux.sh   (fills PAYLOAD_OFFSET and appends the image)
#  Verbs:   ./MaritimeCyberRange-linux.run            install + run (default)
#           ./MaritimeCyberRange-linux.run stop       stop the container
#           ./MaritimeCyberRange-linux.run uninstall  stop + remove image
# =============================================================================
set -euo pipefail

# Byte offset where the appended image payload begins. build-linux.sh rewrites
# this fixed-width field in place (do NOT change its width -- 12 digits).
PAYLOAD_OFFSET=000000000000

IMAGE="mcr:latest"
CONTAINER="mcr"
PORT=8080
URL="http://localhost:${PORT}"
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

say(){ printf '\033[1m[MCR]\033[0m %s\n' "$*"; }
warn(){ printf '\033[33m[MCR] %s\033[0m\n' "$*" >&2; }
die(){ printf '\033[31m[MCR] %s\033[0m\n' "$*" >&2; exit 1; }

# ---- pick a working `docker` (fall back to sudo if the group isn't active) ---
DOCKER=""
pick_docker(){
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER="docker"; return 0
  fi
  if command -v docker >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    DOCKER="sudo docker"; return 0
  fi
  return 1
}

ensure_docker(){
  if pick_docker; then return 0; fi

  if ! command -v docker >/dev/null 2>&1; then
    warn "Docker is not installed."
    read -r -p "[MCR] Install Docker now via the official get.docker.com script? (needs sudo) [y/N] " a
    case "${a:-}" in
      y|Y)
        curl -fsSL https://get.docker.com -o /tmp/mcr-get-docker.sh \
          || die "Could not download the Docker installer. Check your internet connection."
        sudo sh /tmp/mcr-get-docker.sh || die "Docker install failed."
        sudo usermod -aG docker "$USER" 2>/dev/null || true
        sudo systemctl enable --now docker 2>/dev/null || true
        say "Docker installed. (You may need to log out and back in for group permissions.)"
        ;;
      *) die "Docker is required. Install it from https://docs.docker.com/engine/install/ and re-run." ;;
    esac
  fi

  # Docker present but daemon not reachable -> try to start it.
  if ! pick_docker; then
    say "Starting the Docker service ..."
    sudo systemctl start docker 2>/dev/null || true
    sleep 2
  fi
  pick_docker || die "Docker is installed but the daemon is not reachable. Start Docker and re-run."
}

load_image(){
  if $DOCKER image inspect "$IMAGE" >/dev/null 2>&1; then
    say "Image '$IMAGE' already present -- skipping load."
    return 0
  fi
  say "Loading the simulator image (~21 GB uncompressed, one-time) ..."
  # Stream the appended gzip straight into docker load -- no intermediate file.
  tail -c "+$((PAYLOAD_OFFSET + 1))" "$SELF" | $DOCKER load \
    || die "docker load failed (out of disk? needs ~25 GB free)."
  say "Image loaded."
}

run_container(){
  $DOCKER rm -f "$CONTAINER" >/dev/null 2>&1 || true
  say "Starting the Maritime Cyber Range ..."
  $DOCKER run -d --name "$CONTAINER" -p "${PORT}:8080" "$IMAGE" >/dev/null \
    || die "Could not start the container (is port ${PORT} already in use?)."
  say "Waiting for the dashboard ..."
  for _ in $(seq 40); do
    if curl -s -o /dev/null "$URL" 2>/dev/null; then
      say "Dashboard is up -> $URL"
      command -v xdg-open >/dev/null 2>&1 && xdg-open "$URL" >/dev/null 2>&1 &
      echo
      say "Controls:"
      say "   stop:      $(basename "$0") stop"
      say "   uninstall: $(basename "$0") uninstall"
      return 0
    fi
    sleep 3
  done
  warn "The dashboard did not respond in time. Check: $DOCKER logs $CONTAINER"
}

cmd_stop(){ pick_docker || die "Docker not available."; $DOCKER rm -f "$CONTAINER" >/dev/null 2>&1 && say "Stopped." || say "Nothing running."; }
cmd_uninstall(){ pick_docker || die "Docker not available."; $DOCKER rm -f "$CONTAINER" >/dev/null 2>&1 || true; $DOCKER rmi "$IMAGE" >/dev/null 2>&1 && say "Image removed." || true; say "Uninstalled."; }

main(){
  case "${1:-run}" in
    run|"")   ensure_docker; load_image; run_container ;;
    stop)     cmd_stop ;;
    uninstall) cmd_uninstall ;;
    *) die "usage: $(basename "$0") [run|stop|uninstall]" ;;
  esac
}
main "$@"
exit 0
# Everything below this marker is the appended Docker image (gzip). Do not edit.
__MCR_PAYLOAD_BELOW__
