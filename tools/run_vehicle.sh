#!/bin/bash
# Boot a self-contained vehicle_twins/<name>/ folder by path, without having
# to know or care about this repo's internal profiles/ layout.
#
# Usage:
#   tools/run_vehicle.sh vehicle_twins/<name> up|down|status
#
# A vehicle_twins/<name>/ folder contains everything specific to that
# digital twin: profile.json (+ hardened.parm if it's a hardened one),
# target.json (for tools/test_target.py), and a README.md explaining the
# expected result per attack. This script's only job is to make that
# profile.json discoverable where tools/run_sim.sh (the actual boot engine,
# unchanged) expects to find it -- profiles/<name>.json -- via a symlink, so
# the folder stays the single source of truth and nothing gets copied out of
# sync. Everything else (the underlying model.sdf/world.sdf, shared meshes)
# is referenced by profile.json via ordinary repo-relative paths, exactly
# like every other profile.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FOLDER="${1:?usage: run_vehicle.sh <path-to-vehicle_twins-folder> up|down|status}"
ACTION="${2:-up}"

# Accept the folder with or without a trailing slash, relative or absolute.
FOLDER="${FOLDER%/}"
if [[ "$FOLDER" != /* ]]; then FOLDER="$REPO/$FOLDER"; fi

PROFILE_JSON="$FOLDER/profile.json"
[[ -f "$PROFILE_JSON" ]] || { echo "FATAL: no profile.json in '$FOLDER'"; exit 1; }

NAME="$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['name'])")"
[[ -n "$NAME" ]] || { echo "FATAL: profile.json in '$FOLDER' has no \"name\""; exit 1; }

ln -sf "$PROFILE_JSON" "$REPO/profiles/$NAME.json"

echo "[run_vehicle] $FOLDER -> profile '$NAME'"
exec "$REPO/tools/run_sim.sh" "$NAME" "$ACTION"
