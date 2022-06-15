#!/usr/bin/env bash

# Immediately exit on errors
set -e

SOLAR_SURFER2=/home/pi
SERVICES_PATH=$SOLAR_SURFER2/services
TOOLS_PATH=$SOLAR_SURFER2/tools

# MAVLink configuration
MAV_SYSTEM_ID=1
## We use the last ID for the companion computer component reserved address for our usage
MAV_COMPONENT_ID_ONBOARD_COMPUTER4=194

SERVICES=(
    'weatherstation100wx',"$SERVICES_PATH/weatherstation100wx/main.py"
)

tmux -f /etc/tmux.conf start-server

function create_service {
    tmux new -d -s "$1" || true
    SESSION_NAME="$1:0"
    # Set all necessary environment variables for the new tmux session
    for NAME in $(compgen -v | grep MAV_); do
        VALUE=${!NAME}
        tmux setenv -t $SESSION_NAME -g $NAME $VALUE
    done
    tmux send-keys -t $SESSION_NAME "$2" C-m
}

echo "Starting services.."
for TUPLE in "${SERVICES[@]}"; do
    IFS=',' read NAME EXECUTABLE <<< ${TUPLE}
    echo "Service: $NAME: $EXECUTABLE"
    create_service $NAME "$EXECUTABLE"
done

echo "SolarSurfer2 running! ☀️🏄‍♂️"
