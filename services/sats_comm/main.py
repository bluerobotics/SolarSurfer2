import struct
import requests
import serial
import time
from loguru import logger
from adafruit_rockblock import RockBlock, mo_status_message

REST_TIME = 3600
unsent_data = []

def send_data_through_rockblock():
    # Connect to the Rockblock modem
    ser = serial.Serial(
        "/dev/ttyUSB0",
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
    weather_res = requests.get("http://127.0.0.1:9990/data")
    weather_data = weather_res.json()
    charging_res = requests.get("http://127.0.0.1:9991/data")
    charging_data = charging_res.json()

    new_data = struct.pack("1f", time.time())
    new_data += struct.pack("1f", float(weather_data["MWV"]["wind_angle"]))
    new_data += struct.pack("1f", float(weather_data["MWV"]["wind_speed"]))
    new_data += struct.pack("1f", float(weather_data["MDA"]["b_pressure_bar"]))
    new_data += struct.pack("1f", float(weather_data["MDA"]["air_temp"]))
    new_data += struct.pack("1f", float(int(charging_data["V"]) / 1000))
    new_data += struct.pack("1f", float(int(charging_data["I"]) / 1000))
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
    main()