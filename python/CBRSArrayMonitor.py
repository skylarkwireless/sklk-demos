#!/usr/bin/python3
#
#    Monitor GUI for an array of CBRS boards to watch power levels
#    and temperature across time along with a user-controlled
#    value for frequency, gain, and others.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#    INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
#    PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
#    FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#    OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
#    (c) info@skylarkwireless.com 2018

########################################################################
## Main window
########################################################################
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWidgets import QSplashScreen
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

class MainWindow(QMainWindow):
    def __init__(self, irises, settings, parent=None, chan=None, **kwargs):
        QMainWindow.__init__(self, parent)
        self._splash = QSplashScreen(self, QPixmap('data/logo.tif'))
        self._splash.show()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("CBRS Array Monitor")
        self.setMinimumSize(800, 600)
        self._settings = settings

        self.addDockWidget(Qt.TopDockWidgetArea, TopLevelControlPanel(irises=irises, settings=settings, parent=self))

        #start the window
        self.setCentralWidget(MainStatusWindow(irises=irises, parent=self, chan=chan))

        #load previous settings
        print("Loading %s"%self._settings.fileName())
        if self._settings.contains("MainWindow/geometry"): self.restoreGeometry(self._settings.value("MainWindow/geometry"))
        if self._settings.contains("MainWindow/state"): self.restoreState(self._settings.value("MainWindow/state"))

        #load complete
        self._splash.finish(self)

    def closeEvent(self, event):

        #stash settings
        self._settings.setValue("MainWindow/geometry", self.saveGeometry())
        self._settings.setValue("MainWindow/state", self.saveState())

########################################################################
## Status window
########################################################################
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QFormLayout
from PyQt5.QtWidgets import QHBoxLayout

class MainStatusWindow(QWidget):
    def __init__(self, irises, parent=None, chan=None):
        QWidget.__init__(self, parent)
        hbox = QHBoxLayout(self)
        for i, iris in enumerate(irises):
            if i%8 == 0:
                form = QFormLayout()
                hbox.addLayout(form)
            serial = iris.getHardwareInfo()['serial']
            statusDisplay = SingleIrisStatus(iris, self, chan)
            form.addRow(serial, statusDisplay)

########################################################################
## Single status display
########################################################################
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QProgressBar
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import pyqtSignal
import numpy as np

class SingleIrisStatus(QWidget):
    parserComplete = pyqtSignal(dict)

    def __init__(self, iris, parent=None, chan=None):
        self.chan = [0,1] if chan is None else [chan]
        QWidget.__init__(self, parent)
        self._iris = iris
        layout = QHBoxLayout(self)
        vbox = QVBoxLayout()
        layout.addLayout(vbox)
        self._progressBars = list()
        self._errorMessages = list()
        for ch in [0,1]:
            pbar = QProgressBar(self)
            vbox.addWidget(pbar)
            pbar.setRange(-100, 0)
            pbar.setFormat("Ch%s %%v dBfs"%("AB"[ch]))
            pbar.setValue(-100)
            self._progressBars.append(pbar)
            txt = QLabel(self)
            vbox.addWidget(txt)
            self._errorMessages.append(txt)
        self._txt = QLabel(self)
        layout.addWidget(self._txt)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._handleTimeout)
        self._timer.start()

        self.parserComplete.connect(self._handleParserComplete)

    def _handleParserComplete(self, results):
        self._thread.join()
        self._thread = None
        for ch in self.chan:
            self._progressBars[ch].setValue(results[ch]['pwr'])
            if 'err' in results[ch]:
                self._errorMessages[ch].setText('<font color="red">%s</font>'%(results[ch]['err']))
            else:
                self._errorMessages[ch].setText('    ')
        self._txt.setText('%g C'%results['temp'])
        #print('_handleParserComplete %s'%str(results))
        self._timer.start()

    def _handleTimeout(self):
        self._thread = threading.Thread(target=self._workThread)
        self._thread.start()

    def _workThread(self):
        results = dict()
        for ch in self.chan:
            samps = self._iris.readRegisters('RX_SNOOPER', ch, 1024)
            samps = np.array([complex(float(np.int16(s & 0xffff)), float(np.int16(s >> 16))) for s in samps])/float(1 << 15)
            result = toneGood(samps)
            results[ch] = result
        results['temp'] = float(self._iris.readSensor('LMS7_TEMP'))
        self.parserComplete.emit(results)

