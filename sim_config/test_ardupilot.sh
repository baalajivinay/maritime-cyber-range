#!/bin/bash
source ~/.profile
cd ~/ardupilot
timeout 30s Tools/autotest/sim_vehicle.py -v Rover --console
