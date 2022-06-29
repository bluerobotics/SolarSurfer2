#! /usr/bin/env python3

import argparse
import asyncio
from datetime import datetime
import json
import math
from typing import Any, Dict, List, Optional, Tuple
import requests
import serial
import time
import uvicorn
from loguru import logger
from adafruit_rockblock import RockBlock, mo_status_message
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from messages import serialize


app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
        <html>
            <head>
                <title>Satellite communication service</title>
            </head>
        </html>
    """


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

parser = argparse.ArgumentParser(description="Sattelite Communication Service", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument("--loguru-output-dir", type=str, default=".",
                    help="Configure loguru output dir.")
parser.add_argument("-v", "--verbosity", dest="verbosity", type=str, action=LoguruLevelArgumentValidator, default="INFO",
                    help="Configure loguru verbosity level: TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL.")
parser.add_argument("--serial", type=str, help="Serial port", required=True)

args = parser.parse_args()

UTC_TIME_LAST_HEARTBEAT = datetime.utcnow()
MESSAGES_ON_MT_QUEUE = False
REST_TIME_DATA_OUT = 120
REST_TIME_DATA_IN = 10
unsent_data = []

def send_data_through_rockblock():
    rb, ser = init_rockblock()

    for data_package in reversed(unsent_data):
        logger.info(f"Trying to send data package: {data_package}.")
        rb.data_out = data_package
        retries = 0
        max_retries = 10
        while retries < max_retries:
            logger.debug(f"Retry {retries}.")
            status_pkg = rb.satellite_transfer()
            mo_status = status_pkg[0]
            status = (mo_status, mo_status_message[mo_status])
            logger.debug(f"status_pkg: {status_pkg} // mo_status: {mo_status} // status: {status}")
            if mo_status <= 5:
                logger.success("Sucessfully sent message.")
                logger.info("Removing gathered data from memory persistency.")
                unsent_data.pop()
                break
            logger.error("Failed sending message. Retrying...")
            time.sleep(0.1)
            retries += 1
    ser.close()

def get_data_through_rockblock() -> Optional[bytes]:
    global MESSAGES_ON_MT_QUEUE
    last_message = None
    rb, ser = init_rockblock()
    logger.debug(f"Status: {rb.status} // Ring Alert mode: {rb.ring_alert} // Ring Alert status: {rb.ring_indication}")
    ring_alert_received = rb.status[4] == 1
    if ring_alert_received:
        logger.info("Ring alert received. Modem Terminated message *maybe* available.")
    if MESSAGES_ON_MT_QUEUE or ring_alert_received:
        logger.info("Pulling messages from the satellites.")
        retries = 0
        max_retries = 10
        while retries < max_retries:
            logger.debug(f"Retry {retries}.")
            status_pkg = rb.satellite_transfer(ring=True)
            mo_status = status_pkg[0]
            status = (mo_status, mo_status_message[mo_status])
            logger.debug(f"status_pkg: {status_pkg} // mo_status: {mo_status} // status: {status}")
            if mo_status <= 5:
                last_message: bytes = rb.data_in
                logger.success("Sucessfully received message.")
                MESSAGES_ON_MT_QUEUE = int(status_pkg[5]) > 0
                if MESSAGES_ON_MT_QUEUE:
                    logger.debug("There are still MT messages on the queue.")
                break
            logger.error("Failed receiving message. Retrying...")
            time.sleep(0.1)
            retries += 1
    ser.close()
    return last_message

def log_modem_info() -> None:
    rb, ser = init_rockblock()
    logger.info("Modem information:")
    logger.info(f"Model: {rb.model}")
    logger.info(f"Revision: {rb.revision}")
    logger.info(f"Serial number: {rb.serial_number}")
    logger.info(f"Status: {rb.status}")
    ser.close()

def init_rockblock() -> Tuple[RockBlock, serial.Serial]:
    ser = serial.Serial(
        args.serial,
        baudrate=19200,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=1,
        write_timeout=1,
    )
    rb = RockBlock(ser)
    rb.ring_alert = True
    return rb, ser

def command_long_message(command_type: str, params: List[float]) -> Dict[str, Any]:
    return {
        "type": "COMMAND_LONG",
        "param1": params[0] if len(params) > 0 else 0,
        "param2": params[1] if len(params) > 1 else 0,
        "param3": params[2] if len(params) > 2 else 0,
        "param4": params[3] if len(params) > 3 else 0,
        "param5": params[4] if len(params) > 4 else 0,
        "param6": params[5] if len(params) > 5 else 0,
        "param7": params[6] if len(params) > 6 else 0,
        "command": {"type": command_type},
        "target_system": 1,
        "target_component": 1,
        "confirmation": 0,
    }

def send_mavlink_message(message: Dict[str, Any]) -> None:
    mavlink2rest_package = {
        "header": {"system_id": 255, "component_id": 240, "sequence": 0},
        "message": message,
    }
    logger.debug(f"Sending following mavlink package to Mavlink2Rest: {mavlink2rest_package}")
    response = requests.post("http://127.0.0.1:6040/mavlink", data=json.dumps(mavlink2rest_package), timeout=10.0)
    logger.debug(f"Response from Mavlink2Rest: {response.__dict__}")

def set_param(param_name, value) -> None:
    logger.info(f"Setting {param_name} to {value}.")
    message = {
        "type": "PARAM_SET",
        "param_value": float(value),
        "target_system": 1,
        "target_component": 0,
        "param_id": [
            "\x00",
            "\x00",
            "\x00",
            "\x00",
            "\x00",
            "\x00",
            "\x00",
            "\x00",
            "\x00",
            "\x00",
            "\x00",
            "\x00",
            "\x00",
            "\x00",
            "\x00",
            "\x00"
        ],
        "param_type": {
            "type": "MAV_PARAM_TYPE_REAL32"
        }
    }

    for i, char in enumerate(param_name):
        message["param_id"][i] = char

    send_mavlink_message(message)

def deal_with_income_data(income_data: bytes) -> None:
    if income_data.decode().startswith("waypoint"):
        _, lat, lon, wait_time, next_id = income_data.decode().split(":")
        logger.info(f"Going to waypoint {lat}/{lon} for {wait_time}s. Next waypoint will be {next_id}.")

        logger.debug("Setting MISSION_PAUSE_S.")
        set_param("MISSION_PAUSE_S", float(wait_time))
        time.sleep(10)

        logger.debug("Setting guided mode.")
        message = command_long_message("MAV_CMD_DO_SET_MODE", [1, 15])
        send_mavlink_message(message)
        time.sleep(10)

        logger.debug("Setting current waypoint.")
        message = {
            "type": "MISSION_ITEM_INT",
            "param1": 0.0,
            "param2": 0.0,
            "param3": 0.0,
            "param4": 0.0,
            "x": int(float(lat)*1e7),
            "y": int(float(lon)*1e7),
            "z": 1.0,
            "seq": 0,
            "command": {
                "type": "MAV_CMD_NAV_WAYPOINT"
            },
            "target_system": 1,
            "target_component": 1,
            "frame": {
                "type": "MAV_FRAME_GLOBAL_INT"
            },
            "current": 2,
            "autocontinue": 1,
            "mission_type": {
                "type": "MAV_MISSION_TYPE_MISSION"
            }
        }
        send_mavlink_message(message)
        time.sleep(5)

        logger.debug("Setting next waypoint.")
        message = {
            "type": "MISSION_SET_CURRENT",
            "seq": int(next_id),
            "target_system": 1,
            "target_component": 0
        }
        send_mavlink_message(message)

    if income_data.decode().startswith("output_rest_time"):
        _, rest_time = income_data.decode().split(":")
        logger.info(f"Setting data output rest time to {rest_time} seconds.")
        global REST_TIME_DATA_OUT
        REST_TIME_DATA_OUT = int(rest_time)
    if income_data.decode().startswith("input_rest_time"):
        _, rest_time = income_data.decode().split(":")
        logger.info(f"Setting data input rest time to {rest_time} seconds.")
        global REST_TIME_DATA_IN
        REST_TIME_DATA_IN = int(rest_time)
    if income_data.decode().startswith("set_mode"):
        _, mode = income_data.decode().split(":")
        logger.info(f"Setting autopilot mode to {mode}.")
        if mode == "manual":
            message = command_long_message("MAV_CMD_DO_SET_MODE", [1, 0])
        elif mode == "auto":
            message = command_long_message("MAV_CMD_DO_SET_MODE", [1, 10])
        elif mode == "smart_rtl":
            message = command_long_message("MAV_CMD_DO_SET_MODE", [1, 12])
        elif mode == "guided":
            message = command_long_message("MAV_CMD_DO_SET_MODE", [1, 15])
        else:
            message = command_long_message("MAV_CMD_DO_SET_MODE", [mode])
        send_mavlink_message(message)
    if income_data.decode().startswith("get_mode"):
        logger.info("Sending autopilot mode to ground station.")
        response = requests.get("http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages/HEARTBEAT/message", timeout=5)
        data = response.json()
        mode = data["base_mode"]["bits"]
        message = f'text:Autopilot mode: {mode}'.encode('ascii')
        unsent_data.append(message)
        send_data_through_rockblock()
    if income_data.decode().startswith("arm"):
        logger.info("Arming vehicle.")
        message = command_long_message("MAV_CMD_COMPONENT_ARM_DISARM", [1])
        send_mavlink_message(message)
    if income_data.decode().startswith("disarm"):
        logger.info("Disarming vehicle.")
        message = command_long_message("MAV_CMD_COMPONENT_ARM_DISARM", [0])
        send_mavlink_message(message)
    if income_data.decode().startswith("set_param"):
        _, param_name, value = income_data.decode().split(":")
        set_param(param_name, float(value))
    acknowledge_message = f"cmd_ack:{income_data.decode()}".encode("ascii")
    unsent_data.append(acknowledge_message)
    send_data_through_rockblock()

def gather_sensors_data():
    try:
        wind_angle = -1
        wind_speed = -1
        air_pressure_bar = -1
        air_temp = -1
        #response = requests.get("http://127.0.0.1:9990/data", timeout=5)
        #data = response.json()
        #wind_angle = float(data["MWV"]["wind_angle"])
        #wind_speed = float(data["MWV"]["wind_speed"])
        #air_pressure_bar = float(data["MDA"]["b_pressure_bar"])
        #air_temp = float(data["MDA"]["air_temp"])
    except Exception as error:
        logger.exception(f"Failed fetching weather data. {error=}")

    try:
        solar_panel_voltage = -1
        solar_panel_power = -1
        response = requests.get("http://127.0.0.1:9991/data", timeout=5)
        data = response.json()
        solar_panel_voltage = float(int(data["VPV"]) / 1000)
        solar_panel_power = float(data["PPV"])
    except Exception as error:
        logger.exception(f"Failed fetching solar panel data. {error=}")

    try:
        heading = -1
        gps_lat = -1
        gps_lon = -1
        heading = -1
        response = requests.get("http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages/GLOBAL_POSITION_INT/message", timeout=5)
        data = response.json()
        heading = float(data["hdg"] / 100)
        gps_lat = float(data["lat"] / 1e7)
        gps_lon = float(data["lon"] / 1e7)
    except Exception as error:
        logger.exception(f"Failed fetching autopilot position data. {error=}")

    try:
        sat_number = 0
        vdop = -1
        hdop = -1
        response = requests.get("http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages/GPS2_RAW/message", timeout=5)
        data = response.json()
        vdop = float(data["epv"])
        hdop = float(data["eph"])
        sat_number = float(data['satellites_visible'])
    except Exception as error:
        logger.exception(f"Failed fetching autopilot vh/dop data. {error=}")

    try:
        time_boot_ms = -1
        time_unix_usec = -1
        response = requests.get("http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages/SYSTEM_TIME/message", timeout=5)
        data = response.json()
        time_boot_ms = float(data["time_boot_ms"])
        time_unix_usec = float(data["time_unix_usec"])
    except Exception as error:
        logger.exception(f"Failed fetching autopilot time data. {error=}")

    try:
        water_temp = -1
        response = requests.get("http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages/SCALED_PRESSURE/message", timeout=5)
        data = response.json()
        water_temp = float(data["temperature"] / 100)
    except Exception as error:
        logger.exception(f"Failed fetching autopilot bar100 data. {error=}")

    try:
        roll = -1
        pitch = -1
        response = requests.get("http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages/ATTITUDE/message", timeout=5)
        data = response.json()
        roll = math.degrees(data["roll"])
        pitch = math.degrees(data["pitch"])
    except Exception as error:
        logger.exception(f"Failed fetching autopilot attitude data. {error=}")

    try:
        battery_current = -1
        battery_voltage = -1
        response = requests.get("http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages/BATTERY_STATUS/message", timeout=5)
        data = response.json()
        battery_current = float(data["current_battery"] / 100)
        battery_voltage = float(data["voltages"][0] / 1000)
    except Exception as error:
        logger.exception(f"Failed fetching autopilot battery data. {error=}")

    try:
        cpu_average_usage = -1
        used_memory = -1
        used_disk_space = -1
        response = requests.get("http://127.0.0.1:6030/system", timeout=5)
        data = response.json()
        total_cpu_usage = 0
        for cpu in data["cpu"]:
            total_cpu_usage += cpu["usage"]
        cpu_average_usage = float(total_cpu_usage / 4)
        used_disk_space = (float(data["disk"][0]["total_space_B"]) - float(data["disk"][0]["available_space_B"]))*100/float(data["disk"][0]["total_space_B"])
        used_memory = float(data["memory"]["ram"]["used_kB"])*100/float(data["memory"]["ram"]["total_kB"])
    except Exception as error:
        logger.exception(f"Failed fetching linux system data. {error=}")

    try:
        left_motor_pwm = -1
        right_motor_pwm = -1
        response = requests.get("http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages/SERVO_OUTPUT_RAW/message", timeout=5)
        data = response.json()
        left_motor_pwm = float(data["servo1_raw"])
        right_motor_pwm = float(data["servo3_raw"])
    except Exception as error:
        logger.exception(f"Failed fetching autopilot motor data. {error=}")

    try:
        mission_status = 0
        #response = requests.get("http://127.0.0.1:9992/data", timeout=5)
        #data = response.json()
        #mission_status = data["mission_status"]
    except Exception as error:
        logger.exception(f"Failed fetching autopilot mission data. {error=}")

    global_message = {
        'name': 'global',
        'heading': heading*255/360,
        'max_abs_roll': 0,
        'max_abs_pitch': 0,
        'battery_voltage': battery_voltage*255/20,
        'battery_current': battery_current*255/64,
        'solar_voltage': solar_panel_voltage*255/64,
        'solar_power': solar_panel_power*255/200,
        'throttle_first': ((left_motor_pwm-1100)/800)*255,
        'throttle_second': ((right_motor_pwm-1100)/800)*255,
        'air_temperature': 0, #air_temp*255/64,
        'water_temperature': 0, #water_temp*255/64,
        'cpu': cpu_average_usage*255/100,
        'memory': used_memory*255/100,
        'disk': used_disk_space*255/100,
        'raspberry_temp': 0,
        'raspberry_volt': 0,
        'mission_status': 0, #mission_status,
        'gps_fix_type': 255,
        'sat_number': sat_number,
        'lattitude': gps_lat,
        'longitude': gps_lon,
        'next_waypoint_lattitude': 0,
        'next_waypoint_longitude': 0,
        'vdop': vdop,
        'hdop': hdop,
        'time_boot_ms': time_boot_ms,
        'time_unix_usec': time_unix_usec
    }

    return serialize(global_message)

def beat_the_heart():
    global UTC_TIME_LAST_HEARTBEAT
    UTC_TIME_LAST_HEARTBEAT = datetime.utcnow()


async def main_data_out_loop(args: argparse.Namespace):
    while True:
        try:
            logger.info("Gattering data from payloads.")
            new_data = gather_sensors_data()

            logger.info(f"Storing gathered data on memory persistency: {new_data}")
            unsent_data.append(new_data)

            logger.info("Trying to send gathered data through satellites.")
            send_data_through_rockblock()
            beat_the_heart()
        except Exception as error:
            logger.exception(error)
        finally:
            logger.info(f"Resting for a moment ({REST_TIME_DATA_OUT} seconds) before next data transmission.")
            await asyncio.sleep(REST_TIME_DATA_OUT)

async def main_data_in_loop():
    while True:
        try:
            logger.info("Checking for incoming messages from the satellites.")
            income_data = get_data_through_rockblock()
            if income_data is not None:
                logger.debug(f"Data received: {income_data}")
                deal_with_income_data(income_data)
        except Exception as error:
            logger.exception(error)
        finally:
            logger.info(f"Resting for a moment ({REST_TIME_DATA_IN} seconds) before checking for new incoming messages.")
            await asyncio.sleep(REST_TIME_DATA_IN)

def configure_logging(args: argparse.Namespace):
    loguru_output_file = args.loguru_output_dir + \
        "/loguru_datalogger_{time}.log"

    logger.add(loguru_output_file,
               level=args.verbosity, rotation="00:00", compression="zip")
    logger.warning(
        f"This service is being logged with Loguru with level {args.verbosity} into the file {loguru_output_file}.")


if __name__ == "__main__":
    configure_logging(args)
    while True:
        try:
            # Wait a minute for the sensors to boot before starting regular routine
            delay = 60
            logger.info(f"Waiting {delay} seconds for sensors to get online...")
            time.sleep(delay)

            # Log information about the satellite modem
            log_modem_info()

            loop = asyncio.new_event_loop()

            # Main data in and data out loops
            loop.create_task(main_data_in_loop())
            loop.create_task(main_data_out_loop(args))

            # Create API
            config = uvicorn.Config(app=app, loop=loop, host="0.0.0.0", port=9992, log_config=None)
            server = uvicorn.Server(config)
            loop.create_task(server.serve())

            loop.run_forever()
        except Exception as e:
            logger.error("Exception in the main loop. Restarting.")
            logger.exception(e)
