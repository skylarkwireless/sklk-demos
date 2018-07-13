########################################################################
## A line edit with color for un-submitted changes
########################################################################

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QSizePolicy

class LineEditCustom(QLineEdit):

    #signals
    valueChanged = pyqtSignal(str)

    def __init__(self, parent):
        QLineEdit.__init__(self, parent)
        self.textChanged.connect(self._handleTextChanged)
        self.returnPressed.connect(self._handleReturnPressed)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred))

    def value(self):
        return self._value

    def setValue(self, value):
        self._value = value
        self.setText(value)
        self._updateState()

    def hasChange(self):
        return self._value != self.text()

    #private slots

    def _handleTextChanged(self, text):
        self._updateState()

    def _handleReturnPressed(self):
        self._value = self.text()
        self.valueChanged.emit(self._value)
        self._updateState()

    def _updateState(self):
        self.setStyleSheet("QLineEdit {background-color: #FFDFEF;}" if self.hasChange() else "")
