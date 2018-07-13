########################################################################
## Device selection dialog
########################################################################
from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QListWidget
from PyQt5.QtWidgets import QGroupBox
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QRadioButton
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import pyqtSignal
import SoapySDR
import threading

DEVICE_POLL_TIME = 1.5 #seconds between poll

class DeviceSelectionDialog(QDialog):

    #signals
    deviceSelected = pyqtSignal(dict)
    deviceListQueried = pyqtSignal(list)

    def __init__(self, channelSelect=False, timeSelect=False, parent = None):
        QDialog.__init__(self, parent)
        self.setWindowTitle('Select a device...')
        self._layout = QVBoxLayout(self)

        configLayout = QHBoxLayout()
        self._layout.addLayout(configLayout)

        selectButton = QPushButton("Select Device", self)
        selectButton.clicked.connect(lambda: self._handleListDoubleClicked(self._list.currentItem()))
        selectButton.setEnabled(False)

        self._list = QListWidget(self)
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
            self._chanRadioButtons[0].setChecked(True)

        if timeSelect:
            self._timeCheckBox = QCheckBox("Show time plots", self)
            configLayout.addWidget(self._timeCheckBox)
            self._timeCheckBox.setChecked(False)

        self.deviceListQueried.connect(self._handleDeviceListQueried)
        self._knownDevices = list()
        self._deviceHandle = None

        self._thread = None
        self._updateTimer = QTimer(self)
        self._updateTimer.setInterval(DEVICE_POLL_TIME*1000) #milliseconds
        self._updateTimer.timeout.connect(self._handleUpdateTimeout)
        self._handleUpdateTimeout() #initial update
        self._updateTimer.start()

    def deviceHandle(self): return self._deviceHandle

    def showTime(self): return self._timeCheckBox.isChecked()

    def channels(self):
        for i, r in enumerate(self._chanRadioButtons):
            if r.isChecked(): return self._chOptions[i]

    def closeEvent(self, event):
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
        args = self._knownDevices[row]
        #print(str(args))
        self._deviceHandle = args
        self.deviceSelected.emit(args)
        self.accept()

    def _handleUpdateTimeout(self):
        if self._thread is not None and self._thread.isAlive(): return
        self._thread = threading.Thread(target=self._queryDeviceListThread)
        self._thread.start()
