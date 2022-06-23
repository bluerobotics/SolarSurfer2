#! /usr/bin/env python3

import argparse
import asyncio
import json
import math
from typing import Any, Dict, List, Optional, Tuple
import requests
import serial
import time
from loguru import logger
from adafruit_rockblock import RockBlock, mo_status_message

from messages import serialize, serialize_message

parser = argparse.ArgumentParser(description="Satellite communication service")
parser.add_argument("--serial", type=str, help="Serial port", required=True)

args = parser.parse_args()

REST_TIME_DATA_OUT = 1800
REST_TIME_DATA_IN = 10
unsent_data = []

def send_data_through_rockblock():
    rb, ser = init_rockblock()

    for data_package in reversed(unsent_data):
        logger.debug(f"Trying to send data package: {data_package}.")
        rb.data_out = data_package
        retries = 0
        max_retries = 10
        while retries < max_retries:
            status_pkg = rb.satellite_transfer()
            mo_status = status_pkg[0]
            status = (mo_status, mo_status_message[mo_status])
            if mo_status <= 5:
                logger.debug(f"Sucessfully sent message. Status: {status}.")
                logger.debug("Removing gathered data from memory persistency.")
                unsent_data.pop()
                break
            logger.debug(f"Failed sending message. Status: {status}. Retrying...")
            time.sleep(0.1)
            retries += 1
    ser.close()

def get_data_through_rockblock() -> Optional[bytes]:
    last_message = None
    rb, ser = init_rockblock()
    logger.debug(f"Status: {rb.status}")
    logger.debug(f"Ring Alert mode: {rb.ring_alert}")
    logger.debug(f"Ring Alert status: {rb.ring_indication}")
    if rb.ring_indication[1] == "001" and rb.status[4] != 0:
        logger.debug("Modem Terminated message available.")
        logger.debug("Pulling data from the satellites.")
        status_pkg = rb.satellite_transfer(ring=True)
        mo_status = status_pkg[0]
        status = (mo_status, mo_status_message[mo_status])
        logger.debug(f"status_pkg: {status_pkg}")
        logger.debug(f"mo_status: {mo_status}")
        logger.debug(f"status: {status}")
        last_message: bytes = rb.data_in
    ser.close()
    return last_message

def log_modem_info() -> None:
    rb, ser = init_rockblock()
    logger.debug("Modem information:")
    logger.debug(f"Model: {rb.model}")
    logger.debug(f"Revision: {rb.revision}")
    logger.debug(f"Serial number: {rb.serial_number}")
    logger.debug(f"Status: {rb.status}")
    ser.close()

def init_rockblock() -> Tuple[RockBlock, serial.Serial]:
    ser = serial.Serial(
        args.serial,
        baudrate=19200,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=1,
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
        "header": {"system_id": 1, "component_id": 194, "sequence": 0},
        "message": message,
    }
    requests.post("http://127.0.0.1:6040/mavlink", data=json.dumps(mavlink2rest_package), timeout=10.0)

def deal_with_income_data(income_data: bytes) -> None:
    if income_data.decode().startswith("waypoint"):
        _, lat, lon, wait_time, next_id = income_data.decode().split(":")
        logger.info(f"Going to waypoint {lat}/{lon} and waiting there for {wait_time} minutes. Next waypoint will be {next_id}.")
    if income_data.decode().startswith("output_rest_time"):
        _, rest_time = income_data.decode().split(":")
        logger.info(f"Setting data output rest time to {rest_time} seconds.")
        global REST_TIME_DATA_OUT
        REST_TIME_DATA_OUT = rest_time
    if income_data.decode().startswith("input_rest_time"):
        _, rest_time = income_data.decode().split(":")
        logger.info(f"Setting data input rest time to {rest_time} seconds.")
        global REST_TIME_DATA_IN
        REST_TIME_DATA_IN = rest_time
    if income_data.decode().startswith("set_mode"):
        _, mode = income_data.decode().split(":")
        logger.info(f"Setting autopilot mode to {mode}.")
        message = command_long_message("MAV_CMD_DO_SET_MODE", [mode])
        send_mavlink_message(message)
    if income_data.decode().startswith("get_mode"):
        logger.info("Sending autopilot mode to ground station.")
        response = requests.get("http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages/GLOBAL_POSITION_INT/message", timeout=5)
        data = response.json()
        mode = data["HEARTBEAT"]["message"]["base_mode"]["bits"]
        message = {
            'text': f'Autopilot mode: {mode}'.ljust(40, '\0').encode('ascii'),
        }
        unsent_data.append(serialize_message(message))
        send_data_through_rockblock()
    if income_data.decode().startswith("arm"):
        logger.info("Arming vehicle.")
        message = command_long_message("MAV_CMD_COMPONENT_ARM_DISARM", [1])
        send_mavlink_message(message)
    if income_data.decode().startswith("disarm"):
        logger.info("Disarming vehicle.")
        message = command_long_message("MAV_CMD_COMPONENT_ARM_DISARM", [0])
        send_mavlink_message(message)

