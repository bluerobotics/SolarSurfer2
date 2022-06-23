import os
import unittest

from main import system_information_filter

pwd = os.path.dirname(__file__)


class Tests(unittest.TestCase):
    def test_system_information_filter(self):
        import json

        with open(f"{pwd}/sample_data/sample_system_information_request.json") as json_file:
            before = json.load(json_file)
            after = system_information_filter(before)

            self.assertEqual("cpu" in before.keys(),
                             "cpu" in after.keys())
            self.assertEqual("process" in before.keys(),
                             "process" not in after.keys())
            self.assertEqual(before.get("cpu", None),
                             after.get("cpu", None))


if __name__ == '__main__':
    unittest.main()
