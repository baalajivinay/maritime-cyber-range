# Windows runtime test checklist

The Windows launcher is authored and syntax-clean, but it has **not** been run
on real Windows (the build machine is Linux). Run this once on a Windows 10/11
64-bit PC and report what happens at each step — that's the real runtime test.

## Setup
1. Copy `MaritimeCyberRange-windows.zip` to the Windows machine and extract it.
   Keep all files together (especially the 6 GB `mcr-image.tar.gz`).
2. Ensure ~25 GB free disk and that CPU virtualization is enabled (BIOS) — Docker
   Desktop/WSL2 needs it.

## Test A — launcher with Docker already installed (happy path)
Pre-install Docker Desktop first, start it, then:
- [ ] Double-click `MaritimeCyberRange.exe` (and separately test `MaritimeCyberRange.bat`).
- [ ] Expected console: `Image 'mcr:latest' ... loading ...` on first run (one-time),
      then `Starting the Maritime Cyber Range ...` → `Dashboard is up`.
- [ ] Browser opens `http://localhost:8080` and the dashboard loads.
- [ ] `docker ps` shows a running `mcr` container publishing `8080`.
- [ ] Stop: PowerShell → `docker rm -f mcr`.

## Test B — Docker NOT installed (install path)
On a machine without Docker Desktop:
- [ ] Run the launcher; it should prompt to install Docker Desktop.
- [ ] Accept → it downloads + runs the official installer (UAC prompt appears).
- [ ] It tells you to reboot; reboot; run the launcher again → happy path (Test A).

## Test C — SmartScreen behaviour (unsigned vs signed)
- [ ] Unsigned `.exe`: expect "Windows protected your PC" → **More info → Run anyway**.
- [ ] After signing (see `sign-windows.sh`): with an EV cert the popup should not
      appear; with a self-signed cert it only disappears on machines that trust
      the cert (import `MaritimeCyberRange-codesign-public.cer` into
      *Trusted Publishers* + *Trusted Root*, or push it via Group Policy).

## What to report back
For each step: did it match "Expected"? Paste any red error text and the output of
`docker logs mcr` if the dashboard didn't come up. I'll fix the launcher from that.
