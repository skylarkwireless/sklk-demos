#!/usr/bin/python3
#
#	Control GUI for high and low level controls. Useful for debugging.
#	Connect to an iris on the network and override its control settings.
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
from PyQt5.QtWidgets import QTabWidget
from PyQt5.QtWidgets import QSplashScreen
from PyQt5.QtWidgets import QScrollArea
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

class MainWindow(QMainWindow):
    def __init__(self, iris, settings, parent = None, **kwargs):
        QMainWindow.__init__(self, parent)
        self._splash = QSplashScreen(self, QPixmap('data/logo.tif'))
        self._splash.show()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Iris Control GUI - %s - Caution use at your own risk!"%kwargs['handle']['label'])
        self.setMinimumSize(800, 600)
        self._settings = settings

        #start the window
        self._controlTabs = QTabWidget(self)
        self.setCentralWidget(self._controlTabs)
        self._mainTab = HighLevelControlTab(iris, [0, 1], self._controlTabs)
        self._controlTabs.addTab(self._mainTab, "Main")
        for name, chans, start, stop in [
            ('LML', [0,], 0x0000, 0x002F),
            ('TxTSP', [0, 1], 0x0200, 0x020C),
            ('RxTSP', [0, 1], 0x0400, 0x040D),
            ('SXX', [0, 1], 0x011C, 0x0124),
            ('RFE', [0, 1], 0x010C, 0x0114),
            ('RBB', [0, 1], 0x0115, 0x011B),
            ('TRF', [0, 1], 0x0100, 0x0104),
            ('TBB', [0, 1], 0x0105, 0x010B),
            ('EN_DIR', [0,], 0x0081, 0x0081),
            ('LDO', [0,], 0x0092, 0x00A7),
            ('DC', [0,], 0x05C0, 0x05CC),
            ('AFE', [0,], 0x0082, 0x0082),
            ('BIAS', [0,], 0x0083, 0x0084),
            ('XBUF', [0,], 0x0085, 0x0085),
            ('CGEN', [0,], 0x0086, 0x008D),
            ('RSSI', [0,], 0x0600, 0x0641),
        ]:
            scroll = QScrollArea(self._controlTabs)
            tab = LowLevelControlTab(iris, chans, start, stop, scroll)
            scroll.setWidget(tab)
            self._controlTabs.addTab(scroll, name)

        #load previous settings
        print("Loading %s"%self._settings.fileName())
        if self._settings.contains("MainWindow/geometry"): self.restoreGeometry(self._settings.value("MainWindow/geometry"))
        if self._settings.contains("MainWindow/state"): self.restoreState(self._settings.value("MainWindow/state"))
        if self._settings.contains("MainWindow/tab"): self._controlTabs.setCurrentIndex(int(self._settings.value("MainWindow/tab")))

        #load complete
        self._splash.finish(self)

    def loadFile(self, filePath):
        self._mainTab.loadFile(filePath)

    def closeEvent(self, event):

        #stash settings
        self._settings.setValue("MainWindow/geometry", self.saveGeometry())
        self._settings.setValue("MainWindow/state", self.saveState())
        self._settings.setValue("MainWindow/tab", self._controlTabs.currentIndex())

########################################################################
## Parse the fields from the LMS7 source
########################################################################
import re
import os

paramsH = open(os.path.join(os.path.dirname(__file__), 'data', 'LMS7002M_parameters.h')).read()
PARAMS = list()
ADDRS = set()
for match in re.findall('static const struct LMS7Parameter ((LMS7_\w+)\s*=\s*{\s*(0x*.+?)}\s*;)', paramsH, re.MULTILINE | re.DOTALL):
    key, fields = match[1:]
    fields = fields.replace('\n', '')
    addr, stop, start, default, name, desc = eval(fields)
    PARAMS.append([key, addr, start, stop, default, name, desc])
    ADDRS.add(addr)

########################################################################
## Low level register edit widget
########################################################################
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QSpinBox
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtCore import pyqtSignal