def gather_sensors_data():
    try:
        wind_angle = -1
        wind_speed = -1
        air_pressure_bar = -1
        air_temp = -1
        response = requests.get("http://127.0.0.1:9990/data", timeout=5)
        data = response.json()
        wind_angle = float(data["MWV"]["wind_angle"])
        wind_speed = float(data["MWV"]["wind_speed"])
        air_pressure_bar = float(data["MDA"]["b_pressure_bar"])
        air_temp = float(data["MDA"]["air_temp"])
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
        response = requests.get("http://127.0.0.1:9992/data", timeout=5)
        data = response.json()
        mission_status = data["mission_status"]
    except Exception as error:
        logger.exception(f"Failed fetching autopilot motor data. {error=}")

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
        'air_temperature': air_temp*255/64,
        'water_temperature': 0, #water_temp*255/64,
        'cpu': cpu_average_usage*255/100,
        'memory': used_memory*255/100,
        'disk': used_disk_space*255/100,
        'raspberry_temp': 0,
        'raspberry_volt': 0,
        'mission_status': 0, #mission_status,
        'wind_speed': wind_speed*255/64,
        'wind_angle': wind_angle*255/360,
        'gps_fix_type': 255,
        'sat_number': 255,
        'lattitude': gps_lat,
        'longitude': gps_lon,
        'next_waypoint_lattitude': 0,
        'next_waypoint_longitude': 0,
        'vdop': 0,
        'hdop': 0,
    }

    return serialize(global_message)


async def main_data_out_loop(args: argparse.Namespace):
    while True:
        try:
            logger.debug("Gattering data from payloads.")
            new_data = gather_sensors_data()

            logger.debug(
                f"Storing gathered data on memory persistency: {new_data}")
            unsent_data.append(new_data)

            logger.debug("Trying to send gathered data through satellites.")
            send_data_through_rockblock()
        except Exception as error:
            logger.exception(error)
        finally:
            logger.debug(f"Resting for a moment ({REST_TIME_DATA_OUT} seconds) before next data transmission.")
            await asyncio.sleep(REST_TIME_DATA_OUT)

async def main_data_in_loop():
    while True:
        try:
            logger.debug("Checking for incoming messages from the satellites.")
            income_data = get_data_through_rockblock()
            if income_data is not None:
                logger.debug(f"Data received: {income_data}")
                deal_with_income_data(income_data)
        except Exception as error:
            logger.exception(error)
        finally:
            logger.debug(f"Resting for a moment ({REST_TIME_DATA_IN} seconds) before checking for new incoming messages.")
            await asyncio.sleep(REST_TIME_DATA_IN)


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
        description="Sattelite Communication Service", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

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
    while True:
        try:
            # Wait a minute for the sensors to boot before starting regular routine
            delay = 60
            logger.info(f"Waiting {delay} seconds for sensors to get online...")
            time.sleep(delay)

            # Log information about the satellite modem
            log_modem_info()

            # Main data in and data out loops
            loop = asyncio.new_event_loop()
            loop.create_task(main_data_in_loop(args))
            loop.create_task(main_data_out_loop(args))
            loop.run_forever()
        except Exception as e:
            logger.error("Exception in the main loop. Restarting.")
            logger.exception(e)
