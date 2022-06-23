#! /usr/bin/env python3

import math
import struct
import requests
import serial
import time
from loguru import logger
from adafruit_rockblock import RockBlock, mo_status_message

REST_TIME = 600
unsent_data = []

def send_data_through_rockblock():
    # Connect to the Rockblock modem
    ser = serial.Serial(
        "/dev/serial/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1:1.0-port0",
        baudrate=19200,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=1,
    )
    rb = RockBlock(ser)
    rb.reset()

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
        logger.error(f"Failed fetching weather data. {error}")

    try:
        solar_panel_voltage = -1
        solar_panel_power = -1
        response = requests.get("http://127.0.0.1:9991/data", timeout=5)
        data = response.json()
        solar_panel_voltage = float(int(data["VPV"]) / 1000)
        solar_panel_power = float(data["PPV"])
    except Exception as error:
        logger.error(f"Failed fetching solar panel data. {error}")

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
        logger.error(f"Failed fetching autopilot position data. {error}")

    try:
        water_temp = -1
        response = requests.get("http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages/SCALED_PRESSURE2/message", timeout=5)
        data = response.json()
        water_temp = float(data["temperature"] / 100)
    except Exception as error:
        logger.error(f"Failed fetching autopilot bar100 data. {error}")

    try:
        roll = -1
        pitch = -1
        response = requests.get("http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages/ATTITUDE/message", timeout=5)
        data = response.json()
        roll = math.degrees(data["roll"])
        pitch = math.degrees(data["pitch"])
    except Exception as error:
        logger.error(f"Failed fetching autopilot attitude data. {error}")

    try:
        battery_current = -1
        battery_voltage = -1
        response = requests.get("http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages/BATTERY_STATUS/message", timeout=5)
        data = response.json()
        battery_current = float(data["current_battery"] / 100)
        battery_voltage = float(data["voltages"][0] / 1000)
    except Exception as error:
        logger.error(f"Failed fetching autopilot battery data. {error}")

    try:
        cpu_average_usage = -1
        memory_usage = -1
        available_disk_space = -1
        response = requests.get("http://127.0.0.1:6030/system", timeout=5)
        data = response.json()
        total_cpu_usage = 0
        for cpu in data["cpu"]:
            total_cpu_usage += cpu["usage"]
        cpu_average_usage = float(total_cpu_usage / 4)
        available_disk_space = float(data["disk"][0]["available_space_B"])
        memory_usage = float(data["memory"]["ram"]["used_kB"])
    except Exception as error:
        logger.error(f"Failed fetching linux system data. {error}")

    try:
        left_motor_pwm = -1
        right_motor_pwm = -1
        response = requests.get("http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages/SERVO_OUTPUT_RAW/message", timeout=5)
        data = response.json()
        left_motor_pwm = float(data["servo1_raw"])
        right_motor_pwm = float(data["servo3_raw"])
    except Exception as error:
        logger.error(f"Failed fetching autopilot motor data. {error}")

    try:
        mission_status = "undefined"
        response = requests.get("http://127.0.0.1:9992/data", timeout=5)
        data = response.json()
        mission_status = data["mission_status"]
    except Exception as error:
        logger.error(f"Failed fetching autopilot motor data. {error}")

    new_data = struct.pack("1f", time.time())
    new_data += struct.pack("1f", wind_angle)
    new_data += struct.pack("1f", wind_speed)
    new_data += struct.pack("1f", air_pressure_bar)
    new_data += struct.pack("1f", air_temp)
    new_data += struct.pack("1f", solar_panel_voltage)
    new_data += struct.pack("1f", solar_panel_power)
    new_data += struct.pack("1f", heading)
    new_data += struct.pack("1f", gps_lat)
    new_data += struct.pack("1f", gps_lon)
    new_data += struct.pack("1f", water_temp)
    new_data += struct.pack("1f", roll)
    new_data += struct.pack("1f", pitch)
    new_data += struct.pack("1f", battery_current)
    new_data += struct.pack("1f", battery_voltage)
    new_data += struct.pack("1f", cpu_average_usage)
    new_data += struct.pack("1f", memory_usage)
    new_data += struct.pack("1f", available_disk_space)
    new_data += struct.pack("1f", left_motor_pwm)
    new_data += struct.pack("1f", right_motor_pwm)
    new_data += struct.pack("1s", str.encode(mission_status))
    return new_data


def main():
    while True:
        try:
            new_data = gather_sensors_data()

            logger.debug(f"Storing gathered data on memory persistency: {new_data}")
            unsent_data.append(new_data)

            logger.debug("Trying talking to the satellites...")

            send_data_through_rockblock()
            # send_new_data_through_swarm()

        except Exception as error:
            logger.exception(error)
        finally:
            logger.debug(f"Resting for a moment ({REST_TIME} seconds) before next data transmission.")
            time.sleep(REST_TIME)

if __name__ == "__main__":
    # Wait a minute for the sensors to boot before starting regular routine
    logger.debug("Waiting for sensors to get online.")
    time.sleep(60)
    main()
