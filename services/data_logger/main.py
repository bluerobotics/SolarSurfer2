#! /usr/bin/env python3

import collections
import os
import subprocess
import time
import requests
import argparse
from loguru import logger
import threading
from datetime import timedelta
from typing import Callable

from data_logger import DataLogger


def flatten_dict(dictionary: dict, parent_key: bool = False, separator: str = '.') -> dict:
    """ Transforms a nested dict into a flatten dict. From: https://stackoverflow.com/a/62186053 """
    items = []
    for key, value in dictionary.items():
        new_key = str(parent_key) + separator + str(key) if parent_key else key
        if isinstance(value, collections.abc.MutableMapping):
            items.extend(flatten_dict(value, new_key, separator).items())
        elif isinstance(value, list):
            for k, v in enumerate(value):
                items.extend(flatten_dict({str(k): v}, new_key).items())
        else:
            items.append((new_key, value))

    return dict(items)


def data_gathering(service_name: str, url: str, timeout: int = 5) -> dict:
    """ Gathers data from the given url using a GET request. """
    data = None
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200 and response.text != 'None':
            data = flatten_dict(response.json())
    except Exception as error:
        logger.exception(f"Failed fetching {service_name} data. {error=}")

    return data


def mock_data_gathering(service_name: str, *_unused) -> dict:
    """ Creates random data in some arbitraty format, used as a mock of data_gathering(). """
    import uuid
    import random
    import json
    from datetime import datetime, timezone

    data = {}
    pwd = os.path.dirname(__file__)

    if service_name == 'Weather Station':
        data = json.load(
            open(f"{pwd}/sample_data/sample_weatherstation_request.json"))
    elif service_name == 'Victron Energy MPPT':
        data = json.load(
            open(f"{pwd}/sample_data/sample_vctron_energy_mppt_request.json"))

    elif service_name == 'Autopilot mavlink messages':
        data = json.load(
            open(f"{pwd}/sample_data/sample_mavlink_request.json"))

    elif service_name == 'System Information':
        data = json.load(
            open(f"{pwd}/sample_data/sample_system_information_request.json"))

    else:
        data = {
            'timestamp': datetime.now(tz=timezone.utc),
            'some_string': str(uuid.uuid4().hex),
            'some_float': float(random.uniform(-1, 1)),
            'some_bool': bool(random.uniform(-1, 1) > 0),
            'some_nested': {
                'float': float(random.uniform(-1, 1)),
                'bool': bool(random.uniform(-1, 1) > 0),
            },
            'some_list': ['a', 'b', 'c', 'd'],
            'some_integer': int(random.randint(0, 255)),
            'some_non_ascci': str(
                ','.join([(chr(random.randint(8000, 9000))) for _ in range(32)])),
        }

    return flatten_dict(data)


def generic_api_data_logger(newfile_interval: timedelta, output_dir: str, request_interval: timedelta, service_name: str, url: str, timeout: int = 5, filter: Callable[[dict], dict] = None):
    """ This function uses the DataLogger class to log any json data gathered
     from any given url, storing to a specific csv datalog file stored in
     `output_dir. This csv file is periodicly being rotated as specified in
     `newfile_interval`. """
    keys = []
    while len(keys) == 0:
        data = data_gathering(service_name, url, timeout)
        if filter is not None and isinstance(data, dict):
            try:
                data = filter(data)
            except Exception as e:
                logger.exception(e)

        if isinstance(data, dict):
            keys = data.keys()

        time.sleep(request_interval.total_seconds())

    filename_prefix = 'log_' + service_name.replace(' ', '_').lower() + '_'
    with DataLogger(keys, newfile_interval=newfile_interval, output_dir=output_dir, log_with_timestamp=True, filename_prefix=filename_prefix) as datalogger:
        while True:
            data = data_gathering(service_name, url, timeout)
            if filter is not None:
                try:
                    data = filter(data)
                except Exception as e:
                    logger.exception(e)

            logger.trace(
                f"{service_name}'s DataLogger (\"{datalogger._filename}\"). {data=}")
            datalogger.log(data)

            time.sleep(request_interval.total_seconds())


