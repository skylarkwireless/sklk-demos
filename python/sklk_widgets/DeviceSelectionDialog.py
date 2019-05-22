

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
import SoapySDR
import threading

DEVICE_POLL_TIME = 1.5 #seconds between poll

class DeviceSelectionDialog(QDialog):

    #signals
    devicesSelected = pyqtSignal(object) #ugh, have to use object so we can emit a list or a dict (for backwards compatibility)
    deviceListQueried = pyqtSignal(list)

    def __init__(self, channelSelect=False, timeSelect=False, settings=None, multiDevice=False, parent = None):
        QDialog.__init__(self, parent)
        self.setWindowTitle('Select a device...')
        self._layout = QVBoxLayout(self)
        self._timeSelect = timeSelect
        self._channelSelect = channelSelect
        self._multiDevice = multiDevice

        configLayout = QHBoxLayout()
        self._layout.addLayout(configLayout)

        selectButton = QPushButton("Select Device(s)", self)
        selectButton.clicked.connect(self._handleSelectClicked) #lambda: self._handleListDoubleClicked(self._list.currentItem()))
        selectButton.setEnabled(False)
        self._selectButton = selectButton
        
        self._list = QListWidget(self)
        if multiDevice:
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
            if timeSelect: self._timeCheckBox.setChecked(self._settings.value("DeviceSelectionDialog/timeSelect", False, type=bool))
            if channelSelect:
                sel = self._settings.value("DeviceSelectionDialog/channelSelect", "AB")
                for i, opt in enumerate(self._chOptions): self._chanRadioButtons[i].setChecked(opt == sel)

        self.finished.connect(self._handleFinished)

    def devicesHandle(self): return self._deviceHandles
    
    def deviceHandle(self): return self._deviceHandles[0]

    def showTime(self): return self._timeCheckBox.isChecked()

    def channels(self):
        for i, r in enumerate(self._chanRadioButtons):
            if r.isChecked(): return self._chOptions[i]

    def _handleFinished(self, num):
        if self._settings:
            if self._timeSelect: self._settings.setValue("DeviceSelectionDialog/timeSelect", self._timeCheckBox.isChecked())
            if self._channelSelect: self._settings.setValue("DeviceSelectionDialog/channelSelect", self.channels())
            self._settings.sync()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _queryDeviceListThread(self):
        self.deviceListQueried.emit([dict(elem) for elem in sorted(SoapySDR.Device.enumerate(dict(driver="iris")), key=lambda x: x['serial'])])

    #private slots

    def _handleDeviceListQueried(self, devices):
        if devices == self._knownDevices: return
        #reload the 
        self._selectButton.setEnabled(False)
        self._list.clear()
        self._knownDevices = devices
        for device in self._knownDevices: self._list.addItem(device['label'])
        #todo reselect devices

    def _handleListDoubleClicked(self, item):
        row = self._list.row(item)
        args = [self._knownDevices[row]]
        self._deviceHandles = args
        self.devicesSelected.emit(args if self._multiDevice else args[0])
        self.accept()

    def _handleSelectClicked(self):
        rows = self._list.selectedItems()
        args = [self._knownDevices[self._list.row(row)] for row in rows]
        self._deviceHandles = args
        self.devicesSelected.emit(args if self._multiDevice else args[0])
        self.accept()

    def _handleUpdateTimeout(self):
        if self._thread is not None and self._thread.isAlive(): return
        self._thread = threading.Thread(target=self._queryDeviceListThread)
        self._thread.start()

