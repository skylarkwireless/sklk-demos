########################################################################
## Combo box with string value interface
########################################################################
from PyQt5.QtWidgets import QComboBox
from PyQt5.QtCore import pyqtSignal

class StringValueComboBox(QComboBox):
    valueChanged = pyqtSignal(str)

    def __init__(self, options, optionNames=list(), editable = False, parent = None):
        QComboBox.__init__(self, parent)
        if editable: raise Exception('TODO fix editable mode handlers and get value...')
        for i, data in enumerate(options):
            title = data if i >= len(optionNames) else optionNames[i]
            self.addItem(title, data)
        self.setEditable(editable)
        self.currentIndexChanged.connect(self._handleIndexChanged)

    def _handleIndexChanged(self, index):
        self.valueChanged.emit(self.itemData(index))

    def setValue(self, val):
        index = self.findData(val)
        if index == -1 and self.isEditable(): self.setEditText(val)
        elif index != -1: self.setCurrentIndex(index)

    def value(self): return self.itemData(self.currentIndex())
