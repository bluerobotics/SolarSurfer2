#! /usr/bin/env python3

import argparse
import asyncio
from datetime import datetime
import pynmea2
import serial
import time
import uvicorn
from pprint import pprint
from loguru import logger
from typing import Any, List
from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()

global_data = {}
UTC_TIME_LAST_HEARTBEAT = datetime.utcnow()


def parse(lines) -> None:
    try:
        for line in lines:
            content = line.split('\t')
            if len(content) != 2:
                logger.warning(
                    f"Can't parse because it is missing a separator (\\t) or has more than one. {line=}.")
                break
            global_data[content[0]] = content[1]
    except Exception as exception:
        logger.exception(f"Parser failed: {exception=}")


async def read_data(args: argparse.Namespace) -> None:
    logger.debug("Rading data thread running.")
    while True:
        await asyncio.sleep(5)
        try:
            with serial.Serial(args.serial, baudrate=19200, timeout=1) as device:
                lines = []
                while True:
                    await asyncio.sleep(0.01)

                    if device.in_waiting == 0:
                        continue

                    data = device.readline()
                    logger.debug(f"Read {data=}")
                    # Using 'backslashreplace' to keep the byte of the Checksum intact: b'Checksum\t\x92\r\n' -> b'Checksum\t\\x92'
                    lines += [data.decode('ascii',
                                          errors='backslashreplace').strip()]
                    logger.debug(f"Data decoded as {lines[-1]=}")

                    # "The maximum number of fields in a block is 22" ("VE.Direct Protocol" pdf, downloadable from https://www.victronenergy.com/support-and-downloads/technical-information)
                    if 'PID' not in lines[0] or len(lines) > 22:
                        logger.debug(
                            f"Start of the frame (\"PID\") not in received, or received too many fields ({len(lines)}) without \"Checksum\", skipping...")
                        lines = []
                        continue

                    # Only parse after have the Checksum of the block
                    if 'Checksum' in lines[-1]:
                        logger.debug(lines)
                        parse(lines)
                        beat_the_heart()
                        lines = []

        except Exception as exception:
            logger.exception(f"Exception: {exception}")


def beat_the_heart():
    global UTC_TIME_LAST_HEARTBEAT
    UTC_TIME_LAST_HEARTBEAT = datetime.utcnow()


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
        <html>
            <head>
                <title>Victron Energy MPPT driver</title>
            </head>
        </html>
    """


@app.get("/data", response_class=JSONResponse)
async def data():
    return global_data


@app.get("/status", response_class=JSONResponse)
async def status():
    return {
        "utcTimeNow": datetime.utcnow(),
        "utcTimeLastHeartbeat": UTC_TIME_LAST_HEARTBEAT,
        "secondsSinceLastHeartbeat": (datetime.utcnow() - UTC_TIME_LAST_HEARTBEAT).seconds,
    }


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
        description="Victron Energy MPPT driver", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("--serial", type=str,
                        help="Serial port", required=True)
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

    loop = asyncio.new_event_loop()

    config = uvicorn.Config(
        app=app, loop=loop, host="0.0.0.0", port=9991, log_config=None)
    server = uvicorn.Server(config)

    loop.create_task(read_data(args))
    loop.run_until_complete(server.serve())
