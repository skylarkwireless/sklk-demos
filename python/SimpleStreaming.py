#!/usr/bin/python
#
#	Bare minimum tx/rx continuous streaming example.  By default it transmits 0s, and 
#	overwrites the same receive buffer; this is just to show and test network streaming.
#
#	Requires one argument: the serial of the Iris being used.
#
#	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#	INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
#	PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
#	FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#	OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#	DEALINGS IN THE SOFTWARE.
#
#	(c) 2019 info@skylarkwireless.com 

import numpy as np
import sys
import os
import SoapySDR
import time
from SoapySDR import * #SOAPY_SDR_constants

if __name__ == '__main__':
	freq = 2.45e9
	rate = 5e6
	rxGain = 10
	txGain = 40
	delay = int(10e6)
	nsamps=8092

	if len(sys.argv) != 2:
		print("Usage: %s IrisSerial" % os.path.basename(__file__))
		sys.exit(-1)

	sdr = SoapySDR.Device(dict(driver="iris", serial = sys.argv[1]))

	# Init Rx
	sdr.setSampleRate(SOAPY_SDR_RX, 0, rate)
	sdr.setFrequency(SOAPY_SDR_RX, 0, "RF", freq)
	sdr.setGain(SOAPY_SDR_RX, 0, rxGain)
	sdr.setAntenna(SOAPY_SDR_RX, 0, "RX")

	# Init Tx
	sdr.setSampleRate(SOAPY_SDR_TX, 0, rate)
	sdr.setFrequency(SOAPY_SDR_TX, 0, "RF", freq)
	sdr.setGain(SOAPY_SDR_TX, 0, txGain)
	sdr.setAntenna(SOAPY_SDR_TX, 0, "TRX")

	#Init Buffers
	sampsRecv = np.zeros(nsamps, dtype=np.complex64)
	sampsSend = np.zeros(nsamps, dtype=np.complex64)

	#Init Streams
	rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [0], {})
	txStream = sdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32, [0], {})

	ts = sdr.getHardwareTime() + delay
	sdr.activateStream(txStream)
	sdr.activateStream(rxStream, SOAPY_SDR_HAS_TIME, ts)

	t=time.time()
	total_samps = 0

	#first call to tx needs timestamp
	sr = sdr.writeStream(txStream, [sampsSend], nsamps, SOAPY_SDR_HAS_TIME, ts+delay)
	if sr.ret != nsamps:
		print("Bad Write!!!")

	while True:
		#print(sdr.getHardwareTime(),ts + SoapySDR.ticksToTimeNs(total_samps, rate), time.time() - t) #debug
		sr = sdr.writeStream(txStream, [sampsSend], nsamps, 0) 
		if sr.ret != nsamps:
			print("Bad Write!!!")
		#do some tx processing here

		sr = sdr.readStream(rxStream, [sampsRecv], nsamps, timeoutUs=int(10e6))	
		if sr.ret != nsamps:
			print("Bad Read!!!")
		#do some rx processing here

		#print an update
		total_samps += nsamps
		if time.time() - t > 1:
			t=time.time()
			print("Total Samples Sent and Received: %i" % total_samps)

		#It is probably good to sleep here, but the readStream will block sufficiently
		#it just depends on your processing

