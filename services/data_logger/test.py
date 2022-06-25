#! /usr/bin/env python3

import os
import unittest
from unittest import mock

from main import flatten_dict, data_gathering, system_information_filter
import json

pwd = os.path.dirname(__file__)


def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, data, status_code):
            self.text = data
            self.status_code = status_code

        def json(self):
            return json.load(self.text)

    if args[0] == 'http://127.0.0.1:6030/system':
        return MockResponse(open(f"{pwd}/sample_data/sample_system_information_request.json"), 200)
    elif args[0] == 'http://127.0.0.1:9991/data':
        return MockResponse(open(f"{pwd}/sample_data/sample_victron_energy_mppt_request.json"), 200)
    elif args[0] == 'http://127.0.0.1:9990/data':
        return MockResponse(open(f"{pwd}/sample_data/sample_weatherstation_request.json"), 200)
    elif args[0] == 'http://127.0.0.1:6040/mavlink/vehicles/1/components/1/messages':
        return MockResponse(open(f"{pwd}/sample_data/sample_mavlink_request.json"), 200)

    return MockResponse(None, 404)


class Tests(unittest.TestCase):

    def test_system_information_filter(self):
        with open(f"{pwd}/sample_data/sample_system_information_request.json") as json_file:
            before = json.load(json_file)
            after = system_information_filter(before)

            self.assertEqual("cpu" in before.keys(),
                             "cpu" in after.keys())
            self.assertEqual("process" in before.keys(),
                             "process" not in after.keys())
            self.assertEqual(before.get("cpu", None),
                             after.get("cpu", None))

    def test_flatten_system_information(self):
        with open(f"{pwd}/sample_data/sample_system_information_request.json") as json_file:
            before = system_information_filter(json.load(json_file))
            after = flatten_dict(before)

            self.assertEqual(before['cpu'][0]['name'],
                             after['cpu.0.name'])

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_data_gathering_system_information(self, mock_get):
        data = data_gathering(service_name="System Information", url="http://127.0.0.1:6030/system",
                                           timeout=5, filter=system_information_filter)

        self.assertEqual(data['cpu.0.name'], 'cpu0')


if __name__ == '__main__':
    unittest.main()
