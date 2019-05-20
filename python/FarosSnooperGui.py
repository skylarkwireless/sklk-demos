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

#TODO:  It seems very slow.  Also, it looks like list update deselects items.

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
        ncol = ndev*(ntime+1) // 3 if ndev*(ntime+1) < 13 else ndev*(ntime+1) // (4+ntime)
        nrows = (ntime+1)*np.ceil(ndev/ncol)
        
        self._axFreq = [None for d in range(ndev)]
        self._axTime = [None for d in range(ndev)]
        for d in range(ndev):
            self._axFreq[d] = fig.add_subplot(nrows, ncol, 1 + ncol*(1+ntime)*(d//ncol)+d%ncol) 
            self._axTime[d] = [fig.add_subplot(nrows, ncol, 1 + ncol*(1+ntime)*(d//ncol)+d%ncol + (i+1)*ncol) for i in range(ntime)]
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
        
        if device == 0: #todo: make draw a seperate thread
            self._figure.draw() 

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
            #time.sleep(0.1)


########################################################################
## Device selection dialog
########################################################################
from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QListWidget
from PyQt5.QtWidgets import QAbstractItemView
from PyQt5.QtWidgets import QGroupBox
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QRadioButton
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import pyqtSignal
#import SoapySDR
#import threading

DEVICE_POLL_TIME = 1.5 #seconds between poll

class DevicesSelectionDialog(QDialog):

    #signals
    devicesSelected = pyqtSignal(list)
    deviceListQueried = pyqtSignal(list)

    def __init__(self, channelSelect=False, timeSelect=False, settings=None, parent = None):
        QDialog.__init__(self, parent)
        self.setWindowTitle('Select a device...')
        self._layout = QVBoxLayout(self)
        self._timeSelect = timeSelect
        self._channelSelect = channelSelect

        configLayout = QHBoxLayout()
        self._layout.addLayout(configLayout)

        selectButton = QPushButton("Select Device(s)", self)
        selectButton.clicked.connect(self._handleSelectClicked) #lambda: self._handleListDoubleClicked(self._list.currentItem()))
        selectButton.setEnabled(False)

        self._list = QListWidget(self)
        self._list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._list.itemSelectionChanged.connect(lambda: selectButton.setEnabled(True))
        self._list.itemDoubleClicked.connect(self._handleListDoubleClicked)
        self._layout.addWidget(self._list)
        self._layout.addWidget(selectButton)

        if channelSelect:
            chanGroupBox = QGroupBox("Channel select", self)
            configLayout.addWidget(chanGroupBox)
            chanRadioLayout = QVBoxLayout(chanGroupBox)
            self._chOptions = ("AB", "A", "B")
            self._chanRadioButtons = [QRadioButton(chan, chanGroupBox) for chan in self._chOptions]
            for r in self._chanRadioButtons: chanRadioLayout.addWidget(r)

        if timeSelect:
            self._timeCheckBox = QCheckBox("Show time plots", self)
            configLayout.addWidget(self._timeCheckBox)
            self._timeCheckBox.setChecked(False)

        self.deviceListQueried.connect(self._handleDeviceListQueried)
        self._knownDevices = list()
        self._deviceHandles = []

        self._thread = None
        self._updateTimer = QTimer(self)
        self._updateTimer.setInterval(DEVICE_POLL_TIME*1000) #milliseconds
        self._updateTimer.timeout.connect(self._handleUpdateTimeout)
        self._handleUpdateTimeout() #initial update
        self._updateTimer.start()

        self._settings = settings
        if self._settings:
            if timeSelect: self._timeCheckBox.setChecked(self._settings.value("DevicesSelectionDialog/timeSelect", False, type=bool))
            if channelSelect:
                sel = self._settings.value("DevicesSelectionDialog/channelSelect", "AB")
                for i, opt in enumerate(self._chOptions): self._chanRadioButtons[i].setChecked(opt == sel)

        self.finished.connect(self._handleFinished)

    def devicesHandle(self): return self._deviceHandles

    def showTime(self): return self._timeCheckBox.isChecked()

    def channels(self):
        for i, r in enumerate(self._chanRadioButtons):
            if r.isChecked(): return self._chOptions[i]

    def _handleFinished(self, num):
        if self._settings:
            if self._timeSelect: self._settings.setValue("DevicesSelectionDialog/timeSelect", self._timeCheckBox.isChecked())
            if self._channelSelect: self._settings.setValue("DevicesSelectionDialog/channelSelect", self.channels())
            self._settings.sync()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _queryDeviceListThread(self):
        self.deviceListQueried.emit([dict(elem) for elem in sorted(SoapySDR.Device.enumerate(dict(driver="iris")), key=lambda x: x['serial'])])

    #private slots

    def _handleDeviceListQueried(self, devices):
        if devices == self._knownDevices: return
        #reload the widget
        self._list.clear()
        self._knownDevices = devices
        for device in self._knownDevices: self._list.addItem(device['label'])

    def _handleListDoubleClicked(self, item):
        row = self._list.row(item)
        args = [self._knownDevices[row]]
        self._deviceHandles = args
        self.devicesSelected.emit(args)
        self.accept()

    def _handleSelectClicked(self):
        rows = self._list.selectedItems()
        args = [self._knownDevices[self._list.row(row)] for row in rows]
        self._deviceHandles = args
        self.devicesSelected.emit(args)
        self.accept()

    def _handleUpdateTimeout(self):
        if self._thread is not None and self._thread.isAlive(): return
        self._thread = threading.Thread(target=self._queryDeviceListThread)
        self._thread.start()


########################################################################
## Invoke the application
########################################################################
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings
#from sklk_widgets import DevicesSelectionDialog #todo, make seperate file
import argparse
import sys

if __name__ == '__main__':
    app = QApplication(sys.argv)

    parser = argparse.ArgumentParser()
    parser.add_argument("--args", help="Device arguments (or none for selection dialog)")
    parser.add_argument("--time", help="Display time domain plots", action='store_true')
    parser.add_argument("--chans", help="Which channels A, B, or AB", default="AB")
    args = parser.parse_args()
    handles = args.args
    showTime = args.time
    chans = args.chans

    #load previous settings
    settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Skylark", "FarosSnooperGUI")

    handles = []
    #pick a device to open
    if not handles:
        dialog = DevicesSelectionDialog(channelSelect=True, timeSelect=True, settings=settings)
        dialog.exec()
        handles = dialog.devicesHandle()
        showTime = dialog.showTime()
        chans = dialog.channels()
    #else:
    #    handles = SoapySDR.Device.enumerate(handles) #todo
    if len(handles) < 1:
        print('No device selected!')
        sys.exit(-1)

    w = MainWindow(handles=handles, showTime=showTime, chans=chans, settings=settings)
    w.show()
    sys.exit(app.exec_())