########################################################################
## tone parsing logic
########################################################################
from sklk_widgets import LogPowerFFT

SAMP_RATE = 10e6
TONE_FS = 1e6
FILT_BW = 30e6

def toneGood(samps, tone=TONE_FS, fs=SAMP_RATE, low_thresh=0.01, high_thresh=0.7, spur_threshes=[10,12,15,20], ignore_dc=False, suppress=100e3):
    """
    Check to see if a tone is received as expected, e.g., for testing boards by
    transmitting a tone and receiving it in loopback mode.

    Rejects if receive power is too low or too high, or if the next n spurious tones are higher than spur_threshes.
    Suppress DC and carriers adjacent to tone, according to ignore_dc and suppress.
    """
    result = dict(ret=False)

    ps = LogPowerFFT(samps)
    dc_bin = len(samps)//2
    tone_bin = dc_bin + int(np.round(len(samps)*tone/fs)) #todo: check
    result['pwr'] = ps[tone_bin]

    avg = np.mean(np.abs(samps))
    result['avg'] = avg
    if avg < low_thresh:
        result['err'] = "Tone power too low."
        return result
    if avg > high_thresh or np.amax(np.abs(samps)) > 1.0:
        result['err'] = "Tone power too high -- likely clipping."
        return result

    if np.argmax(ps) != tone_bin:
        result['err'] = "Tone is not highest signal."
        return result

    if(ignore_dc): #ignore DC
        ps[dc_bin] = np.min(ps) #-100

    n_suppress = int(np.round(len(samps)*suppress/fs))
    #print(n_suppress, np.min(ps),tone_bin)
    ps[tone_bin+1:tone_bin+1+n_suppress] = np.min(ps)
    ps[tone_bin-n_suppress:tone_bin] = np.min(ps)

    s_power = np.sort(ps)
    for i,thresh in enumerate(spur_threshes):
        if  s_power[-i-2] > ps[tone_bin] - thresh:
            result['err'] = 'Spur %d is too high!  It is %f, tone is %f' % (i+1, s_power[-i-2], ps[tone_bin])
            return result

    result['ret'] = True
    return result

def setupIris(iris, chan):
    for ch in [0, 1]:
        iris.setSampleRate(SOAPY_SDR_RX, ch, SAMP_RATE)
        iris.setSampleRate(SOAPY_SDR_TX, ch, SAMP_RATE)
        iris.setBandwidth(SOAPY_SDR_RX, ch, FILT_BW)
        iris.setBandwidth(SOAPY_SDR_TX, ch, FILT_BW)
        iris.writeSetting(SOAPY_SDR_TX, ch, 'TSP_TSG_CONST', str(1 << 12))
        iris.setFrequency(SOAPY_SDR_TX, ch, 'BB', TONE_FS)
    iris.writeSetting('FE_ENABLE_CAL_PATH', 'true')
    if chan is not None:
        iris.writeSetting(SOAPY_SDR_TX, int(not chan), "ENABLE_CHANNEL","false")
        iris.writeSetting(SOAPY_SDR_RX, int(not chan), "ENABLE_CHANNEL","false")

########################################################################
## Top level control panel
########################################################################
from PyQt5.QtWidgets import QDockWidget
from PyQt5.QtWidgets import QDoubleSpinBox
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QFormLayout
from PyQt5.QtWidgets import QGroupBox
from PyQt5.QtWidgets import QWidget
from sklk_widgets import FreqEntryWidget
from SoapySDR import *
import functools
import threading

