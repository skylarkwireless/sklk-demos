#!/usr/bin/python
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


import SoapySDR
import sys

if __name__ == '__main__':
     sdrs = SoapySDR.Device([dict(driver='iris',serial=s,timeout="1000000") for s in sys.argv[1:]])
     for sdr in sdrs:
         sensors = sdr.listSensors()
         print("%s:" % sdr.getHardwareInfo()['serial'])
         for s in sensors: 
             info = sdr.getSensorInfo(s)
             name, units = info.name, info.units
             print("    %s %s %s" % ((name + ":").ljust(23), str(sdr.readSensor(s)), units))
