#!/usr/bin/python3
#
#    Read sensors from provided Iris serials.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#    INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
#    PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
#    FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#    OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
#    (c) 2018 info@skylarkwireless.com


import sys
import site
import os
import SoapySDR
import argparse
import traceback
import json
import yaml

STDERR_FILENO = 2

filepath = os.path.dirname(os.path.abspath(__file__))
sitepath = os.path.abspath(os.path.join(filepath, '..'))
site.addsitedir(sitepath)

def suppress_stderr(func, *args, **kwargs):
    # Close stderr
    fd = os.dup(STDERR_FILENO)
    f = open(os.devnull, 'w')
    os.dup2(f.fileno(), STDERR_FILENO)
    try:
        retval = func(*args, **kwargs)
    finally:
        os.dup2(fd, STDERR_FILENO)
    return retval


class TemperatureChart(object):
    '''
        Class to display the temperatures of iris nodes in a table format
    '''
    sensor_names = [
        'ZYNQ_TEMP',
        'FE_RX_TEMP',
        'FE_TX_TEMP',
        'LMS7_TEMP'
    ]
    MAX_BARS = 10

    def __init__(self, args):
        self.serials = args.serials
        self.min_temp = {}
        self.max_temp = {}
        self.min_display_temp = {}
        self.max_display_temp = {}
        self.setDisplyRanges(args)

    def setDisplyRanges(self, args):
        '''
        Set the display ranges of each temperature sensor.  If no bounds are set, dynamic
        ranges will be used.

        :param args: Namespace containing temperature ranges for each sensor.  The
                     format for each variable will be:
                        args.min_<sensor lower case>
                        args.max_<sensor lower case>
        :return: None
        '''
        for range_name in ['min', 'max']:
            d = {}
            for sensor_name in self.sensor_names:
                default_value = getattr(args, self.varNameFromSensor(range_name, sensor_name))
                if default_value is None:
                    default_value = getattr(args, self.varNameFromSensor(range_name))
                if default_value is not None :
                    d.setdefault(sensor_name, default_value)
            setattr(self, range_name + '_display_temp', d)

    @classmethod
    def argNameFromSensor(self, range_str, sensor_name):
        'Returns the opptions parameter name for a given sensor.'
        return '--{}-{}'.format(range_str, sensor_name.lower().replace('_', '-') if sensor_name is not None else "temp")

    @classmethod
    def varNameFromSensor(self, range_str, sensor_name=None):
        'Returns the name of a given sensor in the options namespace.'
        return '{}_{}'.format(range_str, sensor_name.lower() if sensor_name is not None else "temp")

    def getSensorsFromSdr(self, serial, sdr) -> dict:
        '''
        Reads each sensor and updates the dynamic range

        :param serial: the identifier for the node
        :param sdr: the iris node
        :return: a dictionary containing sensor information for the iris
        '''
        try:
            sensors = sdr.listSensors() if sdr else []
        except RuntimeError:
            sensors = []

        sensor_table = {
            'serial': serial,
            'idx': self.serials.index(serial)+1
        }

        for sensor_name in sensors:
            try:
                value = json.loads(sdr.readSensor(sensor_name))
            except RuntimeError:
                continue
            if value == 0:
                # Ignore any values of 0.  They are not being reported correctly
                continue
            sensor_table[sensor_name] = value
            self.min_temp[sensor_name] = min(self.min_temp.setdefault(sensor_name, value), value)
            self.max_temp[sensor_name] = max(self.max_temp.setdefault(sensor_name, value), value)

        return sensor_table

    def convertSensorToBar(self, sensor_name, sensor):
        'Uses the dynamic and static ranges to calculate a bar graph'
        _min_temp = min(self.min_display_temp.get(sensor_name, self.min_temp[sensor_name]), self.min_temp[sensor_name])
        _max_temp = max(self.max_display_temp.get(sensor_name, self.max_temp[sensor_name]), self.max_temp[sensor_name])
        temp = int((sensor - _min_temp) / max(_max_temp - _min_temp, 1) * self.MAX_BARS + 1)
        return '|' * temp

    def convertSensorToStr(self, sensor_name, sensor):
        'Converts a sensor to a display string'
        return "{:4.1f} {}".format(sensor, self.convertSensorToBar(sensor_name, sensor)) if sensor is not None else ""

    def getSdrs(self):
        'Get a list of devices based on serials'
        sdrs = {}
        for serial in self.serials:
            try:
                sdrs[serial] = SoapySDR.Device(dict(driver='iris', serial=serial, timeout="1000000"))
            except RuntimeError:
                sdrs[serial] = None
        return sdrs

    def _getSensors(self) -> dict:
        sdrs = self.getSdrs()
        return dict([serial, self.getSensorsFromSdr(serial, sdr)] for serial, sdr in sdrs.items())

    def getSensors(self) -> dict:
        'Returns a dictionary of iris node sensors'
        return suppress_stderr(self._getSensors)

    def getFormatStr(self):
        'Return the format string for all sensors for a single node'
        field_size = 7 + self.MAX_BARS
        return "{:3}  {:<11}" + (" {:<%s}" % field_size) * len(self.sensor_names)

    def printRow(self, row):
        'Display the sensors for a single iris'
        format_str = self.getFormatStr()
        fields = []

        for sensor_name in self.sensor_names:
            sensor = row.get(sensor_name, None)
            fields.append(self.convertSensorToStr(sensor_name, sensor))

        print(format_str.format(row['idx'], row['serial'], *fields))

    def printChart(self, sensors_by_node):
        'Display all iris nodes'
        format_str = self.getFormatStr()
        print(format_str.format('idx', 'Serial', *self.sensor_names))

        range_temp = {}
        for sensor_name in self.sensor_names:
            if sensor_name in self.max_temp and sensor_name in self.min_temp:
                range_temp[sensor_name] = "{:4.1f}".format(self.max_temp[sensor_name] - self.min_temp[sensor_name])
            else:
                range_temp[sensor_name] = ""

        for serial in self.serials:
            self.printRow(sensors_by_node[serial])

        print()
        print (format_str.format("", "Range", *[range_temp[sensor_name] for sensor_name in self.sensor_names]))

    @classmethod
    def get_config_keys(cls):
        config_key_search = ['serials', ]
        for range_name in ['min', 'max']:
            for sensor_name in cls.sensor_names:
                config_key_search.append(cls.varNameFromSensor(range_name, sensor_name))
        return config_key_search

    @classmethod
    def set_args_from_config (cls, args):
        if args.config is None or not os.path.exists(args.config):
            return

        with open(args.config, "r+") as fptr:
            config = yaml.load(fptr, Loader=yaml.FullLoader)

        for key in cls.get_config_keys():
            value = config.get(key, None)
            if type(value) is list:
                getattr(args, key).extend([x for x in value if type(x)==str])
            elif type(value) in (str, int, float,):
                setattr(args, key, value)

    @classmethod
    def run(cls, args):
        chart = cls(args)
        rows = chart.getSensors()
        chart.printChart(rows)

    @classmethod
    def main(cls, argv):
        parser = argparse.ArgumentParser()
        parser.add_argument('--debug', help="turn on debug messages", action="store_true")
        parser.add_argument('--pdb', help="Enter debugger on failure", action="store_true")

        for range_str in ['min', 'max']:
            name = range_str + 'imum'
            parser.add_argument('--{}-temp'.format(range_str), help="Set a {} temperature".format(name), action="store", default=None, type=float, metavar='TEMP')
            for sensor_name in cls.sensor_names:
                component = " ".join(sensor_name.split('_')[:-1])
                argname = cls.argNameFromSensor(range_str, sensor_name)
                parser.add_argument(argname, help="Set a {} {} temperature".format(name, component), action="store", default=None, type=float, metavar='TEMP')

        parser.add_argument('--config', help="Specify a configuration file.  The following keys are supported: {}".
                            format(cls.get_config_keys()), action="store", default=None)
        parser.add_argument('serials', nargs='*', help="List of serial numbers", default=[])
        args = parser.parse_args(argv)
        cls.set_args_from_config(args)
        if (not args.serials):
            print("Must specify a serial or config file with serials")
            return -1

        try:
            cls.run(args)
        except Exception as e:
            if args.pdb:
                traceback.print_exc()
                import pdb
                pdb.post_mortem()
            else:
                raise e

if __name__ == "__main__":
    sys.exit(TemperatureChart.main(sys.argv[1:] ))
