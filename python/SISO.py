#!/usr/bin/python
#
#	Simple SISO class for demonstrating a TX and/or RX.
#	This class was mostly made for use in Matlab, e.g.:
#		rate = 5e6;
#		siso_sdr = py.SISO.SISO_SDR(pyargs('rate', rate, 'txserial','0115', 'rxserial', '0114','freq',2484e6,'txGain',40.0,'rxGain',30.0));
#		time = 0:(1/rate):5000/rate - 1/rate; 
#		frequency = 1e6;
#		pilot_tone = [zeros(1,200), exp(sqrt(-1)*2*pi*frequency*time)*.5, zeros(1,200)];
#		x = siso_sdr.trx(real(pilot_tone),imag(pilot_tone));
#		rxData = double(py.array.array('d',py.numpy.nditer(py.numpy.real(x)))) +j*double(py.array.array('d',py.numpy.nditer(py.numpy.imag(x))));
#		plot(real(rxData))
#
#	This is a bit awkward since matlab doesn't understand numpy arrays, and array.array can't be complex.
#
#	Of course, you have to have matlab setup to use the right python, and SoapySDR installed with python setup to use it.
#
#	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#	INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
#	PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
#	FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#	OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#	DEALINGS IN THE SOFTWARE.
#
#	(c) 2018 info@skylarkwireless.com 

from argparse import ArgumentParser
import SoapySDR
from SoapySDR import * #SOAPY_SDR_constants
import numpy as np
import time

def cfloat2uint32(arr, order='IQ'):
		arr_i = (np.real(arr) * 32767).astype(np.uint16)
		arr_q = (np.imag(arr) * 32767).astype(np.uint16)
		if order == 'IQ':
			return np.bitwise_or(arr_q ,np.left_shift(arr_i.astype(np.uint32), 16))
		else:
			return np.bitwise_or(arr_i ,np.left_shift(arr_q.astype(np.uint32), 16))
	
def uint32tocfloat(arr, order='IQ'):
	arr_hi = ((np.right_shift(arr, 16).astype(np.int16))/32768.0)
	arr_lo = (np.bitwise_and(arr, 0xFFFF).astype(np.int16))/32768.0
	if order == 'IQ':
		return (arr_hi + 1j*arr_lo).astype(np.complex64)
	else:
		return (arr_lo + 1j*arr_hi).astype(np.complex64)

