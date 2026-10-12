#!/usr/bin/env bash
# =============================================================================
#  Authenticode-sign the Windows launcher .exe (cross-platform, on Linux).
#
#  WHAT THIS DOES: applies a SHA-256 Authenticode signature + an RFC-3161
#  trusted timestamp to MaritimeCyberRange.exe, then verifies it.
#
#  WHAT IT DOES NOT DO: it cannot, by itself, make Windows SmartScreen stop
#  warning strangers. That requires a certificate Windows already trusts:
#    * EV code-signing cert  -> instant SmartScreen trust (public distribution)
#    * OV code-signing cert  -> trusted, but SmartScreen still warns until the
#                               file earns download reputation
#    * self-signed / internal-CA cert -> ONLY trusted on machines where that
#                               cert is installed as trusted (e.g. pushed by
#                               Group Policy on managed/organisation PCs)
#
#  Prereq:  sudo apt-get install -y osslsigncode      (uses the system openssl)
#
#  Usage:
#    # with a real certificate you obtained (.pfx / .p12):
#    app/windows/sign-windows.sh --pfx mycert.pfx --pass '****' dist/MaritimeCyberRange-windows/MaritimeCyberRange.exe
#
#    # make + use a SELF-SIGNED cert (testing, or internal-trust deployments):
#    app/windows/sign-windows.sh --self-signed "Your Org Name" dist/MaritimeCyberRange-windows/MaritimeCyberRange.exe
#
#  After signing, re-zip the Windows package so the signed .exe is the one you ship.
# =============================================================================
set -euo pipefail

TSA="http://timestamp.digicert.com"     # public RFC-3161 timestamp authority
MODE=""; PFX=""; PASS=""; CN=""; EXE=""

die(){ echo "[sign] $*" >&2; exit 1; }
command -v osslsigncode >/dev/null 2>&1 || die "osslsigncode not found. Install it:  sudo apt-get install -y osslsigncode"

while [ $# -gt 0 ]; do
  case "$1" in
    --pfx)         MODE=pfx; PFX="$2"; shift 2;;
    --pass)        PASS="$2"; shift 2;;
    --self-signed) MODE=self; CN="$2"; shift 2;;
    -*)            die "unknown option: $1";;
    *)             EXE="$1"; shift;;
  esac
done
[ -n "$EXE" ] && [ -f "$EXE" ] || die "give the path to MaritimeCyberRange.exe"
[ -n "$MODE" ] || die "choose --pfx <file> --pass <pw>   OR   --self-signed \"<Org Name>\""

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

if [ "$MODE" = self ]; then
  echo "[sign] generating a SELF-SIGNED code-signing certificate for: $CN"
  echo "[sign]   (reminder: this only removes the warning on machines that TRUST this cert)"
  openssl req -x509 -newkey rsa:3072 -keyout "$WORK/key.pem" -out "$WORK/cert.pem" \
    -days 1095 -nodes -subj "/CN=${CN}" \
    -addext "keyUsage=digitalSignature" -addext "extendedKeyUsage=codeSigning" >/dev/null 2>&1
  CERT_ARGS=(-certs "$WORK/cert.pem" -key "$WORK/key.pem")
  # also emit the public cert so it can be imported into Trusted Publishers (e.g. via GPO)
  cp "$WORK/cert.pem" "$(dirname "$EXE")/MaritimeCyberRange-codesign-public.cer"
  echo "[sign] wrote public cert -> $(dirname "$EXE")/MaritimeCyberRange-codesign-public.cer"
else
  [ -f "$PFX" ] || die "pfx not found: $PFX"
  CERT_ARGS=(-pkcs12 "$PFX" -pass "$PASS")
fi

SIGNED="$WORK/signed.exe"
echo "[sign] signing (SHA-256) + timestamping via $TSA ..."
osslsigncode sign "${CERT_ARGS[@]}" \
  -h sha256 -ts "$TSA" \
  -n "Maritime Cyber Range" -i "https://github.com/" \
  -in "$EXE" -out "$SIGNED"

mv "$SIGNED" "$EXE"
echo "[sign] verifying ..."
osslsigncode verify "$EXE" || die "verification failed"
echo "[sign] DONE -> $EXE"
echo "[sign] Now rebuild the zip so the SIGNED .exe ships:  app/build-windows.sh <image.tar.gz> dist/"
