#! /usr/bin/env python3

from dataclasses import dataclass
from datetime import datetime
from os import system
import time
from typing import List
from loguru import logger
import requests


REST_TIME_SERVICES_CHECK = 300
SOLAR_SURFER2="/home/pi"
SERVICES_PATH=f"{SOLAR_SURFER2}/services"
TOOLS_PATH=f"{SOLAR_SURFER2}/tools"
LOGS_PATH="/var/logs/blueos/solarsurfer"
VERBOSITY_LEVEL="INFO"

@dataclass
class Service:
    name: str
    status_url: str
    seconds_off_before_killing: int
    command_line: str
    utc_time_last_reach: datetime

services: List[Service] = [
    Service(
        name="sats_comm",
        status_url="http://127.0.0.1:9992/status",
        seconds_off_before_killing=21600,
        command_line=f"{SERVICES_PATH}/sats_comm/main.py --serial /dev/serial/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1:1.0-port0 --loguru-output-dir {LOGS_PATH}/sats_comm --verbosity {VERBOSITY_LEVEL}",
        utc_time_last_reach=datetime.utcnow(),
    ),
    Service(
        name="victron-energy-mppt",
        status_url="http://127.0.0.1:9991/status",
        seconds_off_before_killing=3600,
        command_line=f"{SERVICES_PATH}/victron-energy-mppt/main.py --serial /dev/serial/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.2.4.1:1.0-port0 --loguru-output-dir {LOGS_PATH}/victron-energy-mppt --verbosity {VERBOSITY_LEVEL}",
        utc_time_last_reach=datetime.utcnow(),
    ),
    Service(
        name="data-logger",
        status_url="http://127.0.0.1:9993/status",
        seconds_off_before_killing=600,
        command_line=f"{SERVICES_PATH}/data_logger/main.py --datalog-output-dir {args.logs_output_base_dir}/data --services-request-interval '00:00:01' --datalog-newfile-interval '24:00:00' --loguru-output-dir={args.logs_output_base_dir}/data_logger --verbosity {args.verbosity}",
        utc_time_last_reach=datetime.utcnow(),
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
            unreachable_for_too_long = False
            no_heartbeats_for_too_long = False
            try:
                logger.info(f"Checking status of '{service.name}' service.")
                response = requests.get(service.status_url, timeout=10.0)
                data = response.json()
                seconds_since_last_heartbeat = data["secondsSinceLastHeartbeat"]
                service.utc_time_last_reach = datetime.utcnow()
                logger.debug(f"Seconds since last '{service.name}' heartbeat: {seconds_since_last_heartbeat}.")
                no_heartbeats_for_too_long = seconds_since_last_heartbeat > service.seconds_off_before_killing
            except Exception as error:
                logger.error("Could not check satellite loop status.")
                logger.exception(error)
            finally:
                seconds_since_last_reachable = (datetime.utcnow() - service.utc_time_last_reach).seconds
                logger.debug(f"Seconds since last reach on '{service.name}': {seconds_since_last_reachable}.")
                unreachable_for_too_long = seconds_since_last_reachable > service.seconds_off_before_killing
                if no_heartbeats_for_too_long or unreachable_for_too_long:
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
