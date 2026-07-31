# Maritime Cyber Range -- full dual-domain stack in one image.
#
# Reproduces the reference machine's $HOME layout so the repo's own
# $HOME-relative launchers (tools/run_demo.sh, tools/run_sim.sh) run UNCHANGED:
#   $HOME/ardupilot            ArduPilot SITL (ardurover + ardusub)
#   $HOME/ardupilot_gazebo     ArduPilotPlugin for Gazebo
#   $HOME/SITL_Models          shared Gazebo models/worlds
#   $HOME/auv_ws/src/dave      BlueROV2 model + ardusub.parm
#   $HOME/maritime-cyber-range this repo (with ros2_ws/ VRX rebuilt here)
#
# Base OS/ROS/Gazebo match the reference: Ubuntu 24.04 + ROS 2 Jazzy + Gazebo
# Harmonic. Build:  see deploy build via ../launch.sh build  (or docker build
# -f deploy/Dockerfile -t mcr:latest .  from the repo root).
#
# Base = the official ROS 2 Jazzy image (Ubuntu 24.04). ROS + colcon + rosdep are
# pre-baked, so we skip a ~20-min apt install of ros-jazzy-desktop -- a base-image
# PULL is durable/resumable, unlike a long in-progress build layer that's thrown
# away if the build is interrupted.
FROM osrf/ros:jazzy-desktop-full

# Pinned upstreams (override with --build-arg for a different revision).
# ArduPilot uses a BRANCH/tag (not a SHA) so it can be shallow-cloned; default
# 'master' matches the reference build's line. ardupilot_gazebo is shallow-cloned
# at its default branch tip too (the pinned SHA is documented for reference).
ARG ARDUPILOT_BRANCH=master
ARG ARDUPILOT_GAZEBO_COMMIT=082a0fe
ARG DAVE_BRANCH=main
# ^ DAVE_BRANCH is intentionally left at its original value so the already-cached
#   ArduPilot compile layer is reused (any ARG-value edit busts ALL later layers'
#   BuildKit cache). dave's real branch ('ros2') is hardcoded in its clone below.

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/root \
    USER=root \
    LANG=en_US.UTF-8 \
    TZ=UTC \
    PIP_BREAK_SYSTEM_PACKAGES=1
# ^ PIP_BREAK_SYSTEM_PACKAGES: ArduPilot's install-prereqs + rosdep pip-install a
#   few packages; Ubuntu 24.04's PEP-668 guard would otherwise reject them. (The
#   app's own deps still go in an isolated venv -- see the Python layer below.)
SHELL ["/bin/bash", "-c"]

