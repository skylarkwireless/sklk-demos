#!/usr/bin/python3
#
#	Passive monitor of Rx Channels with live wave plot and FFT viewer.
#	This application has no controls by design, the irises must be setup
#	by another script, demo, 3rd party application, etc.
#
#	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#	INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
#	PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
#	FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#	OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#	DEALINGS IN THE SOFTWARE.
#
#	(c) info@skylarkwireless.com 2019

#TODO:  It looks like list update deselects items (this happens when the list changes, e.g., a new iris was discovered.)

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
        self.setWindowTitle("Faros Snooper GUI") # - %s"%kwargs['handles']['label'])
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

    snooperComplete = pyqtSignal(list,int)

    def __init__(self, handles, showTime, chans, parent = None, width=10, height=8, dpi=100):
        QWidget.__init__(self, parent)
        self._layout = QVBoxLayout(self)
        self._thread = None

        self._handles = handles
        self._chans = chans
        self._showTime = showTime
        self._sampleRate = [1e6 for handle in handles]
        self._centerFreq = [1e9 for handle in handles]
        self._rxGain = [[0,0] for handle in handles]
        self._txGain = [[0,0] for handle in handles]
        self._devices = [SoapySDR.Device(handle) for handle in handles]

        #figs = [Figure(figsize=(width, height), dpi=dpi) for d in self._devices]
        fig = Figure(figsize=(width, height), dpi=dpi)
        ndev = len(self._devices)
        ntime = len(chans) if showTime else 0
        ncols = np.ceil(ndev*(ntime+1) / 3) if ndev*(ntime+1) < 12 else ndev*(ntime+1) // 4
        nrows = (ntime+1)*np.ceil(ndev/ncols)

        self._axFreq = [None for d in range(ndev)]
        self._axTime = [None for d in range(ndev)]
        for d in range(ndev):
            self._axFreq[d] = fig.add_subplot(nrows, ncols, 1 + ncols*(1+ntime)*(d//ncols)+d%ncols) 
            self._axTime[d] = [fig.add_subplot(nrows, ncols, 1 + ncols*(1+ntime)*(d//ncols)+d%ncols + (i+1)*ncols) for i in range(ntime)]
        fig.tight_layout()
        self._figure = FigureCanvas(fig)
        self._figure.setParent(self)
        self._figure.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._figure.updateGeometry()
        self._layout.addWidget(self._figure)

        #start background thread
        self._running = True
        self.snooperComplete.connect(self._handleSnooperComplete)
        self._threads = [threading.Thread(target=self._snoopChannels,args=[d]) for d in range(ndev)]
        self._mutex = [threading.Lock() for d in range(ndev)]
        self._drawMutex = threading.Lock()
        self._lastDraw = time.time()
        self._dataInFlight = [0 for d in range(ndev)]
        for d in range(ndev): self._threads[d].start()

    def closeEvent(self, event):
        self._running = False
        time.sleep(0.1)
        for d in range(len(self._devices)):
            if self._threads[d] is not None:
                self._threads[d].join()
                self._threads[d] = None

    def _handleSnooperComplete(self, sampleses, device, fontsize=7):

        #only handle if this is the last samples enqueued
        with self._mutex[device]:
            self._dataInFlight[device] -= 1
            if self._dataInFlight[device]: return

        self._axFreq[device].clear()
        rxRate = self._sampleRate[device]
        for i, samps in enumerate(sampleses):
            ps = LogPowerFFT(samps)
            color = "bg"[i]
            self._axFreq[device].plot(np.arange(-rxRate/2/1e6, rxRate/2/1e6, rxRate/len(ps)/1e6)[:len(ps)], ps, color)
        self._axFreq[device].set_title('%s Center frequency %g MHz, Sample rate %g Msps, Tx Gain %s, Rx Gain %s' % (self._handles[device]['label'],self._centerFreq[device]/1e6, rxRate/1e6, str(self._txGain[device]), str(self._rxGain[device])), fontsize=fontsize) #todo
        self._axFreq[device].set_ylabel('Power (dBfs)', fontsize=fontsize)
        self._axFreq[device].set_ylim(top=0, bottom=-120)
        self._axFreq[device].grid(True)
        self._axFreq[device].tick_params(labelsize=fontsize)

        if self._showTime:
            WAVE_SAMPS = 1024
            timeScale = np.arange(0, WAVE_SAMPS/(rxRate*1e-3), 1/(rxRate*1e-3))
            for ch, ax in enumerate(self._axTime[device]):
                if ax is None: continue
                ax.clear()
                samps = sampleses[ch]
                ax.plot(timeScale, np.real(samps[:WAVE_SAMPS]))
                ax.plot(timeScale, np.imag(samps[:WAVE_SAMPS]))
                ax.tick_params(labelsize=fontsize)
                ax.set_ylabel('Amplitude Ch%s (units)'%self._chans[ch], fontsize=fontsize)
                ax.set_ylim(top=-1, bottom=1)
                ax.grid(True)

        if self._axTime[device]: self._axTime[device][-1].set_xlabel('Time (ms)', fontsize=fontsize)

        with self._drawMutex:
            if time.time() - self._lastDraw > .05:
                self._figure.draw()
                self._lastDraw = time.time()

    def _snoopChannels(self, device):
        dev = self._devices[device]
        nextUpdate = time.time()
        while self._running:
            if dev is None:
                print('Attempting to re-establish connection...')
                try: dev = SoapySDR.Device(self._handles[device])
                except Exception as ex:
                    print('Failed to connect %s, retrying in several seconds...'%str(ex))
                    time.sleep(3)
                    continue
            if nextUpdate < time.time():
                self._sampleRate[device] = dev.getSampleRate(SOAPY_SDR_RX, 0)
                self._centerFreq[device] = dev.getFrequency(SOAPY_SDR_RX, 0)
                self._rxGain[device] = [dev.getGain(SOAPY_SDR_RX, chan) for chan in range(2)]
                self._txGain[device] = [dev.getGain(SOAPY_SDR_TX, chan) for chan in range(2)]
                nextUpdate = time.time() + 1.5
            sampleses = list()
            for ch in [0, 1]:
                if "AB"[ch] not in self._chans: continue
                try: samps = dev.readRegisters('RX_SNOOPER', ch, 1024)
                except Exception as ex:
                    print('readRegisters error %s, attempting to close connection...'%str(ex))
                    self._device = None
                    break
                samps = np.array([complex(float(np.int16(s & 0xffff)), float(np.int16(s >> 16))) for s in samps])/float(1 << 15)
                sampleses.append(samps)
            if dev is None: continue
            with self._mutex[device]: self._dataInFlight[device] += 1
            self.snooperComplete.emit(sampleses, device)
            while self._dataInFlight[device] and self._running:
                time.sleep(.05)

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
    parser.add_argument("--serials", type=str, dest="serials", help="SDR Serial Numbers, e.g. 00002 00004", default=None)
    args = parser.parse_args()
    showTime = args.time
    chans = args.chans

    #load previous settings
    settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Skylark", "FarosSnooperGUI")

    handles = []
    #pick a device to open
    if args.serials is None:
        dialog = DeviceSelectionDialog(channelSelect=True, timeSelect=True, settings=settings, multiDevice=True, FEfilter=True)
        dialog.exec()
        handles = dialog.devicesHandle()
        showTime = dialog.showTime()
        chans = dialog.channels()
    else:
        handles = [dict(serial=s,label=s) for s in args.serials.split()]
    if len(handles) < 1:
        print('No device selected!')
        sys.exit(-1)

    w = MainWindow(handles=handles, showTime=showTime, chans=chans, settings=settings)
    w.show()
    sys.exit(app.exec_())
