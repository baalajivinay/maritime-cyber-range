; ============================================================================
;  Maritime Cyber Range -- small Windows launcher .exe (NSIS).
;
;  NSIS installers cannot embed a file larger than ~2 GB, so this .exe does NOT
;  contain the 6 GB image. It embeds only MaritimeCyberRange.ps1 and runs it,
;  pointing it at $EXEDIR -- the folder the user ran the .exe from, where the
;  mcr-image.tar.gz data file sits next to it (FitGirl-style: launcher + data).
;
;  Build (on Linux or Windows):  makensis app/windows/installer.nsi
;  Produces:  MaritimeCyberRange.exe
; ============================================================================
Unicode true
Name "Maritime Cyber Range"
OutFile "MaritimeCyberRange.exe"
RequestExecutionLevel user          ; the .ps1 self-elevates only if it must install Docker
SilentInstall silent                 ; no installer UI -- it's a launcher, not a setup
; Icon "mcr.ico"                     ; (optional) drop a 256x256 mcr.ico here to brand the .exe

Section
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File "MaritimeCyberRange.ps1"
  ; run the launcher; $EXEDIR = where this .exe (and the image data file) live
  nsExec::ExecToLog 'powershell -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\MaritimeCyberRange.ps1" -DataDir "$EXEDIR"'
  Pop $0
SectionEnd