def main(args: argparse.Namespace):
    datalog_newfile_interval = args.datalog_newfile_interval
    datalog_dir = args.datalog_output_dir
    request_interval = args.services_request_interval

    # Create log directory if it doesn't exists yet
    os.makedirs(datalog_dir, exist_ok=True)

    tasks = []

    for service in [
        #{'service_name': 'Weather Station', 'url': 'http://127.0.0.1:9990/data'},
        {'service_name': 'Victron Energy MPPT',
         'url': 'http://127.0.0.1:9991/data'},
        # This saves all mavlink messages in the same file
        {'service_name': 'Autopilot mavlink messages',
         'url': 'http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages'},
        {'service_name': 'System Information',
         'url': 'http://127.0.0.1:6030/system',
         'filter': system_information_filter},
    ]:
        tasks.append(
            {
                'task': generic_api_data_logger,
                'thread': None,
                'args': {
                    'newfile_interval': datalog_newfile_interval,
                    'output_dir': datalog_dir,
                    'request_interval': request_interval,
                    'service_name': service['service_name'],
                    'url': service['url'],
                    'filter': service.get('filter', None),
                },
            }
        )

    tasks.append(
        {
            'task': monitor_dir_size_growth,
            'thread': None,
            'args': {
                'dir': datalog_dir,
                'period': 60,
            },
        }
    )

    # start/restart all tasks as daemons so that they are killed when the main program exits
    while True:
        time.sleep(1)
        for task in tasks:
            thread = task['thread']
            if thread == None or not thread.is_alive():
                logger.debug(f"Creating a DataLogger. {task=}")
                task['thread'] = threading.Thread(
                    target=task['task'], daemon=True, kwargs=task['args'])
                task['thread'].start()


def system_information_filter(data: dict) -> dict:
    return {
        "cpu": data.get("cpu", None),
        "disk": data.get("disk", None),
        "network": data.get("network", None),
        "memory": data.get("memory", None),
        "temperature": data.get("temperature", None),
        "unix_time_seconds": data.get("unix_time_seconds", None),
    }


def du(path):
    """disk usage in bytes"""
    size = int(0)
    try:
        size = int(subprocess.check_output(
            ['du', path]).split()[0].decode('utf-8'))
    except Exception as error:
        logger.exception(
            f"Error trying to compute dir {path} size: {error=}")
    return size


def monitor_dir_size_growth(dir: str, period: int = 60):
    sizes = [du(dir), 0]  # as [new, old]
    times = [time.time(), 0]  # as [new, old]
    while True:
        size = du(dir)
        if size != sizes[0]:
            sizes = [size, sizes[0]]
            times = [time.time(), times[0]]
            size_growth = (sizes[0] - sizes[1]) / (times[0] - times[1])
            size_growth *= 24 * 3600 / 1024**2  # bytes per second to megabytes per day
            logger.info(
                f"Directory: ({dir}) size growth: {size_growth} mb per day.")

        time.sleep(period)


class TimedeltaArgumentValidator(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        """ Creates a timedelta object extracting `hours, minutes, seconds` from a `HH:MM:SS` string """
        try:
            h, m, s = [int(a) if a != '' else 0 for a in values.split(':')]
            time = timedelta(hours=h, minutes=m, seconds=s)
        except Exception:
            raise argparse.ArgumentTypeError(
                "Wrong time format, expect \"HH:MM:SS\".")
        setattr(namespace, self.dest, time)


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
        description="", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("--datalog-output-dir", type=str,
                        help="Output directory for datalog files.", default=".", required=False)
    parser.add_argument("--datalog-newfile-interval", type=str, action=TimedeltaArgumentValidator,
                        help="Time between swap to a new file.", default='24:00:00', required=False)
    parser.add_argument("--services-request-interval", type=str, action=TimedeltaArgumentValidator,
                        help="Time between data requests.", default='00:01:00', required=False)
    parser.add_argument("--mock-data", type=bool,
                        help="Generate mock data for testing.", default=False, required=False)
    parser.add_argument("--loguru-output-dir", type=str, default=".",
                        help="Configure loguru output dir.")
    parser.add_argument("-v", "--verbosity", dest="verbosity", type=str, action=LoguruLevelArgumentValidator, default="INFO",
                        help="Configure loguru verbosity level: TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL.")

    return parser.parse_args()


def configure_logging(args: argparse.Namespace):
    loguru_output_file = args.loguru_output_dir + \
        "/loguru_datalogger_{time}.log"

    logger.add(loguru_output_file,
               level=args.verbosity, rotation="00:00", compression="zip")
    logger.warning(
        f"This service is being logged with Loguru with level {args.verbosity} into the file {loguru_output_file}.")


if __name__ == "__main__":
    args = get_arguments()
    configure_logging(args)

    if args.mock_data:
        data_gathering = mock_data_gathering

    main(args)
