#! /usr/bin/env python3

import collections
import os
import time
import requests
import argparse
from loguru import logger
import threading
from datetime import timedelta

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
        logger.error(f"Failed fetching {service_name} data. {error=}")

    return data


def mock_data_gathering(*_unused) -> dict:
    """ Creates random data in some arbitraty format, used as a mock of data_gathering(). """
    import uuid
    import random
    from datetime import datetime, timezone
    return flatten_dict({
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
    })


def generic_api_data_logger(newfile_interval: timedelta, output_dir: str, request_interval: timedelta, service_name: str, url: str, timeout: int = 5):
    """ This function uses the DataLogger class to log any json data gathered
     from any given url, storing to a specific csv datalog file stored in
     `output_dir. This csv file is periodicly being rotated as specified in
     `newfile_interval`. """
    keys = []
    while len(keys) == 0:
        data = data_gathering(service_name, url, timeout)
        if isinstance(data, dict):
            keys = data.keys()

        time.sleep(request_interval.total_seconds())

    filename_prefix = 'log_' + service_name.replace(' ', '_').lower() + '_'
    with DataLogger(keys, newfile_interval=newfile_interval, output_dir=output_dir, log_with_timestamp=True, filename_prefix=filename_prefix) as datalogger:
        while True:
            data = data_gathering(service_name, url, timeout)
            logger.debug(
                f"{service_name}'s DataLogger (\"{datalogger._filename}\"). {data=}")
            datalogger.log(data)

            time.sleep(request_interval.total_seconds())


def hours_minutes_seconds(time: str) -> timedelta:
    """ Creates a timedelta object extracting `hours, minutes, seconds` from a `HH: MM: SS` string """
    ret = None
    try:
        h, m, s = [int(a) if a != '' else 0 for a in time.split(':')]
        ret = timedelta(hours=h, minutes=m, seconds=s)
    except Exception:
        raise ValueError('wrong time format')
    return ret


def main(args: argparse.Namespace):
    datalog_newfile_interval = args.datalog_newfile_interval
    datalog_dir = args.datalog_output_dir
    request_interval = args.services_request_interval

    # Create log directory if it doesn't exists yet
    os.makedirs(datalog_dir, exist_ok=True)

    tasks = []

    for service in [
        {'service_name': 'Weather Station',
         'url': 'http://127.0.0.1:9990/data'},
        {'service_name': 'Victron Energy MPPT',
         'url': 'http://127.0.0.1:9991/data'},
        # This saves all mavlink messages in the same file
        {'service_name': 'Autopilot mavlink messages',
         'url': 'http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages'},
        # TODO: Get CPU, DISK and RAM stats
        # {'service_name': 'Mission Status',
        #  'url': 'http://127.0.0.1:6030/system'},
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
                    'url': service['url']
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("--datalog-output-dir", type=str,
                        help="Output directory for datalog files.", default=".", required=False)
    parser.add_argument("--datalog-newfile-interval", type=hours_minutes_seconds,
                        help="Time between swap to a new file.", default='24:00:00', required=False)
    parser.add_argument("--services-request-interval", type=hours_minutes_seconds,
                        help="Time between data requests.", default='00:01:00', required=False)
    parser.add_argument("--mock-data", type=bool,
                        help="Generate mock data for testing.", default=False, required=False)
    args = parser.parse_args()

    if args.mock_data:
        data_gathering = mock_data_gathering

    main(args)
