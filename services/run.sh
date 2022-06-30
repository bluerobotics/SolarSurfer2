#!/usr/bin/env bash

# Immediately exit on errors
set -e

# Get CLI parameters
SERVICES_VERBOSITY_LEVEL="${1:-INFO}"

# Settings for SolarSurfer2 services
SOLAR_SURFER2_HOME=/home/pi
SERVICES_PATH=$SOLAR_SURFER2_HOME/services
LOGS_PATH=/var/logs/blueos/solarsurfer
SERIAL_VICTRON_ENERGY_MPPT=/dev/serial/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.2.4.1:1.0-port0
SERIAL_SATS_COMM=/dev/serial/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1:1.0-port0

# Start the tmux server
TMUX_SESSION_NAME="SolarSurfer2"
tmux -f /etc/tmux.conf start-server
tmux new -t $TMUX_SESSION_NAME -d


# Start the Supervisor, which will run and manager all SolarSurfer2 services
SUPERVISOR=(
    $SERVICES_PATH/supervisor/main.py
    --logs-output-base-dir $LOGS_PATH
    --verbosity $SERVICES_VERBOSITY_LEVEL
    --serial-sats-comm $SERIAL_SATS_COMM
    --serial-victron-energy-mppt $SERIAL_VICTRON_ENERGY_MPPT
)
tmux send-keys -t $TMUX_SESSION_NAME "${SUPERVISOR[*]}" C-m
