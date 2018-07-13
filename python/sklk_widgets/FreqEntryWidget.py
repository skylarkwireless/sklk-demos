########################################################################
## A line edit specialized for frequency entry
########################################################################

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QSizePolicy
from . LineEditCustom import LineEditCustom

ALLOWED_ERROR_HZ = 100

def freqToStr(freq):
    freq = int(round(freq/ALLOWED_ERROR_HZ))*ALLOWED_ERROR_HZ
    if freq >= 1e9: return '%g GHz'%(freq/1e9)
    if freq >= 1e6: return '%g MHz'%(freq/1e6)
    if freq >= 1e3: return '%g kHz'%(freq/1e3)
    return '%g Hz'%(freq/1e0)

def strToFreq(s):
    try:
        freq = float(s)
        return freq
    except: pass
    try:
        freq, suffix = s.split()
        freq = float(freq)
        suffix = suffix.upper().strip()
        if suffix in ['G', 'GHZ']: return freq*1e9
        if suffix in ['M', 'MHZ']: return freq*1e6
        if suffix in ['K', 'KHZ']: return freq*1e3
        if suffix in ['HZ']: return freq*1e0
    except: pass
    raise Exception('cant parse %s'%s)

class FreqEntryWidget(QWidget):

    #signals
    valueChanged = pyqtSignal(float)

    def __init__(self, parent):
        QWidget.__init__(self, parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._entry = LineEditCustom(self)
        self._layout.addWidget(self._entry)
        self._entry.valueChanged.connect(self._handleValueChanged)
        self.setValue(0)
        self._entry.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred))

    def value(self):
        return strToFreq(self._entry.value())

    def setValue(self, value):
        self._entry.setValue(freqToStr(value))

    def hasChange(self):
        try: return abs(self._entry.value() - strToFreq(self._entry.text())) > ALLOWED_ERROR_HZ
        except: return True

    #private slots

    def _handleValueChanged(self, value):
        try:
            hz = strToFreq(value)
            self.valueChanged.emit(hz)
            self.setValue(hz) #reformat
        except Exception as ex: print(ex)

