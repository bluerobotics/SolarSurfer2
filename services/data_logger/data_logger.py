#! /usr/bin/env python3

from datetime import datetime, timezone, timedelta
from logging import exception


class DataLogger(object):
    def __init__(self, header: dict, newfile_interval: timedelta, output_dir: str,
                 log_with_timestamp=True, log_timestamp_format='%Y-%m-%dT%H%M%S.%f%z',
                 filename_datetime_format='%Y-%m-%d_%H%M%S',
                 filename_prefix: str = 'log_',
                 csv_separator: str = ',',
                 file_encoding='utf-8'):
        self.header = header
        self.file_creation_interval = newfile_interval
        self.output = output_dir

        self._log_with_timestamp = log_with_timestamp
        self._log_timestamp_format = log_timestamp_format
        self._filename_datetime_format = filename_datetime_format
        self._filename_prefix = filename_prefix
        self._separator = csv_separator
        self._encoding = file_encoding

        self._filename = None
        self._file = None
        self._file_creation_time = None

    def __enter__(self):
        self._create_new_file()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self._file.close()

    def _create_new_file(self):
        def _write_header_to_file(self):
            header = self._separator.join(self.header) + '\n'

            if self._log_with_timestamp:
                header = self._separator.join(
                    ['datalogger_datetime', 'datalogger_timestamp']) + self._separator + header

            self._file.write(header)

        def _generate_new_filename_string(self):
            filename_dir = self.output
            filename_prefix = self._filename_prefix
            filename_date = datetime.now(
                tz=timezone.utc).strftime(self._filename_datetime_format)
            self._filename = f"{filename_dir}/{filename_prefix}{filename_date}.csv"

        _generate_new_filename_string(self)
        self._file_creation_time = datetime.now(tz=timezone.utc)
        try:
            self._file = open(self._filename, mode='x',
                              encoding=self._encoding)
        except FileExistsError:
            self._file = open(self._filename, mode='a',
                              encoding=self._encoding)
            return
        _write_header_to_file(self)  # only writes header if it is a new file

    def new_file(self):
        """ Closes the current log file and continue to log into a new one. """
        self._file.close()
        self._create_new_file()

    def log(self, data: dict):
        """ Logs the given data to the current log file. """

        if not isinstance(data, dict):
            return

        now = datetime.now(tz=timezone.utc)
        if (now - self._file_creation_time) >= self.file_creation_interval:
            self.new_file()

        line = self._separator.join(
            [f"\"{data[key]}\"" for key in data.keys()]) + '\n'

        if self._log_with_timestamp:
            datetimestr = now.strftime(self._log_timestamp_format)
            timestampstr = str(now.timestamp())
            line = self._separator.join(
                ['"' + datetimestr + '"', '"' + timestampstr + '"']) + self._separator + line

        self._file.write(line)


def _example():
    from dataclasses import dataclass
    import time
    from datetime import datetime, timedelta

    @dataclass(init=False)
    class Data:
        # Just a mock data
        timestamp: str
        some_string: str
        some_float: float
        some_integer: int
        some_non_ascci: str

        def __init__(self):
            import uuid
            import random
            self.timestamp = datetime.now(tz=timezone.utc)
            self.some_string = str(uuid.uuid4().hex)
            self.some_float = float(random.uniform(-1, 1))
            self.some_integer = int(random.randint(0, 255))
            self.some_non_ascci = str(
                ','.join([(chr(random.randint(8000, 9000))) for _ in range(32)]))

    def get_data() -> dict:
        return Data().__dict__

    interval = timedelta(seconds=10)
    keys = list(get_data().keys())

    with DataLogger(keys, newfile_interval=interval, output_dir='.', log_with_timestamp=True, filename_prefix='solarsurfer2_log_') as logger:
        i = 0
        while(i < 15):
            data = get_data()
            logger.log(data)

            time.sleep(1)
            i += 1


if __name__ == "__main__":
    _example()
