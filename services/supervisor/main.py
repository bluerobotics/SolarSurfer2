#! /usr/bin/env python3

from collections import namedtuple
from os import system
import time
from typing import List
from loguru import logger
import requests


REST_TIME_SERVICES_CHECK = 60
SOLAR_SURFER2="/home/pi"
SERVICES_PATH=f"{SOLAR_SURFER2}/services"
TOOLS_PATH=f"{SOLAR_SURFER2}/tools"
LOGS_PATH="/var/logs/blueos/solarsurfer"

Service = namedtuple("Service", ["name", "status_url", "seconds_off_before_killing", "command_line"])
services: List[Service] = [
    Service(
        name="sats_comm",
        status_url="http://127.0.0.1:9992/status",
        seconds_off_before_killing=3600,
        command_line=f"{SERVICES_PATH}/sats_comm/main.py --serial /dev/serial/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1:1.0-port0 --loguru-output-dir {LOGS_PATH}/sats_comm --verbosity DEBUG",
    ),
]


def restart_service(service: Service) -> None:
    logger.debug(f"Killing service '{service.name}'.")
    kill_service(service)
    time.sleep(10)
    logger.debug(f"Starting service '{service.name}' with command-line '{service.command_line}'.")
    start_service(service)
    time.sleep(10)

def kill_service(service: Service) -> None:
    system(f"tmux kill-session -t '{service.name}'")

def start_service(service: Service) -> None:
    system(f"tmux new -d -s {service.name}")
    system(f"tmux send-keys -t {service.name} '{service.command_line}' C-m")

def main():
    while True:
        logger.debug(f"Resting for {REST_TIME_SERVICES_CHECK} seconds before next supervisor cycle.")
        time.sleep(REST_TIME_SERVICES_CHECK)
        for service in services:
            restart = False
            try:
                logger.info(f"Checking status of '{service.name}' service.")
                response = requests.get(service.status_url, timeout=10.0)
                data = response.json()
                seconds_since_last_heartbeat = data["secondsSinceLastHeartbeat"]
                logger.debug(f"Seconds since last '{service.name}' heartbeat: {seconds_since_last_heartbeat}.")
                if seconds_since_last_heartbeat > service.seconds_off_before_killing:
                    restart = True
            except Exception as error:
                logger.error("Could not check satellite loop status.")
                logger.exception(error)
                restart = True
            finally:
                if restart:
                    try:
                        restart_service(service)
                    except Exception as error:
                        logger.error(f"Could not restart '{service.name}'.")
                        logger.exception(error)

if __name__ == "__main__":
    logger.info("Supervisor service started.")
    while True:
        try:
            main()
        except Exception as e:
            logger.error("Exception in the main supervisor loop.")
            logger.exception(e)