# --- base tooling + locale (ROS/colcon/rosdep already in the base image) ----
RUN apt-get update && apt-get install -y --no-install-recommends \
        sudo curl wget gnupg lsb-release ca-certificates locales \
        git build-essential cmake pkg-config tzdata python3-pip python3-venv \
        python3-colcon-common-extensions python3-rosdep python3-vcstool \
    && locale-gen en_US en_US.UTF-8 && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
    && (rosdep init 2>/dev/null || true) && rosdep update \
    && rm -rf /var/lib/apt/lists/*

# --- Gazebo Harmonic + ros_gz -- mirrors sim_config/install_gazebo.sh ------
RUN wget -q https://packages.osrfoundation.org/gazebo.gpg \
        -O /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable noble main" \
        > /etc/apt/sources.list.d/gazebo-stable.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        gz-harmonic ros-jazzy-ros-gz \
    && rm -rf /var/lib/apt/lists/*

# --- Python runtime deps ----------------------------------------------------
# Install into a venv with --system-site-packages, NOT into system dist-packages.
# ROS 2 ships many of Flask/pymavlink's transitive deps (blinker, numpy, ...) as
# dpkg packages with no pip RECORD, so `pip install` into the system env dies with
# "Cannot uninstall <pkg>, RECORD file not found" the moment a newer version is
# needed. A --system-site-packages venv SEES those system packages but installs
# the app's requirements on TOP of them inside the venv (shadowing, never
# uninstalling) -- clean and conflict-free. The entrypoint puts this venv first on
# PATH so the app's `python3 ...` calls use it; build steps keep system python3.
COPY deploy/requirements.txt /tmp/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends python3-pip python3-venv \
    && python3 -m venv --system-site-packages /opt/mcr-venv \
    && /opt/mcr-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/mcr-venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -rf /var/lib/apt/lists/*

# --- ArduPilot SITL: ardurover + ardusub -----------------------------------
# SHALLOW clone in its OWN layer: the full ArduPilot history + all submodules is
# gigabytes and the transfer 'early EOF's over a long fetch. --depth 1 +
# --shallow-submodules pulls a fraction of that (just the tip we build), and a
# separate layer means a later build interruption never re-fetches the source.
# We build the branch tip rather than a pinned SHA because shallow fetch can't
# reach an arbitrary old commit; override ARDUPILOT_BRANCH for a specific release.
RUN git config --global http.postBuffer 524288000 \
    && git clone --depth 1 --branch "$ARDUPILOT_BRANCH" --recurse-submodules --shallow-submodules \
        https://github.com/ArduPilot/ardupilot.git "$HOME/ardupilot"

# install-prereqs pulls the SITL build toolchain; then waf builds both vehicles.
# ArduPilot's install-prereqs REFUSES to run as root ("don't sudo it!"), so we do
# this one step as a non-root 'builder' user (with passwordless sudo for its own
# apt calls). The result is compiled C++ binaries under /root/ardupilot/build; at
# runtime root just executes them (no Python env needed), so cross-user is fine.
# /root is chmod 755 so 'builder' can traverse into the cloned tree.
RUN useradd -m -s /bin/bash builder \
    && echo "builder ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/builder \
    && chmod 0440 /etc/sudoers.d/builder \
    && chmod 755 /root \
    && chown -R builder:builder /root/ardupilot \
    && su - builder -c "cd /root/ardupilot \
        && Tools/environment_install/install-prereqs-ubuntu.sh -y \
        && . ~/.profile \
        && ./waf configure --board sitl \
        && ./waf rover \
        && ./waf sub" \
    && rm -rf /var/lib/apt/lists/*

# --- ArduPilotPlugin for Gazebo --------------------------------------------
# gstreamer dev libs are required by the plugin's camera-streaming component;
# installed here (not in an early layer) to keep the cached ArduPilot build above.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    && git clone https://github.com/ArduPilot/ardupilot_gazebo.git "$HOME/ardupilot_gazebo" \
    && cd "$HOME/ardupilot_gazebo" \
    && git checkout "$ARDUPILOT_GAZEBO_COMMIT" \
    && mkdir build && cd build \
    && cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    && make -j"$(nproc)" \
    && rm -rf /var/lib/apt/lists/*

# --- shared models: SITL_Models (ArduPilot) + dave (BlueROV2 + ardusub.parm)
RUN git clone --depth 1 https://github.com/ArduPilot/SITL_Models.git "$HOME/SITL_Models" \
    && mkdir -p "$HOME/auv_ws/src" \
    && git clone --depth 1 --branch ros2 https://github.com/ioes-lab/dave.git "$HOME/auv_ws/src/dave"

# --- VRX ROS2 workspace ----------------------------------------------------
# Copy ONLY the workspace SOURCE first, then build it. This way an edit to any
# OTHER repo file (launchers, entrypoint, docs) does NOT invalidate this ~20-min
# VRX compile -- only a change under ros2_ws/src does. build|install|log are
# .dockerignore'd (host artifacts); VRX is compiled fresh here.
COPY ros2_ws/src "$HOME/maritime-cyber-range/ros2_ws/src"
RUN cd "$HOME/maritime-cyber-range/ros2_ws" \
    && source /opt/ros/jazzy/setup.bash \
    && apt-get update \
    && rosdep install --from-paths src --ignore-src -r -y \
    && colcon build \
    && rm -rf /var/lib/apt/lists/* build log

# --- runtime tools the repo launchers need ---------------------------------
# iproute2 -> `ss` (run_sim.sh port health-checks); psmisc -> `fuser`
# (run_demo.sh killall_demo teardown). Placed AFTER the VRX build so it never
# invalidates that layer.
RUN apt-get update && apt-get install -y --no-install-recommends \
        iproute2 psmisc \
    && rm -rf /var/lib/apt/lists/*

# --- the rest of the project (fast layer: editing app/docs/entrypoint here
#     never triggers the VRX recompile above) ------------------------------
COPY . "$HOME/maritime-cyber-range"

# --- entrypoint ------------------------------------------------------------
COPY deploy/entrypoint.sh /usr/local/bin/mcr-entrypoint
RUN chmod +x /usr/local/bin/mcr-entrypoint

EXPOSE 8080
WORKDIR /root/maritime-cyber-range
ENTRYPOINT ["/usr/local/bin/mcr-entrypoint"]
# default: boot the underwater vehicle -- the validated headless-container demo
# (the surface wamv/VRX world doesn't boot headless in Docker; see docs/DEPLOY.md).
CMD ["up", "bluerov2"]
