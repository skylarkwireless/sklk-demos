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
from PyQt5.QtCore import QSettings
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

class MainWindow(QMainWindow):
    def __init__(self, iris, parent = None, **kwargs):
        QMainWindow.__init__(self, parent)
        self._splash = QSplashScreen(self, QPixmap('data/logo.tif'))
        self._splash.show()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Iris Control GUI - Caution use at your own risk!")
        self.setMinimumSize(800, 600)
        self._settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Skylark", "IrisControlGUI", self)

        #start the window
        self._controlTabs = QTabWidget(self)
        self.setCentralWidget(self._controlTabs)
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

    def closeEvent(self, event):

        #stash settings
        self._settings.setValue("MainWindow/geometry", self.saveGeometry())
        self._settings.setValue("MainWindow/state", self.saveState())
        self._settings.setValue("MainWindow/tab", self._controlTabs.currentIndex())

########################################################################
## Parse the fields from the LMS7 source
########################################################################
import re
paramsH = open('data/LMS7002M_parameters.h').read()
PARAMS = list()
for match in re.findall('static const struct LMS7Parameter ((LMS7_\w+)\s*=\s*{\s*(0x*.+?)}\s*;)', paramsH, re.MULTILINE | re.DOTALL):
    key, fields = match[1:]
    fields = fields.replace('\n', '')
    addr, stop, start, default, name, desc = eval(fields)
    PARAMS.append([key, addr, start, stop, default, name, desc])

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
                    def makeUpdateCallback(*args): return lambda val: LowLevelControlTab.rmwSetting(val, *args)
                    edit.valueChanged.connect(makeUpdateCallback(iris, ch, addr, bit_start, bit_stop))

    @staticmethod
    def setChannel(iris, ch):
        rdVal = iris.readRegister('LMS7IC', 0x0020)
        wrVal = (rdVal & ~0x3) | (ch+1)
        if rdVal != wrVal: iris.writeRegister('LMS7IC', 0x0020, wrVal)

    @staticmethod
    def rmwSetting(val, iris, ch, addr, bit_start, bit_stop):
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
## Invoke the application
########################################################################
from PyQt5.QtWidgets import QApplication
import SoapySDR
import argparse
import sys

if __name__ == '__main__':
    app = QApplication(sys.argv)

    parser = argparse.ArgumentParser()
    parser.add_argument("--args", help="Device arguments (or none for selection dialog)")
    args = parser.parse_args()
    handle = args.args

    iris = SoapySDR.Device(handle)

    w = MainWindow(iris=iris, handle=handle)
    w.show()
    sys.exit(app.exec_())
