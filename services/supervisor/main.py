#! /usr/bin/env python3

import argparse
from dataclasses import dataclass
from datetime import datetime
from os import system
import time
from typing import List
from loguru import logger
import requests


REST_TIME_SERVICES_CHECK = 300
SOLAR_SURFER2_HOME = "/home/pi"
SERVICES_PATH = f"{SOLAR_SURFER2_HOME}/services"


class LoguruLevelArgumentValidator(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        """ Parse loguru log levels """
        levels = ["TRACE", "DEBUG", "INFO",
                  "SUCCESS", "WARNING", "ERROR", "CRITICAL"]
        if values not in levels:
            raise argparse.ArgumentTypeError(
                f"Wrong log level passed, available: {levels}.")
        setattr(namespace, self.dest, values)


def get_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Supervisor", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("--serial-victron-energy-mppt", type=str,
                        help="Serial port for Victron Energy MPPT", required=True)
    parser.add_argument("--serial-sats-comm", type=str,
                        help="Serial port for Sattelite Communicator", required=True)
    parser.add_argument("--logs-output-base-dir", type=str, default="/var/logs/blueos/solarsurfer",
                        help="Configure output base directory, used by both Loguru and Data Logger.")
    parser.add_argument("-v", "--verbosity", dest="verbosity", type=str, action=LoguruLevelArgumentValidator, default="INFO",
                        help="Configure loguru verbosity level: TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL.")

    return parser.parse_args()


args = get_arguments()


@dataclass
class Service:
    name: str
    status_url: str
    seconds_off_before_killing: int
    command_line: str
    utc_time_last_reach: datetime

    def restart(self) -> None:
        logger.debug(f"Killing service '{self.name}'.")
        self.kill_service()
        time.sleep(10)
        logger.debug(
            f"Starting service '{self.name}' with command-line '{self.command_line}'.")
        self.start_service()
        time.sleep(10)

    def kill(self) -> None:
        system(f"tmux kill-session -t '{self.name}'")

    def start(self) -> None:
        system(f"tmux new -d -s {self.name}")
        system(f"tmux send-keys -t {self.name} '{self.command_line}' C-m")


services: List[Service] = [
    Service(
        name="sats_comm",
        status_url="http://127.0.0.1:9992/status",
        seconds_off_before_killing=600,
        command_line=f"{SERVICES_PATH}/sats_comm/main.py --serial {args.serial_sats_comm} --loguru-output-dir {args.logs_output_base_dir}/sats_comm --verbosity {args.verbosity}",
        utc_time_last_reach=datetime.utcnow(),
    ),
    Service(
        name="victron-energy-mppt",
        status_url="http://127.0.0.1:9991/status",
        seconds_off_before_killing=3600,
        command_line=f"{SERVICES_PATH}/victron-energy-mppt/main.py --serial {args.serial_victron_energy_mppt} --loguru-output-dir {args.logs_output_base_dir}/victron-energy-mppt --verbosity {args.verbosity}",
        utc_time_last_reach=datetime.utcnow(),
    ),
]


def main():
    [service.start() for service in services]
    logger.info("SolarSurfer2 running! ☀️🏄‍♂️")

    while True:
        logger.debug(
            f"Resting for {REST_TIME_SERVICES_CHECK} seconds before next supervisor cycle.")
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
                logger.debug(
                    f"Seconds since last '{service.name}' heartbeat: {seconds_since_last_heartbeat}.")
                no_heartbeats_for_too_long = seconds_since_last_heartbeat > service.seconds_off_before_killing
            except Exception as error:
                logger.error("Could not check satellite loop status.")
                logger.exception(error)
            finally:
                seconds_since_last_reachable = (
                    datetime.utcnow() - service.utc_time_last_reach).seconds
                logger.debug(
                    f"Seconds since last reach on '{service.name}': {seconds_since_last_reachable}.")
                unreachable_for_too_long = seconds_since_last_reachable > service.seconds_off_before_killing
                if no_heartbeats_for_too_long or unreachable_for_too_long:
                    try:
                        service.restart()
                    except Exception as error:
                        logger.error(f"Could not restart '{service.name}'.")
                        logger.exception(error)


def configure_logging(args: argparse.Namespace):
    loguru_output_file = args.logs_output_base_dir + \
        "/supervisor/loguru_supervisor_{time}.log"

    logger.add(loguru_output_file,
               level=args.verbosity, rotation="00:00", compression="zip")
    logger.warning(
        f"This service is being logged with Loguru with level {args.verbosity} into the file {loguru_output_file}.")


if __name__ == "__main__":
    configure_logging(args)

    logger.info("Supervisor service started.")
    while True:
        try:
            main()
        except Exception as e:
            logger.error("Exception in the main supervisor loop.")
            logger.exception(e)