class TopLevelControlPanel(QDockWidget):
    def __init__(self, irises, settings, parent = None):
        QDockWidget.__init__(self, "Control panel", parent)
        self.setObjectName("TopLevelControlPanel")
        self._irises = irises
        self._settings = settings

        widget = QWidget(self)
        self.setWidget(widget)
        layout = QHBoxLayout(widget)
        form = QFormLayout()
        layout.addLayout(form)

        freq = self._settings.value('TopLevelControlPanel/tddFrequency', 3.6e9, float)
        self._handleTddFreqChange(freq)
        tddFrequencyEntry = FreqEntryWidget(widget)
        tddFrequencyEntry.setValue(freq)
        tddFrequencyEntry.valueChanged.connect(self._handleTddFreqChange)
        form.addRow("TDD Frequency", tddFrequencyEntry)

        for dirName, direction in (("Tx controls", SOAPY_SDR_TX), ("Rx controls", SOAPY_SDR_RX)):
            groupBox = QGroupBox(dirName, widget)
            hbox = QHBoxLayout(groupBox)
            layout.addWidget(groupBox)
            for i, gainName in enumerate(irises[0].listGains(direction, 0)):
                if i%2 == 0:
                    form = QFormLayout()
                    hbox.addLayout(form)
                value = self._settings.value('TopLevelControlPanel/%sGain%s'%('Rx' if direction == SOAPY_SDR_RX else 'Tx', gainName), 0.0, float)
                self._handleGainChange(direction, gainName, value)
                edit = QDoubleSpinBox(widget)
                form.addRow(gainName, edit)
                r = irises[0].getGainRange(direction, 0, gainName)
                edit.setRange(r.minimum(), r.maximum())
                if r.step() != 0: edit.setSingleStep(r.step())
                edit.setSuffix(' dB')
                edit.setValue(value)
                edit.valueChanged.connect(functools.partial(self._handleGainChange, direction, gainName))

    def _handleTddFreqChange(self, newFreq):
        for direction in (SOAPY_SDR_RX, SOAPY_SDR_TX):
            threads = [threading.Thread(target=functools.partial(iris.setFrequency, direction, 0, "RF", newFreq)) for iris in self._irises]
            for t in threads: t.start()
            for t in threads: t.join()
        self._settings.setValue('TopLevelControlPanel/tddFrequency', newFreq)

    def _handleGainChange(self, direction, gainName, newValue):
        for ch in [0, 1]:
            threads = [threading.Thread(target=functools.partial(iris.setGain, direction, ch, gainName, newValue)) for iris in self._irises]
            for t in threads: t.start()
            for t in threads: t.join()
        self._settings.setValue('TopLevelControlPanel/%sGain%s'%('Rx' if direction == SOAPY_SDR_RX else 'Tx', gainName), newValue)

########################################################################
## Invoke the application
########################################################################
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings
from sklk_widgets import DeviceSelectionDialog
import SoapySDR
import argparse
import threading
import sys

if __name__ == '__main__':
    app = QApplication(sys.argv)

    #parser = argparse.ArgumentParser()
    #args = parser.parse_args()
    chan = None #set to 0 or 1 for only testing one channel (better performance in CBRS)
    serials = sys.argv[1:]
    if serials: handles = [dict(driver='iris',serial=s) for s in serials]
    else:
        handles = [h for h in SoapySDR.Device.enumerate(dict(driver='iris')) if 'CBRS' in h['frontend']]

    irises = SoapySDR.Device(handles)
    threads = [threading.Thread(target=setupIris, args=[iris,chan]) for iris in irises]
    for t in threads: t.start()
    for t in threads: t.join()

    settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Skylark", "CBRSArrayMonitor")

    w = MainWindow(irises=irises, settings=settings, chan=chan)
    w.show()
    sys.exit(app.exec_())
