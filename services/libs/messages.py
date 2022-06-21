#! /usr/bin/env python3

from struct import pack, unpack, calcsize
from collections import namedtuple

START = '$'
ENDIAN = '<'
MESSAGES = {
    'global': {
        'id': 1,
        'fields': [
            ('heading', 'B', '360degree/256'),
            ('max_abs_roll', 'B', '360degree/256'),
            ('max_abs_pitch', 'B', '360degree/256'),
            ('battery_voltage', 'B', 'decavoltage/256'),
            ('battery_current', 'B', '64amps/256'),
            ('solar_voltage', 'B', '64volts/256'),
            ('solar_power', 'B', '200w/256'),
            ('throttle_first', 'B', '100%/256'),
            ('throttle_second', 'B', '100%/256'),
            ('air_temperature', 'B', '64celsius/256'),
            ('water_temperature', 'B', '64celsius/256'),
            ('cpu', 'B', '100/256'),
            ('memory', 'B', '100/256'),
            ('disk', 'B', '100/256'),
            ('raspberry_temp', 'B', '128celsius/256'),
            ('raspberry_volt', 'B', '10volts/256'),
            ('mission_status', 'B', 'holding,running,drift,disarmed'),
            ('wind_speed', 'B', '64meters/second'),
            ('wind_angle', 'B', '360degree/256'),
            ('gps_fix_type', 'B', 'no gps/no fix/2d fix/3d fix'),
            ('sat_number', 'B', 'number'),
            ('lattitude', 'f', 'degrees'),
            ('longitude', 'f', 'degrees'),
            ('next_waypoint_lattitude', 'f', 'degrees'),
            ('next_waypoint_longitude', 'f', 'degrees'),
            ('vdop', 'H', 'uin16_t'),
            ('hdop', 'H', 'uin16_t'),
        ],
    },
    'waypoint': {
        'id': 2,
        'fields': [
            ('lattitude', 'f', 'degrees'),
            ('longitude', 'f', 'degrees'),
            ('holding_time', 'H', 'minutes'),
        ],
    },
    'control': {
        'id': 3,
        'fields': [
            ('type', 'B', 'Hold, run, drift, disarm'),
        ],
    },
    'message': {
        'id': 4,
        'fields': [
            ('text', '40s', 'text string'),
        ],
    },
}

def get_header(name):
    return (START + chr(MESSAGES[name]['id'])).encode('ascii')

def get_struct_format(name):
    return ENDIAN + ''.join([f[1] for f in MESSAGES[name]['fields']])

def _serialize(content, name):
    definition = MESSAGES[name]
    data = []
    for name, field, kind in definition['fields']:
        data += [pack(ENDIAN + field, content[name])]
    return b''.join(data)

def _deserialize(data, name):
    definition = MESSAGES[name]
    names = [f[0] for f in definition['fields']]
    format = get_struct_format(name)
    values = unpack(format, data)
    return dict(zip(names, values))

def deserialize(data):
    assert chr(data[0]) == START, 'Start byte does not match'
    ids_to_name = {MESSAGES[name]['id']:name for name in MESSAGES}
    assert data[1] in [MESSAGES[name]['id'] for name in MESSAGES], 'Message id does not match'
    name = ids_to_name[data[1]]
    result = _deserialize(data[2:], name)
    result['name'] = name
    return result

def serialize(data):
    assert 'name' in data, 'Name does not exist in data'
    return get_header(data['name']) + _serialize(data, data['name'])

def serialize_global(data):
    return _serialize(data, 'global')

def serialize_waypoint(data):
    return _serialize(data, 'waypoint')

def serialize_control(data):
    return _serialize(data, 'control')

def serialize_message(data):
    return _serialize(data, 'message')

def deserialize_global(data):
    return _deserialize(data, 'global')

def deserialize_waypoint(data):
    return _deserialize(data, 'waypoint')

def deserialize_control(data):
    return _deserialize(data, 'control')

def deserialize_message(data):
    return _deserialize(data, 'message')


if __name__ == "__main__":
    global_message = {
        'heading': 1,
        'max_abs_roll': 2,
        'max_abs_pitch': 3,
        'battery_voltage': 4,
        'battery_current': 5,
        'solar_voltage': 6,
        'solar_power': 7,
        'throttle_first': 8,
        'throttle_second': 9,
        'air_temperature': 10,
        'water_temperature': 11,
        'cpu': 12,
        'memory': 13,
        'disk': 14,
        'raspberry_temp': 15,
        'raspberry_volt': 16,
        'mission_status': 17,
        'wind_speed': 18,
        'wind_angle': 19,
        'gps_fix_type': 20,
        'sat_number': 21,
        'lattitude': 22,
        'longitude': 23,
        'next_waypoint_lattitude': 24,
        'next_waypoint_longitude': 25,
        'vdop': 26,
        'hdop': 27,
    }
    print(calcsize(get_struct_format('global')))
    print(global_message == deserialize_global(serialize_global(global_message)))
    global_message['name'] = 'global'
    print(global_message == deserialize(serialize(global_message)))

    waypoint_message = {
        'lattitude': 0,
        'longitude': 1,
        'holding_time': 2,
    }
    print(calcsize(get_struct_format('waypoint')))
    print(waypoint_message == deserialize_waypoint(serialize_waypoint(waypoint_message)))
    waypoint_message['name'] = 'waypoint'
    print(waypoint_message == deserialize(serialize(waypoint_message)))

    control_message = {
        'type': 128,
    }
    print(calcsize(get_struct_format('control')))
    print(control_message == deserialize_control(serialize_control(control_message)))
    control_message['name'] = 'control'
    print(control_message == deserialize(serialize(control_message)))

    message = {
        'text': 'Blue Robotics!'.ljust(40, '\0').encode('ascii'),
    }
    print(calcsize(get_struct_format('message')))
    print(message == deserialize_message(serialize_message(message)))
    message['name'] = 'message'
    print(message == deserialize(serialize(message)))
