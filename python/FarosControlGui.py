#!/usr/bin/python3
#
#	Control GUI for high and low level controls. Useful for debugging.
#	Connect to irises on the network and override its control settings.
#
#	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#	INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
#	PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
#	FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#	OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#	DEALINGS IN THE SOFTWARE.
#
#	(c) info@skylarkwireless.com 2019
#
#   TODO: Fix bug where only some values are written back when switching readback Irises or
#         switching panes (only some widgets call their setters)

########################################################################
## Main window
########################################################################
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWidgets import QTabWidget
from PyQt5.QtWidgets import QSplashScreen
from PyQt5.QtWidgets import QScrollArea
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

class CallableList(list):
	"""Nifty list that simply calls the function on every element, then returns all of their return values in a list."""
	def __init__(self, *a, **kw):
		super(CallableList, self).__init__(*a, **kw)
	def __getattr__(self, attr): #if you use __getattribute__ it overrides the list functions!
		def f(*a, **kw):
			return CallableList([getattr(n,attr)(*a, **kw) for n in self])
		return f

def listFuncHelper(funcs, *a, **kw):
    return [f( *a, **kw) for f in funcs]

class MainWindow(QMainWindow):
    def __init__(self, irises, settings, parent = None, **kwargs):
        QMainWindow.__init__(self, parent)
        self._splash = QSplashScreen(self, QPixmap('data/logo.tif'))
        self._splash.show()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Faros Control GUI - %s - %s - Caution use at your own risk!" % (irises[0].getHardwareInfo()['frontend'], str([iris.getHardwareInfo()['serial'] for iris in irises]))) #%kwargs['handles']['label'])
        self.setMinimumSize(800, 600)
        self._settings = settings

        #start the window
        self._controlTabs = QTabWidget(self)
        self.setCentralWidget(self._controlTabs)
        self._tabs = {}
        self._mainTab = HighLevelControlTab(irises, [0, 1], self.setReadIris, self.setWriteIrises, self._controlTabs)
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
        ]:
            scroll = QScrollArea(self._controlTabs)
            self._tabs[name] = LowLevelControlTab(irises, chans, start, stop, scroll)
            scroll.setWidget(self._tabs[name])
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

    def setReadIris(self, iris):
        for k,tab in self._tabs.items():
            tab._iris = iris #lazy, not implementing setter
    def setWriteIrises(self, irises):
        for k,tab in self._tabs.items():
            tab._writeIrises = irises #lazy, not implementing setter

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
    def __init__(self, irises, chans, start, stop, parent = None):
        QWidget.__init__(self, parent)
        layout = QHBoxLayout(self)
        self._iris = irises[0]
        self._irises = irises
        self._writeIrises = irises
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
                    edit.valueChanged.connect(functools.partial(LowLevelControlTab.rmwSetting, irises, ch, addr, bit_start, bit_stop))

    @staticmethod
    def setChannel(irises, ch):
        rdVal = irises[0].readRegister('LMS7IC', 0x0020)
        wrVal = (rdVal & ~0x3) | (ch+1)
        for iris in irises: iris.writeRegister('LMS7IC', 0x0020, wrVal)

    @staticmethod
    def rmwSetting(irises, ch, addr, bit_start, bit_stop, val):
        LowLevelControlTab.setChannel(irises, ch)
        nbits = 1+bit_stop-bit_start
        mask = (1 << nbits)-1
        regVal = irises[0].readRegister('LMS7IC', addr)
        regVal &= ~(mask << bit_start)
        regVal |= (val & mask) << bit_start
        for iris in irises: iris.writeRegister('LMS7IC', addr, regVal)

    def showEvent(self, e):
        for ch in self._chans:
            LowLevelControlTab.setChannel(self._writeIrises, ch)
            values = self._iris.readRegisters('LMS7IC', self._start, 1+self._stop-self._start)
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
#from PyQt5.QtWidgets import QGroupBox
#from PyQt5.QtWidgets import QFormLayout
from PyQt5.QtWidgets import QGridLayout
from PyQt5.QtWidgets import QDoubleSpinBox
#from PyQt5.QtWidgets import QComboBox
#from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtWidgets import QPushButton
#from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtWidgets import QRadioButton
from PyQt5.QtWidgets import QLabel
from SoapySDR import *
from sklk_widgets import FreqEntryWidget
from sklk_widgets import ArbitrarySettingsWidget
from sklk_widgets import StringValueComboBox
import functools
import json

