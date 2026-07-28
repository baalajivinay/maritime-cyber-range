#!/bin/bash
set -e
source ~/.profile
cd ~/ardupilot
Tools/autotest/sim_vehicle.py -v Rover -f rover-skid --model JSON --no-rebuild -l -33.724223,150.679736,0,0
