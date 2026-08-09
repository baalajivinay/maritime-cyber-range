#!/bin/bash
set -e
source ~/.profile
cd ~/ardupilot
./waf configure --board sitl
./waf rover
./waf sub