class HighLevelControlTab(QWidget):
    def __init__(self, irises, chans, setReadIrisCallback, setWriteIrisesCallback, parent = None):
        QWidget.__init__(self, parent)
        layout = QGridLayout(self)
        self._setReadIrisCallback = setReadIrisCallback
        self._setWriteIrisesCallback = setWriteIrisesCallback
        self._editWidgets = list()
        self._iris = irises[0]
        self._irises = irises
        self._writeIrises = irises
        self._txReplayWaveform = ""

        #global configuration parameters
        groupBox = QGroupBox("Global", self)
        layout.addWidget(groupBox, 0, 0, 2, 1)
        formLayout = QFormLayout(groupBox)
        for name, widgetType, setter, getter in (
            ("Rx Frequency", FreqEntryWidget, lambda f: [[iris.setFrequency(SOAPY_SDR_RX, ch, "RF", f) for ch in [0, 1] for iris in irises]], lambda: self._iris.getFrequency(SOAPY_SDR_RX, 0, "RF")), #functools.partial(self._iris.getFrequency, SOAPY_SDR_RX, 0, "RF")),
            ("Tx Frequency", FreqEntryWidget, lambda f: [[iris.setFrequency(SOAPY_SDR_TX, ch, "RF", f) for ch in [0, 1] for iris in irises]], lambda: self._iris.getFrequency(SOAPY_SDR_TX, 0, "RF")),
            ("Sample Rate", FreqEntryWidget, lambda r: [[iris.setSampleRate(d, 0, r) for d in (SOAPY_SDR_RX, SOAPY_SDR_TX) for iris in irises]], lambda: self._iris.getSampleRate(SOAPY_SDR_RX, 0)),
        ):
            edit = FreqEntryWidget(groupBox)
            formLayout.addRow(name, edit)
            self.loadEditWidget(edit, setter, getter, [name])
        self.loadArbitrarySettings(groupBox, formLayout)

        if len(irises) > 1:
            irisGroupBox = QGroupBox("Iris Read/Write Select (Experimental!)", self)
            layout.addWidget(irisGroupBox, 2, 0, 1, 3, Qt.AlignHCenter)
            irisLayout = QFormLayout(irisGroupBox)
            irisReadRadioLayout = QHBoxLayout(irisGroupBox)
            irisLayout.addRow(irisReadRadioLayout)
            irisReadRadioLayout.addWidget(QLabel("Readback:"))            
            self._irisRadioButtons = [QRadioButton(iris.getHardwareInfo()['serial'], irisGroupBox) for iris in irises]
            #for i,r in (irises,self._irisRadioButtons): r.iris = i
            self._irisRadioButtons[0].setChecked(True)
            for i,r in zip(irises,self._irisRadioButtons): 
                irisReadRadioLayout.addWidget(r)
                r.toggled.connect(functools.partial(self.setReadIris, i))
            irisWriteCheckBoxLayout = QHBoxLayout(irisGroupBox)
            irisWriteCheckBoxLayout.addWidget(QLabel("Write:"))
            irisLayout.addRow(irisWriteCheckBoxLayout)
            self._irisWriteCheckButtons = [QCheckBox(iris.getHardwareInfo()['serial'], irisGroupBox) for iris in irises]
            for i,r in zip(irises,self._irisWriteCheckButtons): 
                r.iris = i
                irisWriteCheckBoxLayout.addWidget(r)
                r.setChecked(True)
                r.toggled.connect(self.setWriteIrises)

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
            lambda: self._txReplayWaveform, ['Tx Waveform'])

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
    
    def setReadIris(self, iris, checked):
        if checked:
            print("Iris %s selected for readback." % iris.getHardwareInfo()['serial'])
            self._iris = iris
            self._setReadIrisCallback(iris)
            self.setWriteIrises(self._irisWriteCheckButtons) #this is done to make sure the read Iris is selected for write.
            self.showEvent(None) #reload the values

    def setWriteIrises(self, checked):
        self._writeIrises = [b.iris for b in self._irisWriteCheckButtons if b.isChecked() or b.iris is self._iris]
        [b.setChecked(True) for b in self._irisWriteCheckButtons if b.iris is self._iris]
        self._setWriteIrisesCallback(self._writeIrises)
            
    def getIris(self): return self._iris
            
    def setupTxReplay(self, name):
        self._txReplayWaveform = name

        #empty string to disable
        if not name: return [iris.writeSetting("TX_REPLAY", "") for iris in self._writeIrises][0]

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
        for iris in self._writeIrises: iris.writeRegisters('TX_RAM_A', 0, cfloat2uint32(samps).tolist())
        for iris in self._writeIrises: iris.writeRegisters('TX_RAM_B', 0, cfloat2uint32(samps).tolist())
        for iris in self._writeIrises: iris.writeSetting("TX_REPLAY", str(len(samps)))

    def loadChannelSettings(self, parent, direction, ch):
        hbox = QHBoxLayout(parent)
        formLayout = QFormLayout()
        hbox.addLayout(formLayout)
        factories = [
            ("NCO Frequency", FreqEntryWidget, functools.partial(listFuncHelper, [iris.setFrequency for iris in self._writeIrises], direction, ch, "BB"), lambda direction=direction, ch=ch: self._iris.getFrequency(direction, ch, "BB")), #functools.partial(self._iris.getFrequency, direction, ch, "BB")), # use this syntax to make direction and ch to persist, but execute self._iris when called (for switching iris readback): https://stackoverflow.com/questions/11087047/deferred-evaluation-with-lambda-in-python/11087323
            ("Filter BW", FreqEntryWidget, functools.partial(listFuncHelper, [iris.setBandwidth for iris in self._writeIrises], direction, ch), lambda direction=direction, ch=ch: self._iris.getBandwidth(direction, ch)),
        ]
        for name, widgetType, setter, getter in factories:
            edit = FreqEntryWidget(parent)
            formLayout.addRow(name, edit)
            self.loadEditWidget(edit, setter, getter, [direction, ch, name])
        for name in self._iris.listGains(direction, ch):
            edit = QDoubleSpinBox(parent)
            formLayout.addRow(name, edit)
            self.loadEditWidget(edit,
                functools.partial(listFuncHelper, [iris.setGain for iris in self._writeIrises], direction, ch, name),
                lambda direction=direction, ch=ch, name=name: self._iris.getGain(direction, ch, name),
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
            functools.partial(listFuncHelper, [iris.setAntenna for iris in self._writeIrises], direction, ch),
            lambda direction=direction, ch=ch: self._iris.getAntenna(direction, ch),
            [direction, ch, 'Antenna'])
        self.loadArbitrarySettings(parent, formLayout, [direction, ch])
        if self._iris.hasDCOffsetMode(direction, ch):
            info = SoapySDR.ArgInfo()
            info.type = info.BOOL
            edit = ArbitrarySettingsWidget(info, self)
            formLayout.addRow("DC Removal", edit)
            self.loadEditWidget(edit,
                lambda v: [iris.setDCOffsetMode(direction, ch, v == "true") for iris in self._writeIrises], #this is a lambda in IrisControlGui, but maybe it's messing things up?
                lambda: "true" if self._iris.getDCOffsetMode(direction, ch) else "false",
                [direction, ch, 'DC Removal'])
        sklkCalButton = QPushButton("SKLK Calibrate", parent)
        sklkCalButton.pressed.connect(functools.partial(listFuncHelper, [iris.writeSetting for iris in self._writeIrises], direction, ch, "CALIBRATE", "SKLK"))
        formLayout.addRow("Self Calibrate", sklkCalButton)
        mcuCalButton = QPushButton("MCU Calibrate", parent)
        mcuCalButton.pressed.connect(functools.partial(listFuncHelper, [iris.writeSetting for iris in self._writeIrises], direction, ch, "CALIBRATE", ""))
        formLayout.addRow("Self Calibrate", mcuCalButton)

    def loadArbitrarySettings(self, parent, formLayout, prefixArgs=[]):
        for info in self._iris.getSettingInfo(*prefixArgs):
            if 'FIR' in info.key: continue #skip FIR stuff
            if 'DELAY' in info.key: continue #skip tx delay
            if info.key in ('TRIGGER_GEN', 'SYNC_DELAYS', 'CALIBRATE', 'FPGA_TSG_CONST'): continue
            edit = ArbitrarySettingsWidget(info, parent)
            formLayout.addRow(info.name, edit)
            self.loadEditWidget(edit,
                functools.partial(listFuncHelper, [iris.writeSetting for iris in self._writeIrises], *(prefixArgs+[info.key])), #lambda v: [iris.writeSetting(*(prefixArgs+[info.key]), v) for iris in self._writeIrises],  #for some reason this is passing "NONE" to RBB_SET_PATH which is not valid.  Not sure why it doesn't complain in the IrisControlGui.py
                lambda prefixArgs=prefixArgs, key=info.key: self._iris.readSetting(*(prefixArgs+[key])),
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
            for iris in self._writeIrises: iris.writeRegister('LMS7IC', 0x0020, r20 | (ch+1))
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
            for iris in self._writeIrises: iris.writeRegister('LMS7IC', 0x0020, r20 | (ch+1))
            for addr, value in config['regs'][ch].items():
                    for iris in self._writeIrises: iris.writeRegister('LMS7IC', int(addr, 16), int(value, 16))
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
    parser.add_argument("--serials", type=str, dest="serials", help="SDR Serial Numbers, e.g. 00002 00004", default=None)
    args = parser.parse_args()

    settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Skylark", "IrisControlGUI")

    if args.serials is None:
        dialog = DeviceSelectionDialog(settings=settings, multiDevice=True, FEfilter=True)
        dialog.exec()
        handles = dialog.devicesHandle()
    else:
        handles = [dict(serial=s) for s in args.serials.split()]
    if len(handles) < 1:
        print('No device selected!')
        sys.exit(-1)

    print(handles)
    irises = SoapySDR.Device(handles)

    #check all Irises are the same (at least same FE)
    fes = [iris.getHardwareInfo()["frontend"] for iris in irises]
    if any([fe != fes[0] for fe in fes]):
        print("Not all frontends match! Expected: %s" % fes[0])
        sys.exit(-1)

    w = MainWindow(irises=irises, settings=settings, handles=handles)
    w.show()
    if args.file: w.loadFile(args.file)
    sys.exit(app.exec_())
