# Maritime Cyber Range — download & run

Two self-contained builds of the simulator. Pick the one for your OS; you only
need **Docker** (the launcher offers to install it if it's missing). The app is
the web dashboard + full attack/detection/verdict stack, served at
<http://localhost:8080>. (The 3D Gazebo window is not included — it needs a GPU
desktop.)

| Your OS | File | Size |
|---|---|---|
| Linux | `MaritimeCyberRange-linux.run` | 6.1 GB |
| Windows 10/11 (64-bit) | `MaritimeCyberRange-windows.zip` | 6.1 GB |

Needs ~25 GB free disk for the loaded image, and CPU virtualization enabled
(for Docker/WSL2 on Windows).

## Verify your download first (recommended for 6 GB files)

Download `SHA256SUMS.txt` too, then:

- **Linux/macOS:** `sha256sum -c SHA256SUMS.txt`  → expect `OK`
- **Windows (PowerShell):** `Get-FileHash MaritimeCyberRange-windows.zip -Algorithm SHA256`
  and compare to the value in `SHA256SUMS.txt`.

A mismatch means a corrupted transfer — re-download.

## Linux

```bash
chmod +x MaritimeCyberRange-linux.run
./MaritimeCyberRange-linux.run          # loads the image once, then opens the dashboard
```
Controls: `./MaritimeCyberRange-linux.run stop` · `./MaritimeCyberRange-linux.run uninstall`.
First-time Docker install needs a terminal (for the sudo prompt) — run it from a
terminal, not a double-click, if Docker isn't installed yet.

## Windows

1. **Unzip, keeping all files together** — `MaritimeCyberRange.exe` / `.bat` need
   `mcr-image.tar.gz` sitting next to them.
2. Double-click **`MaritimeCyberRange.exe`** (or `MaritimeCyberRange.bat`).
3. If Docker Desktop isn't installed, the launcher offers to install it; you'll
   reboot once, then run it again.
4. The dashboard opens at <http://localhost:8080>.

> **SmartScreen:** this build is **unsigned**, so Windows may show
> "Windows protected your PC" → click **More info → Run anyway**. (A signed
> build removes this — see `app/windows/SIGNING.md` in the source repo.)

To stop: open PowerShell and run `docker rm -f mcr`.

## What you're looking at

Open the dashboard, pick a destination on the map, fire the GPS / AIS / C2 /
acoustic attack buttons, and watch the vessel's true-vs-believed position
diverge while the blind detectors raise alerts. The default vehicle is the
vulnerable CUSV twin. Full walkthrough is in the source repo's
`docs/TWIN_DEMO_GUIDE.md`.
