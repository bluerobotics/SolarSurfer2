#! /usr/bin/env python3

import argparse
import asyncio
import pynmea2
import serial
import time
import uvicorn
from pprint import pprint
from typing import Any, List
from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

parser = argparse.ArgumentParser(description="WeatherStation® 100WX Service")
parser.add_argument("--serial", type=str, help="Serial port", required=True)

args = parser.parse_args()

app = FastAPI()

# for nome information of units and variables check this: https://github.com/Knio/pynmea2/blob/e2dd9e5716d144dd24161b5622622fcf9be7e6b1/pynmea2/types/talker.py

global_data = {}

def handle_nmea(nmea_message) -> None:
    message_dict = {}
    for i in range(len(nmea_message.fields)):
        message_dict[nmea_message.fields[i][1]] = nmea_message.data[i]
    print(message_dict)
    global_data[nmea_message.sentence_type] = message_dict

async def read_data() -> None:
    print("Rading data thread running.")
    while True:
        await asyncio.sleep(5)
        try:
            with serial.Serial(args.serial, baudrate=4800, timeout=1) as device:
                while True:
                    await asyncio.sleep(0.01)
                    line = device.readline().decode('ascii', errors='replace').strip()
                    try:
                        message = pynmea2.parse(line)
                        print(message.sentence_type)
                        handle_nmea(message)
                    except Exception as exception:
                        print(f"Exception: {exception}")
        except Exception as exception:
            print(f"Exception: {exception}")

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
        <html>
            <head>
                <title>WeatherStation® 100WX</title>
            </head>
        </html>
    """

@app.get("/data", response_class=JSONResponse)
async def data():
    return global_data

if __name__ == "__main__":
    loop = asyncio.new_event_loop()

    config = uvicorn.Config(app=app, loop=loop, host="0.0.0.0", port=9990, log_config=None)
    server = uvicorn.Server(config)

    loop.create_task(read_data())
    loop.run_until_complete(server.serve())
