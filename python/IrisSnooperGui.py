#!/usr/bin/python3
#
#	Passive monitor of Rx Channels with live wave plot and FFT viewer.
#	This application has no controls by design, the iris must be setup
#	by another script, demo, 3rd party application, etc.
#
#	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#	INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
#	PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
#	FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#	OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#	DEALINGS IN THE SOFTWARE.
#
#	(c) info@skylarkwireless.com 2018

########################################################################
## Main window
########################################################################
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWidgets import QSplashScreen
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

class MainWindow(QMainWindow):
    def __init__(self, settings, parent = None, **kwargs):
        QMainWindow.__init__(self, parent)
        self._splash = QSplashScreen(self, QPixmap('data/logo.tif'))
        self._splash.show()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Iris Snooper GUI - %s"%kwargs['handle']['label'])
        self.setMinimumSize(800, 600)
        self._settings = settings

        #load previous settings
        print("Loading %s"%self._settings.fileName())
        if self._settings.contains("MainWindow/geometry"): self.restoreGeometry(self._settings.value("MainWindow/geometry"))
        if self._settings.contains("MainWindow/state"): self.restoreState(self._settings.value("MainWindow/state"))

        #start the window
        self._plotters = PlotterWidgets(parent=self, **kwargs)
        self.setCentralWidget(self._plotters)

        #load complete
        self._splash.finish(self)

    def closeEvent(self, event):

        #stash settings
        self._settings.setValue("MainWindow/geometry", self.saveGeometry())
        self._settings.setValue("MainWindow/state", self.saveState())

        self._plotters.closeEvent(event)

########################################################################
## Display widget
########################################################################
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtCore import pyqtSignal
from sklk_widgets import LogPowerFFT
import threading
import numpy as np
import time
import SoapySDR
from SoapySDR import *

import matplotlib
try: matplotlib.use('Qt5Agg')
except Exception as ex:
    print("Failed to use qt5 backend -- maybe its not installed")
    print("On ubuntu trusty, install python3-matplotlib from ppa:takluyver/matplotlib-daily")
    raise ex
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class PlotterWidgets(QWidget):

    snooperComplete = pyqtSignal(list)

    def __init__(self, handle, showTime, chans, parent = None, width=5, height=4, dpi=100):
        QWidget.__init__(self, parent)
        self._layout = QVBoxLayout(self)
        self._thread = None

        self._handle = handle
        self._chans = chans
        self._showTime = showTime
        self._sampleRate = 1e6
        self._centerFreq = 1e9
        self._device = SoapySDR.Device(self._handle)

        fig = Figure(figsize=(width, height), dpi=dpi)
        ntime = len(chans) if showTime else 0
        nrows = ntime+1
        self._axFreq = fig.add_subplot(nrows, 1, 1)
        self._axTime = [fig.add_subplot(nrows, 1, i+2) for i in range(ntime)]
        self._figure = FigureCanvas(fig)
        self._figure.setParent(self)
        self._figure.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._figure.updateGeometry()
        self._layout.addWidget(self._figure)

        #start background thread
        self._running = True
        self.snooperComplete.connect(self._handleSnooperComplete)
        self._thread = threading.Thread(target=self._snoopChannels)
        self._mutex = threading.Lock()
        self._dataInFlight = 0
        self._thread.start()

    def closeEvent(self, event):
        if self._thread is not None:
            self._running = False
            self._thread.join()
            self._thread = None

    def _handleSnooperComplete(self, sampleses):

        #only handle if this is the last samples enqueued
        with self._mutex:
            self._dataInFlight -= 1
            if self._dataInFlight: return

        self._axFreq.clear()
        rxRate = self._sampleRate
        for i, samps in enumerate(sampleses):
            ps = LogPowerFFT(samps)
            color = "bg"[i]
            self._axFreq.plot(np.arange(-rxRate/2/1e6, rxRate/2/1e6, rxRate/len(ps)/1e6)[:len(ps)], ps, color)
        self._axFreq.set_title('Center frequency %g MHz, Sample rate %g Msps'%(self._centerFreq/1e6, rxRate/1e6), fontsize=10)
        self._axFreq.set_ylabel('Power (dBfs)', fontsize=10)
        self._axFreq.set_ylim(top=0, bottom=-120)
        self._axFreq.grid(True)

        if self._showTime:
            WAVE_SAMPS = 1024
            timeScale = np.arange(0, WAVE_SAMPS/(rxRate*1e-3), 1/(rxRate*1e-3))
            for ch, ax in enumerate(self._axTime):
                if ax is None: continue
                ax.clear()
                samps = sampleses[ch]
                ax.plot(timeScale, np.real(samps[:WAVE_SAMPS]))
                ax.plot(timeScale, np.imag(samps[:WAVE_SAMPS]))
                ax.set_ylabel('Amplitude Ch%s (units)'%self._chans[ch], fontsize=10)
                ax.set_ylim(top=-1, bottom=1)
                ax.grid(True)

        if self._axTime: self._axTime[-1].set_xlabel('Time (ms)', fontsize=10)

        self._figure.draw()

    def _snoopChannels(self):
        nextUpdate = time.time()
        while self._running:
            if self._device is None:
                print('Attempting to re-establish connection...')
                try: self._device = SoapySDR.Device(self._handle)
                except Exception as ex:
                    print('Failed to connect %s, retrying in several seconds...'%str(ex))
                    time.sleep(3)
                    continue
            if nextUpdate < time.time():
                self._sampleRate = self._device.getSampleRate(SOAPY_SDR_RX, 0)
                self._centerFreq = self._device.getFrequency(SOAPY_SDR_RX, 0)
                nextUpdate = time.time() + 1.5
            sampleses = list()
            for ch in [0, 1]:
                if "AB"[ch] not in self._chans: continue
                try: samps = self._device.readRegisters('RX_SNOOPER', ch, 1024)
                except Exception as ex:
                    print('readRegisters error %s, attempting to close connection...'%str(ex))
                    self._device = None
                    break
                samps = np.array([complex(float(np.int16(s & 0xffff)), float(np.int16(s >> 16))) for s in samps])/float(1 << 15)
                sampleses.append(samps)
            if self._device is None: continue
            with self._mutex: self._dataInFlight += 1
            self.snooperComplete.emit(sampleses)
            time.sleep(0.1)

########################################################################
## Invoke the application
########################################################################
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings
from sklk_widgets import DeviceSelectionDialog
import argparse
import sys

if __name__ == '__main__':
    app = QApplication(sys.argv)

    parser = argparse.ArgumentParser()
    parser.add_argument("--args", help="Device arguments (or none for selection dialog)")
    parser.add_argument("--time", help="Display time domain plots", action='store_true')
    parser.add_argument("--chans", help="Which channels A, B, or AB", default="AB")
    args = parser.parse_args()
    handle = args.args
    showTime = args.time
    chans = args.chans

    #load previous settings
    settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Skylark", "IrisSnooperGUI")

    #pick a device to open
    if not handle:
        dialog = DeviceSelectionDialog(channelSelect=True, timeSelect=True, settings=settings)
        dialog.exec()
        handle = dialog.deviceHandle()
        showTime = dialog.showTime()
        chans = dialog.channels()
    else:
        handle = SoapySDR.Device.enumerate(handle)[0]
    if not handle:
        print('No device selected!')
        exit(-1)

    w = MainWindow(handle=handle, showTime=showTime, chans=chans, settings=settings)
    w.show()
    sys.exit(app.exec_())