class SISO_SDR:
	'''
		Class that initializes 1 TX and/or 1 RX Irises (based on the serials provided),		
		If two are provided, it assumes the Irises are connected to each other and sharing a trigger.
	'''
		
	def __init__(self,
		rate=None,
		txserial=None,
		rxserial=None,
		freq=None,
		bw=None,
		txGain=None,
		rxGain=None,
		chained=True,
	):
		self.sdrs = []
		if txserial is not None: 
			self.txsdr = SoapySDR.Device(dict(driver="iris", serial = txserial))
			self.sdrs.append(self.txsdr)
		else: self.txsdr = None
		if rxserial is not None: 
			self.rxsdr = SoapySDR.Device(dict(driver="iris", serial = rxserial))
			self.sdrs.append(self.rxsdr)
		else: self.rxsdr = None
		
		self.trig_sdr = self.txsdr if txserial is not None else self.rxsdr
		self.rate = rate
		
		### Setup channel rates, ports, gains, and filters ###
		for sdr in self.sdrs:
			info = sdr.getHardwareInfo()
			for chan in [0]:
				if rate is not None: sdr.setSampleRate(SOAPY_SDR_RX, chan, rate)
				if bw is not None: sdr.setBandwidth(SOAPY_SDR_RX, chan, bw)
				if rxGain is not None: sdr.setGain(SOAPY_SDR_RX, chan, rxGain)
				if freq is not None: sdr.setFrequency(SOAPY_SDR_RX, chan, "RF", freq)
				sdr.setAntenna(SOAPY_SDR_RX, chan, "TRX")
				sdr.setFrequency(SOAPY_SDR_RX, chan, "BB", 0) #don't use cordic
				sdr.setDCOffsetMode(SOAPY_SDR_RX, chan, False) #dc removal on rx #we'll remove this in post-processing

				if rate is not None: sdr.setSampleRate(SOAPY_SDR_TX, chan, rate)
				if bw is not None: sdr.setBandwidth(SOAPY_SDR_TX, chan, bw)
				if txGain is not None: sdr.setGain(SOAPY_SDR_TX, chan, txGain) 
				if freq is not None: sdr.setFrequency(SOAPY_SDR_TX, chan, "RF", freq)
				print("Set frequency to %f" % sdr.getFrequency(SOAPY_SDR_TX,chan))
				sdr.setAntenna(SOAPY_SDR_TX, chan, "TRX")
				sdr.setFrequency(SOAPY_SDR_TX, chan, "BB", 0) #don't use cordic
				
				if ("CBRS" in info["frontend"]):
					#sdr.setGain(SOAPY_SDR_TX, chan, "PA1", 15)
					sdr.setGain(SOAPY_SDR_TX, chan, "PA2", 0)
					#sdr.setGain(SOAPY_SDR_TX, chan, "PA3", 30)
					#sdr.setGain(SOAPY_SDR_TX, chan, "PAD", 40) 
					sdr.setGain(SOAPY_SDR_TX, chan, "ATTN", 0) 
				if ("UHF" in info["frontend"]):
					sdr.setGain(SOAPY_SDR_RX, chan, 'ATTN1', -6) #[-18,0]
					sdr.setGain(SOAPY_SDR_RX, chan, 'ATTN2', -12) #[-18,0]
					sdr.setGain(SOAPY_SDR_TX, chan, 'ATTN', 0) #[-18,0]
		### Synchronize Triggers and Clocks ###
		if chained:
			self.trig_sdr.writeSetting('SYNC_DELAYS', "")
			for sdr in self.sdrs: sdr.setHardwareTime(0, "TRIGGER")
			self.trig_sdr.writeSetting("TRIGGER_GEN", "")
		else:
			for sdr in self.sdrs: sdr.setHardwareTime(0)  #they'll be a bit off...
			
		#create streams
		if rxserial is not None:
			self.rxsdr.writeSetting(SOAPY_SDR_RX, 0, 'CALIBRATE', 'SKLK')
			self.rxStream = self.rxsdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [0], {})
		if txserial is not None:
			self._txing = False
			self.txsdr.writeSetting(SOAPY_SDR_TX, 0, 'CALIBRATE', 'SKLK')
			self.txStream = None #we set this up in the tx so it can be continuous
		
	def rx(self, nsamps, rx_delay=57, delay=10000000, ts=None):
		'''Receive nsamps on rxsdr at timestamp ts, if provided, otherwise waits delay ns.'''
		if self.rxsdr is None:
			print('Error: No RX SDR provided!')
			return
		nsamps = int(nsamps)
		rx_delay_ns = SoapySDR.ticksToTimeNs(rx_delay,self.rate)
		hw_time = self.trig_sdr.getHardwareTime()
		ts = hw_time + delay + rx_delay_ns if ts is None else ts + rx_delay_ns
		sampsRecv = np.empty(nsamps, dtype=np.complex64)
		rxFlags = SOAPY_SDR_HAS_TIME | SOAPY_SDR_END_BURST
		self.rxsdr.activateStream(self.rxStream, rxFlags, ts, nsamps)
		
		#print(hw_time,delay,rx_delay_ns,ts)
		#print([sdr.getHardwareTime() for sdr in self.sdrs])
		time.sleep((ts - hw_time)/1e9)		
		
		sr = self.rxsdr.readStream(self.rxStream, [sampsRecv], nsamps, timeoutUs=int(1e6))
		if sr.ret != nsamps:
			print("Bad read!!!")
		return sampsRecv
	
	def tx(self, sig, sigimag=None, delay=10000000, continuous=False):		
		'''Transmit sig on txsdr; repeat indefinitely if continuous.  Returns timestamp of start of tx.'''
		
		if self.txsdr is None:
			print('Error: No TX SDR provided!')
			return
		if sigimag is not None: sig = np.asarray(sig, dtype=np.complex64) + 1.j*np.asarray(sigimag, dtype=np.complex64)  #hack for matlab...
		self._txing = continuous
		if continuous:
			replay_addr = 0
			max_replay = 4096  #todo: read from hardware
			if(len(sig) > max_replay):
				print("Warning: Continuous mode signal must be less than %d samples. Using first %d samples." % (max_replay, max_replay) )
				sig = sig[:max_replay]
			self.txsdr.writeRegisters('TX_RAM_A', replay_addr, cfloat2uint32(sig).tolist())
			self.txsdr.writeSetting("TX_REPLAY", str(len(sig)))
		else:
			if self.txStream is not None: self.txsdr.deactivateStream(self.txStream)
			self.txStream = self.txsdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32, [0], {})
		
		
			ts = self.trig_sdr.getHardwareTime() + delay #give us delay ns to set everything up.
			txFlags = SOAPY_SDR_HAS_TIME | SOAPY_SDR_END_BURST
			self.txsdr.activateStream(self.txStream)
			sr = self.txsdr.writeStream(self.txStream, [sig.astype(np.complex64)], len(sig), txFlags, timeNs=ts)
			
			if sr.ret != len(sig):
				print("Bad Write!!!")
			return ts
	
	def stop_tx(self):
		self.txsdr.writeSetting("TX_REPLAY", '')
		self._txing = False
	
	def trx(self, sig, sigimag=None, delay=10000000, rx_delay=57):
		'''Perform synchronized tx/rx and return received signal.'''
		if self._txing:
			print('Warning! trx() called during continuous transmit.  Just calling rx().')
			return self.rx(len(sig), rx_delay=rx_delay)
		if sigimag is not None: sig = np.asarray(sig, dtype=np.complex64) + 1.j*np.asarray(sigimag, dtype=np.complex64)  #hack for matlab...
		ts = self.tx(sig, delay=delay)
		return self.rx(len(sig), ts=ts, rx_delay=rx_delay)

	def close(self):
		'''Cleanup streams.'''
		print("Cleanup streams")
		if self.txsdr is not None:
			if self.txStream is not None: self.txsdr.deactivateStream(self.txStream)
			self.txsdr.closeStream(self.txStream)
			self.txsdr = None #still doesn't release handle... you have to kill python.
			self.txStream = None
		if self.rxsdr is not None:
			self.rxsdr.deactivateStream(self.rxStream)
			self.rxsdr.closeStream(self.rxStream)
			self.rxsdr = None
			self.rxStream = None
		print("Done!")
		
