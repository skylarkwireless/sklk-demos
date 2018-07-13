########################################################################
## Arbitrary settings widget with string value interface
########################################################################
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QSpinBox
from . StringValueComboBox import StringValueComboBox
from . LineEditCustom import LineEditCustom

class ArbitrarySettingsWidget(QWidget):
    valueChanged = pyqtSignal(str)

    def __init__(self, info, parent = None):
        QWidget.__init__(self, parent)
        self.setToolTip(info.description)
        self._info = info
        self._edit = None
        layout = QHBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        if self._info.type == self._info.BOOL:
            self._edit = QCheckBox(self)
            self._edit.toggled.connect(lambda x: self.valueChanged.emit(self.value()))
        elif self._info.type == self._info.INT:
            self._edit = QSpinBox(parent)
            self._edit.setRange(info.range.minimum(), info.range.maximum())
            self._edit.valueChanged.connect(lambda x: self.valueChanged.emit(str(x)))
        else:
            self._edit = LineEditCustom(self)
            self._edit.valueChanged.connect(self.valueChanged)

        if self._info.options:
            options = list(self._info.options)
            optionNames = list(self._info.optionNames)
            if self._info.type == self._info.STRING:
                self._edit.setVisible(False)
            else:
                options.insert(0, '')
                optionNames.insert(0, '<Custom>')
            self._comboBox = StringValueComboBox(options=options, optionNames=optionNames, parent=self)
            self._comboBox.valueChanged.connect(self.valueChanged)
            self.valueChanged.connect(self._handleUpdateComboBox)
            layout.addWidget(self._comboBox)

        if self._edit:
            layout.addWidget(self._edit)
            self.setValue(self._info.value)

    def value(self):
        if self._info.options and self._comboBox.value():
            return self._comboBox.value()
        if self._info.type == self._info.BOOL:
            return 'true' if self._edit.isChecked() else 'false'
        if self._info.type == self._info.INT:
            return str(self._edit.value())
        return self._edit.value()

    def setValue(self, val):

        if self._info.options:
            if val in self._info.options:
                self._comboBox.setValue(val)
                value = self._info.value #back to default
            else: self._comboBox.setValue('')

        if self._info.type == self._info.BOOL:
            self._edit.setChecked(val == 'true')
        elif self._info.type == self._info.INT:
            try: self._edit.setValue(int(val))
            except: pass
        else:
            self._edit.setValue(val)

    def _handleUpdateComboBox(self, value):
        #dual widget updated, but not using drop down
        if value != self._comboBox.value(): self._comboBox.setValue('')
