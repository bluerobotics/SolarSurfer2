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

parser = argparse.ArgumentParser(description="Victron Energy MPPT driver")
parser.add_argument("--serial", type=str, help="Serial port", required=True)

args = parser.parse_args()

app = FastAPI()

global_data = {}

def parse(lines) -> None:
    try:
        for line in lines:
            content = line.split('\t')
            global_data[content[0]] = content[1]
    except Exception as exception:
        print(f"Parser failed: {exception}")

async def read_data() -> None:
    print("Rading data thread running.")
    while True:
        await asyncio.sleep(5)
        try:
            with serial.Serial(args.serial, baudrate=19200, timeout=1) as device:
                lines = []
                while True:
                    await asyncio.sleep(0.01)
                    lines += [device.readline().decode('ascii', errors='replace').strip()]
                    print(lines[-1])
                    if 'Checksum' in lines[-1] and 'PID' in lines[0]:
                        print(lines)
                        parse(lines)
                        lines = []
                    if len(lines) > 40:
                        print('Buffer is huge aborting!')
                        lines = []


        except Exception as exception:
            print(f"Exception: {exception}")

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

if __name__ == "__main__":
    loop = asyncio.new_event_loop()

    config = uvicorn.Config(app=app, loop=loop, host="0.0.0.0", port=9991, log_config=None)
    server = uvicorn.Server(config)

    loop.create_task(read_data())
    loop.run_until_complete(server.serve())