def printSensor(irises, *args):
	'''Print sensor values from array of Irises, e.g., ZYNQ_TEMP.'''
	try: iter(irises)
	except TypeError: irises = [irises]
	info = irises[0].getSensorInfo(*args)
	name, units = info.name, info.units
	out = name.ljust(25)
	for iris in irises:
		value = iris.readSensor(*args)
		out += ('%g'%float(value)).ljust(10) + " "
	out += units
	print(out)


if __name__ == '__main__':

	parser = ArgumentParser()
	parser.add_argument("--txserial", type=str, dest="txserial", help="TX SDR Serial Number, e.g., 00001", default=None)
	parser.add_argument("--rxserial", type=str, dest="rxserial", help="RX SDR Serial Number, e.g., 00002", default=None)
	parser.add_argument("--rate", type=float, dest="rate", help="Sample rate", default=7.68e6)
	parser.add_argument("--txGain", type=float, dest="txGain", help="Optional Tx gain (dB)", default=40)
	parser.add_argument("--rxGain", type=float, dest="rxGain", help="Optional Rx gain (dB)", default=20)
	parser.add_argument("--freq", type=float, dest="freq", help="Optional Tx freq (Hz)", default=2450e6)
	parser.add_argument("--bw", type=float, dest="bw", help="Optional filter bw (Hz)", default=30e6)
	args = parser.parse_args()
	
	siso_sdr = SISO_SDR(
		txserial=args.txserial,
		rxserial=args.rxserial,
		rate=args.rate,
		freq=args.freq,
		bw=args.bw,
		txGain=args.txGain,
		rxGain=args.rxGain,
	)
	
	#Generate signal to send
	nsamps = 78000*2
	nsamps_pad = 100
	s_freq = 500e3
	Ts = 1/siso_sdr.rate
	s_time_vals = np.array(np.arange(0,nsamps)).transpose()*Ts
	sig = np.exp(s_time_vals*1j*2*np.pi*s_freq).astype(np.complex64)*.5
	sig_pad = np.concatenate((np.zeros(nsamps_pad), sig, np.zeros(nsamps_pad)))
	
	#rx = siso_sdr.trx(sig_pad) if args.txserial is not None else siso_sdr.rx(nsamps)
	
	#import matplotlib.pyplot as plt
	#plt.plot(rx)
	
	#siso_sdr.close()
