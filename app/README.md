# Packaging the Maritime Cyber Range as a one-file application

This turns the project into a shareable "download-and-run" app (FitGirl-repack
style): the recipient runs **one launcher**, it brings up Docker, loads the
simulator image, and opens the dashboard at <http://localhost:8080>. The 3D
Gazebo window is **not** included (it needs a GPU/X desktop); the app is the web
dashboard + full attack/detection/verdict stack.

Everything is built from the `mcr:latest` Docker image (see `../deploy/`). The
image is the real payload (~21 GB uncompressed, ~6 GB gzipped); these scripts
wrap it so no Docker knowledge is required to run it.

## What ships

| Platform | Artifact | Form |
|---|---|---|
| **Linux** | `MaritimeCyberRange-linux.run` | **One self-contained file** — the launcher with the 6 GB image appended after it. Run it: `./MaritimeCyberRange-linux.run`. |
| **Windows** | `MaritimeCyberRange-windows.zip` | A folder: small `MaritimeCyberRange.exe` (or `.bat`) **+ `mcr-image.tar.gz` beside it**. NSIS can't embed >2 GB in one `.exe`, so the image rides alongside the launcher (exactly how a repack ships `setup.exe` + data). |

Both launchers: ensure Docker is present (offer to install it) → `docker load`
the image once → `docker run -p 8080:8080` → open the browser. Re-running just
restarts the container (the load is skipped if the image is already present).

## Build

Prereq: a built `mcr:latest` image, and `../deploy/` able to rebuild it.
First produce the image tarball once (reused by both builders):

```bash
docker save mcr:latest | gzip > /tmp/mcr-image.tar.gz
```

### Linux (one self-extracting file) — no extra tools
```bash
app/build-linux.sh /tmp/mcr-image.tar.gz dist/MaritimeCyberRange-linux.run
```
Implementation: `run-linux.sh` is the launcher **and** the self-extractor header.
`build-linux.sh` fills its `PAYLOAD_OFFSET` (byte position where the image
begins) and appends the raw gzip. At runtime the launcher streams
`tail -c +OFFSET "$0" | docker load` — no temp copy of the 6 GB.

### Windows (launcher + data) — `.exe` needs NSIS
```bash
sudo apt-get install -y nsis          # one-time, to cross-build the .exe on Linux
app/build-windows.sh /tmp/mcr-image.tar.gz dist/
```
Without NSIS the builder still produces the package using the `.bat` launcher
(the `.exe` is just a thin wrapper around the same `MaritimeCyberRange.ps1`).

## Files here

| File | Role |
|---|---|
| `run-linux.sh` | Linux launcher + self-extractor header (the shipped `.run` is this + the image). |
| `build-linux.sh` | Assembles `MaritimeCyberRange-linux.run`. |
| `windows/MaritimeCyberRange.ps1` | The Windows launcher logic (Docker check/install, load, run, browser). |
| `windows/MaritimeCyberRange.bat` | No-build double-click fallback that runs the `.ps1`. |
| `windows/installer.nsi` | NSIS source for the small `MaritimeCyberRange.exe` wrapper. |
| `build-windows.sh` | Compiles the `.exe` (if NSIS present) and zips the Windows package. |

## Caveats (be honest with recipients)

- **Docker is required.** The launchers install it for you (official installers),
  but on Windows that means Docker Desktop + WSL2 + **admin rights and a reboot** —
  unavoidable, no installer can skip it.
- **Disk:** ~25 GB free for the loaded image.
- **Linux `.run` first-time Docker install** needs a terminal (the sudo prompt) —
  run it from a terminal the first time, not a double-click, if Docker is absent.
- **Windows `.exe` is authored but not yet tested** from this repo (no Windows
  box here) — give it one real run on Windows before sharing widely.
