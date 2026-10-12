#!/usr/bin/env bash
# =============================================================================
#  Build the Windows application folder:  MaritimeCyberRange-windows.zip
#
#  Layout (FitGirl-style -- a small launcher + the big data file beside it):
#     MaritimeCyberRange.exe      <- compiled by makensis (if available)
#     MaritimeCyberRange.bat      <- no-.exe fallback (always works)
#     MaritimeCyberRange.ps1      <- the actual launcher logic
#     mcr-image.tar.gz            <- the ~6 GB Docker image
#     README.txt
#
#  NSIS (makensis) is only needed for the .exe; the .bat works without it.
#  Install NSIS to cross-build the .exe on Linux:   sudo apt-get install -y nsis
#
#  Usage:  app/build-windows.sh [path/to/mcr-image.tar.gz] [output_dir]
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
WIN="$HERE/windows"

IMG_TAR="${1:-}"
OUTDIR="${2:-$REPO/dist}"
STAGE="$OUTDIR/MaritimeCyberRange-windows"

[ -n "$IMG_TAR" ] && [ -s "$IMG_TAR" ] || { echo "[build] pass the image tarball: build-windows.sh <mcr-image.tar.gz>" >&2; exit 1; }
mkdir -p "$STAGE"

# 1. Compile the small launcher .exe (optional -- needs makensis).
if command -v makensis >/dev/null 2>&1; then
  echo "[build] compiling MaritimeCyberRange.exe with makensis ..."
  ( cd "$WIN" && makensis -V2 installer.nsi )
  mv "$WIN/MaritimeCyberRange.exe" "$STAGE/"
  echo "[build]   .exe built."
else
  echo "[build] makensis not found -- skipping the .exe (the .bat still works)."
  echo "[build]   install it with:  sudo apt-get install -y nsis   then re-run."
fi

# 2. Stage the launcher scripts.
cp "$WIN/MaritimeCyberRange.ps1" "$WIN/MaritimeCyberRange.bat" "$STAGE/"

# 3. Stage the data file (copy so the original tarball is preserved).
echo "[build] copying the 6 GB image into the package ..."
cp "$IMG_TAR" "$STAGE/mcr-image.tar.gz"

# 4. A plain-text readme for the recipient.
cat > "$STAGE/README.txt" <<'TXT'
Maritime Cyber Range -- Windows
================================
1. Keep all files in this folder together (especially mcr-image.tar.gz).
2. Double-click MaritimeCyberRange.exe  (or MaritimeCyberRange.bat).
3. If Docker Desktop is not installed, the launcher offers to install it.
   You will need to reboot once after that, then run the launcher again.
4. The simulator dashboard opens at http://localhost:8080.

To stop:   open PowerShell and run    docker rm -f mcr
Requires:  Windows 10/11 64-bit with virtualization enabled (for Docker/WSL2),
           about 25 GB free disk.
TXT

# 5. Zip it up.
echo "[build] zipping the package ..."
( cd "$OUTDIR" && rm -f MaritimeCyberRange-windows.zip \
    && zip -r -q MaritimeCyberRange-windows.zip "MaritimeCyberRange-windows" )
echo "[build] done: $OUTDIR/MaritimeCyberRange-windows.zip"
ls -lh "$OUTDIR/MaritimeCyberRange-windows.zip"
