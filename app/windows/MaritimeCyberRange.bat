@echo off
REM Maritime Cyber Range -- Windows launcher (no-build fallback).
REM Double-click this, OR run the compiled MaritimeCyberRange.exe -- both do the
REM same thing. Keep mcr-image.tar.gz in this same folder.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MaritimeCyberRange.ps1" -DataDir "%~dp0"
echo.
pause