class LowLevelEditWidget(QWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, addr, start, stop, default, name, desc, parent = None):
        QWidget.__init__(self, parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        nbits = 1+stop-start
        self._isCheckBox = stop == start

        if self._isCheckBox:
            edit = QCheckBox(self)
            edit.toggled.connect(lambda x: self.valueChanged.emit(1 if x else 0))
        else:
            edit = QSpinBox(self)
            if "2's complement" in desc:
                nbits -= 1
                edit.setRange(-(1 << nbits), (1 << nbits)-1)
            elif "Unsigned integer" in desc or nbits <= 4:
                edit.setRange(0, (1 << nbits)-1)
            else:
                edit.setDisplayIntegerBase(16)
                edit.setPrefix('0x')
                edit.setRange(0, (1 << nbits)-1)
            edit.valueChanged[int].connect(lambda x: self.valueChanged.emit(self.value()))

        edit.setToolTip(desc)
        layout.addWidget(edit)
        self._edit = edit

    def setValue(self, value):
        self._edit.blockSignals(True)
        if self._isCheckBox: self._edit.setChecked(bool(value))
        elif self._edit.minimum() < 0: #supports 2-compliment
            if value > self._edit.maximum(): self._edit.setValue(value+2*self._edit.minimum())
            else: self._edit.setValue(value)
        else: self._edit.setValue(value)
        self._edit.blockSignals(False)

    def value(self):
        if self._isCheckBox:
            return 1 if self._edit.isChecked() else 0
        elif self._edit.minimum() < 0: #supports 2-compliment
            value = self._edit.value()
            if value >= 0: return value
            return value - 2*self._edit.minimum()
        return self._edit.value()

########################################################################
## Low level register access control table
########################################################################
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QGroupBox
from PyQt5.QtWidgets import QFormLayout
from PyQt5.QtWidgets import QHBoxLayout
import functools

class LowLevelControlTab(QWidget):
    def __init__(self, iris, chans, start, stop, parent = None):
        QWidget.__init__(self, parent)
        layout = QHBoxLayout(self)
        self._iris = iris
        self._chans = chans
        self._start = start
        self._stop = stop

        self._editWidgets = dict()
        for ch in chans:

            if len(chans) == 1: title = ""
            elif start == 0x011C: title = 'SX' + "RT"[ch]
            else: title = "Ch" + "AB"[ch]
            groupBox = QGroupBox(title, self)
            layout.addWidget(groupBox)
            hbox = QHBoxLayout(groupBox)
            formLayout = QFormLayout()
            hbox.addLayout(formLayout)

            for i, addr in enumerate(range(start, stop+1)):
                for key, param_addr, bit_start, bit_stop, default, name, desc in PARAMS:
                    if addr != param_addr: continue
                    edit = LowLevelEditWidget(param_addr, bit_start, bit_stop, default, name, desc, self)
                    edit.setToolTip(desc)
                    if formLayout.count() == 40:
                        formLayout = QFormLayout()
                        hbox.addLayout(formLayout)
                    formLayout.addRow(name, edit)
                    self._editWidgets[(key, ch)] = edit
                    edit.valueChanged.connect(functools.partial(LowLevelControlTab.rmwSetting, iris, ch, addr, bit_start, bit_stop))

    @staticmethod
    def setChannel(iris, ch):
        rdVal = iris.readRegister('LMS7IC', 0x0020)
        wrVal = (rdVal & ~0x3) | (ch+1)
        if rdVal != wrVal: iris.writeRegister('LMS7IC', 0x0020, wrVal)

    @staticmethod
    def rmwSetting(iris, ch, addr, bit_start, bit_stop, val):
        LowLevelControlTab.setChannel(iris, ch)
        nbits = 1+bit_stop-bit_start
        mask = (1 << nbits)-1
        regVal = iris.readRegister('LMS7IC', addr)
        regVal &= ~(mask << bit_start)
        regVal |= (val & mask) << bit_start
        iris.writeRegister('LMS7IC', addr, regVal)

    def showEvent(self, e):
        for ch in self._chans:
            LowLevelControlTab.setChannel(self._iris, ch)
            values = iris.readRegisters('LMS7IC', self._start, 1+self._stop-self._start)
            for key, param_addr, bit_start, bit_stop, default, name, desc in PARAMS:
                if (key, ch) not in self._editWidgets: continue
                edit = self._editWidgets[(key, ch)]
                nbits = 1+bit_stop-bit_start
                mask = (1 << nbits)-1
                value = values[param_addr-self._start]
                val = (value >> bit_start) & mask
                edit.setValue(val)

########################################################################
## Main controls and high level controls
########################################################################
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QGroupBox
from PyQt5.QtWidgets import QFormLayout
from PyQt5.QtWidgets import QGridLayout
from PyQt5.QtWidgets import QDoubleSpinBox
from PyQt5.QtWidgets import QComboBox
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QFileDialog
from SoapySDR import *
from sklk_widgets import FreqEntryWidget
from sklk_widgets import ArbitrarySettingsWidget
from sklk_widgets import StringValueComboBox
import functools
import json

class HighLevelControlTab(QWidget):
    def __init__(self, iris, chans, parent = None):
        QWidget.__init__(self, parent)
        layout = QGridLayout(self)
        self._editWidgets = list()
        self._iris = iris
        self._txReplayWaveform = ""

        #global configuration parameters
        groupBox = QGroupBox("Global", self)
        layout.addWidget(groupBox, 0, 0, 2, 1)
        formLayout = QFormLayout(groupBox)
        for name, widgetType, setter, getter in (
            ("Rx Frequency", FreqEntryWidget, lambda f: [iris.setFrequency(SOAPY_SDR_RX, ch, "RF", f) for ch in [0, 1]], functools.partial(iris.getFrequency, SOAPY_SDR_RX, 0, "RF")),
            ("Tx Frequency", FreqEntryWidget, lambda f: [iris.setFrequency(SOAPY_SDR_TX, ch, "RF", f) for ch in [0, 1]], functools.partial(iris.getFrequency, SOAPY_SDR_TX, 0, "RF")),
            ("Sample Rate", FreqEntryWidget, lambda r: [iris.setSampleRate(d, 0, r) for d in (SOAPY_SDR_RX, SOAPY_SDR_TX)], functools.partial(iris.getSampleRate, SOAPY_SDR_RX, 0)),
        ):
            edit = FreqEntryWidget(groupBox)
            formLayout.addRow(name, edit)
            self.loadEditWidget(edit, setter, getter, [name])
        self.loadArbitrarySettings(groupBox, formLayout)

        info = SoapySDR.ArgInfo()
        info.type = info.STRING
        info.options.push_back("")
        info.options.push_back("LTS")
        info.optionNames.push_back("Off")
        info.optionNames.push_back("LTS")
        edit = ArbitrarySettingsWidget(info, self)
        formLayout.addRow("TX Replay Waveform", edit)
        self.loadEditWidget(edit,
            self.setupTxReplay,
            lambda: self._txReplayWaveform,
            ['Tx Waveform'])

        loadConfigButton = QPushButton("Load Config", groupBox)
        formLayout.addRow(loadConfigButton)
        loadConfigButton.pressed.connect(self._handleLoadDialog)
        saveConfigButton = QPushButton("Save Config", groupBox)
        formLayout.addRow(saveConfigButton)
        saveConfigButton.pressed.connect(self._handleSaveDialog)

        #per channel configuration parameters
        for ch in chans:
            for direction in (SOAPY_SDR_RX, SOAPY_SDR_TX):
                groupBox = QGroupBox(("Rx" if direction == SOAPY_SDR_RX else "Tx") + " Ch"+"AB"[ch], self)
                layout.addWidget(groupBox, 0 if direction == SOAPY_SDR_RX else 1, ch+1, 1, 1)
                self.loadChannelSettings(groupBox, direction, ch)

    def setupTxReplay(self, name):
        self._txReplayWaveform = name

        #empty string to disable
        if not name: return iris.writeSetting("TX_REPLAY", "")

        if name == "LTS":
            import lts
            samps = lts.genLTS()

        #TODO others

        def cfloat2uint32(arr):
            import numpy as np
            arr_i = (np.real(arr) * 32767).astype(np.uint16)
            arr_q = (np.imag(arr) * 32767).astype(np.uint16)
            return np.bitwise_or(arr_q ,np.left_shift(arr_i.astype(np.uint32), 16))

        samps = cfloat2uint32(samps)
        self._iris.writeRegisters('TX_RAM_A', 0, cfloat2uint32(samps).tolist())
        self._iris.writeRegisters('TX_RAM_B', 0, cfloat2uint32(samps).tolist())
        self._iris.writeSetting("TX_REPLAY", str(len(samps)))

    def loadChannelSettings(self, parent, direction, ch):
        hbox = QHBoxLayout(parent)
        formLayout = QFormLayout()
        hbox.addLayout(formLayout)
        factories = [
            ("NCO Frequency", FreqEntryWidget, functools.partial(self._iris.setFrequency, direction, ch, "BB"), functools.partial(self._iris.getFrequency, direction, ch, "BB")),
            ("Filter BW", FreqEntryWidget, functools.partial(self._iris.setBandwidth, direction, ch), functools.partial(self._iris.getBandwidth, direction, ch)),
        ]
        for name, widgetType, setter, getter in factories:
            edit = FreqEntryWidget(parent)
            formLayout.addRow(name, edit)
            self.loadEditWidget(edit, setter, getter, [direction, ch, name])
        for name in self._iris.listGains(direction, ch):
            edit = QDoubleSpinBox(parent)
            formLayout.addRow(name, edit)
            self.loadEditWidget(edit,
                functools.partial(self._iris.setGain, direction, ch, name),
                functools.partial(self._iris.getGain, direction, ch, name),
                [direction, ch, name])
            r = self._iris.getGainRange(direction, ch, name)
            edit.setRange(r.minimum(), r.maximum())
            if r.step() != 0: edit.setSingleStep(r.step())
            edit.setSuffix(' dB')
        formLayout = QFormLayout()
        hbox.addLayout(formLayout)
        edit = StringValueComboBox(options=self._iris.listAntennas(direction, ch), parent=parent)
        formLayout.addRow("Antenna", edit)
        self.loadEditWidget(edit,
            functools.partial(self._iris.setAntenna, direction, ch),
            functools.partial(self._iris.getAntenna, direction, ch),
            [direction, ch, 'Antenna'])
        self.loadArbitrarySettings(parent, formLayout, [direction, ch])
        if self._iris.hasDCOffsetMode(direction, ch):
            info = SoapySDR.ArgInfo()
            info.type = info.BOOL
            edit = ArbitrarySettingsWidget(info, self)
            formLayout.addRow("DC Removal", edit)
            self.loadEditWidget(edit,
                lambda v: iris.setDCOffsetMode(direction, ch, v == "true"),
                lambda: "true" if iris.getDCOffsetMode(direction, ch) else "false",
                [direction, ch, 'DC Removal'])
        sklkCalButton = QPushButton("SKLK Calibrate", parent)
        sklkCalButton.pressed.connect(functools.partial(self._iris.writeSetting, direction, ch, "CALIBRATE", "SKLK"))
        formLayout.addRow("Self Calibrate", sklkCalButton)
        mcuCalButton = QPushButton("MCU Calibrate", parent)
        mcuCalButton.pressed.connect(functools.partial(self._iris.writeSetting, direction, ch, "CALIBRATE", ""))
        formLayout.addRow("Self Calibrate", mcuCalButton)

    def loadArbitrarySettings(self, parent, formLayout, prefixArgs=[]):
        for info in self._iris.getSettingInfo(*prefixArgs):
            if 'FIR' in info.key: continue #skip FIR stuff
            if 'DELAY' in info.key: continue #skip tx delay
            if info.key in ('TRIGGER_GEN', 'SYNC_DELAYS', 'CALIBRATE', 'FPGA_TSG_CONST'): continue
            edit = ArbitrarySettingsWidget(info, parent)
            formLayout.addRow(info.name, edit)
            self.loadEditWidget(edit,
                functools.partial(self._iris.writeSetting, *(prefixArgs+[info.key])),
                functools.partial(self._iris.readSetting, *(prefixArgs+[info.key])),
                prefixArgs + [info.name])

    def loadEditWidget(self, edit, setter, getter, args):
        def safeCall(s, v):
            try: s(v)
            except Exception as ex: print(ex)
        edit.valueChanged.connect(functools.partial(safeCall, setter))
        self._editWidgets.append((edit, setter, getter, args))

    def showEvent(self, e):
       for edit, setter, getter, args in self._editWidgets:
           value = None
           try: value = getter()
           except Exception as ex: print(ex)
           if value is not None: edit.setValue(value)

    def _handleSaveDialog(self):
        fname = QFileDialog.getSaveFileName(self, "Save config to file", ".", "Config (*.json)")
        if not fname: return
        config = {'global':{}, 'tx':[{}, {}], 'rx':[{}, {}], 'regs':[{}, {}]}
        for edit, setter, getter, args in self._editWidgets:
            if len(args) == 1: config['global'][args[0]] = getter()
            else: config['tx' if args[0] == SOAPY_SDR_TX else 'rx'][args[1]][args[2]] = getter()
        r20 = self._iris.readRegister('LMS7IC', 0x0020) & ~0x3
        for ch in [0, 1]:
            self._iris.writeRegister('LMS7IC', 0x0020, r20 | (ch+1))
            for addr in ADDRS:
                if ch == 1 and addr < 0x0100: continue
                value = iris.readRegister('LMS7IC', addr)
                config['regs'][ch][hex(addr)] = hex(value)
        open(fname[0], 'w').write(json.dumps(config, indent=4))
        print('wrote %s'%fname[0])

    def _handleLoadDialog(self):
        fname = QFileDialog.getOpenFileName(self, "Open saved config file", ".", "Config (*.json)")
        if not fname: return
        self.loadFile(fname[0])

    def loadFile(self, fname):
        config = json.loads(open(fname).read())
        r20 = self._iris.readRegister('LMS7IC', 0x0020) & ~0x3
        for ch in [0, 1]:
            self._iris.writeRegister('LMS7IC', 0x0020, r20 | (ch+1))
            for addr, value in config['regs'][ch].items():
                iris.writeRegister('LMS7IC', int(addr, 16), int(value, 16))
        for edit, setter, getter, args in self._editWidgets:
            try:
                if len(args) == 1: setter(config['global'][args[0]])
                else: setter(config['tx' if args[0] == SOAPY_SDR_TX else 'rx'][args[1]][args[2]])
            except (IndexError, KeyError): print('Could not find %s in config...'%str(args))
        self.showEvent(None) #reload

########################################################################
## Invoke the application
########################################################################
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings
from sklk_widgets import DeviceSelectionDialog
import SoapySDR
import argparse
import sys

if __name__ == '__main__':
    app = QApplication(sys.argv)

    parser = argparse.ArgumentParser()
    parser.add_argument("--args", help="Device arguments (or none for selection dialog)")
    parser.add_argument("--file", help="Load saved config when specified")
    args = parser.parse_args()
    handle = args.args

    settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Skylark", "IrisControlGUI")

    if not handle:
        dialog = DeviceSelectionDialog(settings=settings)
        dialog.exec()
        handle = dialog.deviceHandle()
    else:
        handle = SoapySDR.Device.enumerate(handle)[0]
    if not handle:
        print('No device selected!')
        sys.exit(-1)

    iris = SoapySDR.Device(handle)

    w = MainWindow(iris=iris, settings=settings, handle=handle)
    w.show()
    if args.file: w.loadFile(args.file)
    sys.exit(app.exec_())
