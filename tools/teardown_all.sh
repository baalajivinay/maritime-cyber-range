#!/bin/bash
# Reliable orphan reaper. Kills every component of any running stack, regardless
# of which profile or site booted it, then clears the FIFO keepalives. Safe to
# run anytime (a no-op if nothing is up).
#
# Complements `tools/run_sim.sh <profile> down`, which only kills the ONE
# profile's recorded PIDs and so can leave orphans behind after a crashed or
# half-finished boot (observed live: a dead stack left tools/test_target.py
# unable to connect). Use this between matrix runs and whenever a boot is wedged.
#
# Usage: tools/teardown_all.sh
set +e

PATTERNS=(
  "gz sim" "ardurover" "ardusub" "mav_bridge.py" "gps_spoof.py"
  "acoustic_spoof.py" "ais_emulator.py" "dashboard_server.py" "inject_current.py"
)
for p in "${PATTERNS[@]}"; do
  pkill -9 -f "$p" 2>/dev/null
done

# FIFO keepalives: run_sim.sh holds each relay/SITL FIFO open with a detached
# `exec 9>FIFO; sleep infinity`. Reap those too, then remove the FIFOs.
pkill -9 -f "sleep infinity" 2>/dev/null
sleep 1
rm -f /tmp/mcr_run/*/*.fifo 2>/dev/null

echo "[teardown_all] reaped stack processes (run dirs under /tmp/mcr_run/ left for inspection)"

stubborn=0
for p in "gz sim" ardurover ardusub; do
  if pgrep -f "$p" >/dev/null 2>&1; then
    echo "[teardown_all] WARNING: '$p' still present after SIGKILL"
    stubborn=1
  fi
done
exit $stubborn
