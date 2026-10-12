#!/usr/bin/env bash
# =============================================================================
#  Build the single-file Linux application:  MaritimeCyberRange-linux.run
#
#  Output = app/run-linux.sh (the launcher header, with PAYLOAD_OFFSET filled)
#           + the raw Docker image gzip appended after its marker.
#
#  Usage:  app/build-linux.sh [path/to/mcr-image.tar.gz] [output.run]
#  If no image path is given, it is produced from the local `mcr:latest`.
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
HEADER="$HERE/run-linux.sh"

IMG_TAR="${1:-}"
OUT="${2:-$REPO/dist/MaritimeCyberRange-linux.run}"
MARKER="__MCR_PAYLOAD_BELOW__"

mkdir -p "$(dirname "$OUT")"

# 1. Obtain the image tarball (reuse if provided; else export mcr:latest).
CLEANUP_TAR=""
if [ -z "$IMG_TAR" ]; then
  IMG_TAR="$(mktemp --suffix=.tar.gz)"
  CLEANUP_TAR="$IMG_TAR"
  echo "[build] exporting mcr:latest -> $IMG_TAR (a few minutes) ..."
  docker save mcr:latest | gzip > "$IMG_TAR"
fi
[ -s "$IMG_TAR" ] || { echo "[build] image tarball is empty/missing: $IMG_TAR" >&2; exit 1; }

# 2. Stage the header and compute the exact byte offset of the appended payload.
#    The payload begins immediately after the marker LINE, so the header length
#    (everything up to and including "<marker>\n") IS the offset.
TMP_HEADER="$(mktemp)"
cp "$HEADER" "$TMP_HEADER"
# truncate the staged header at the marker line (drop anything after it)
awk -v m="$MARKER" '{print} $0==m{exit}' "$HEADER" > "$TMP_HEADER"
HEADER_BYTES="$(wc -c < "$TMP_HEADER")"

# 3. Write the real offset into the 12-digit field (width preserved -> length stable).
OFFSET_STR="$(printf '%012d' "$HEADER_BYTES")"
sed -i "s/^PAYLOAD_OFFSET=[0-9]\{12\}$/PAYLOAD_OFFSET=${OFFSET_STR}/" "$TMP_HEADER"
# sanity: length must be unchanged after the substitution
[ "$(wc -c < "$TMP_HEADER")" -eq "$HEADER_BYTES" ] || { echo "[build] offset rewrite changed header size -- abort" >&2; exit 1; }

# 4. Assemble: header + raw image gzip.
echo "[build] assembling $OUT ..."
cat "$TMP_HEADER" "$IMG_TAR" > "$OUT"
chmod +x "$OUT"
rm -f "$TMP_HEADER"
[ -n "$CLEANUP_TAR" ] && rm -f "$CLEANUP_TAR"

echo "[build] done: $OUT"
ls -lh "$OUT"
echo "[build] payload offset = $HEADER_BYTES bytes"
echo "[build] self-test: the first appended byte should be gzip magic (1f 8b):"
{ tail -c "+$((HEADER_BYTES + 1))" "$OUT" 2>/dev/null | head -c 2 | od -An -tx1; } || true
