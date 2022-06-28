#! /usr/bin/env python3

import subprocess
import time
from loguru import logger
import psutil
import requests


SOLAR_SURFER2="/home/pi"
SERVICES_PATH=f"{SOLAR_SURFER2}/services"
TOOLS_PATH=f"{SOLAR_SURFER2}/tools"
LOGS_PATH="/var/logs/blueos/solarsurfer"

services = [
    {
        "name": "sats_comm",
        "status_url": "http://127.0.0.1:9992/status",
        "seconds_off_before_killing": 3600,
        "command_line": f"{SERVICES_PATH}/sats_comm/main.py --serial /dev/serial/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1:1.0-port0 --loguru-output-dir {LOGS_PATH}/sats_comm --verbosity DEBUG",
    },
]


def kill_service_by_name(name: str) -> None:
    def is_service_process(process: psutil.Process) -> bool:
        if name in " ".join(process.cmdline()):
            return True
        return False

    candidate_process = list(filter(is_service_process, psutil.process_iter()))

    for process in candidate_process:
        try:
            logger.debug(f"Killing process {process.name()}::{process.pid}.")
            process.kill()
            time.sleep(5)
        except Exception as error:
            raise RuntimeError(f"Could not kill {process.name()}::{process.pid}.") from error

def start_service_by_command(command_line: str) -> None:
    logger.debug(f"Using command_line line: '{command_line}'")
    subprocess.Popen(
        command_line,
        shell=True,
        encoding="utf-8",
        errors="ignore",
    )

def main():
    while True:
        time.sleep(60)
        for service in services:
            restart = False
            try:
                logger.info(f"Checking status of {service['name']} service.")
                response = requests.get(service["status_url"], timeout=10.0)
                data = response.json()
                seconds_since_last_heartbeat = data["secondsSinceLastHeartbeat"]
                logger.debug(f"Seconds since last {service['name']} heartbeat: {seconds_since_last_heartbeat}.")
                if seconds_since_last_heartbeat > service["seconds_off_before_killing"]:
                    restart = True
            except Exception as error:
                logger.error("Could not check satellite loop status.")
                logger.exception(error)
                restart = True
            finally:
                if restart:
                    try:
                        kill_service_by_name(service["name"])
                        time.sleep(10)
                        start_service_by_command(service["command_line"])
                    except Exception as error:
                        logger.error(f"Could not restart {service['name']}.")
                        logger.exception(error)

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            logger.error("Exception in the main supervisor loop.")
            logger.exception(e)
