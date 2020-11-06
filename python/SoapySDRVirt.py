#!/usr/bin/python
#
#	Simple class to emulate SoapySDR devices locally.
#   This is an initial version and needs improvement.
#   It can only really be used to quickly test SoapySDR code.
#
#   It is lacking any sort of timestamp or streaming ability, or any notion of sample rate.  
#   It could probably be done much more effectively at a lower layer, e.g., a SoapyRemote 
#   device attached to a channel emulator.
#
#
#
#   #usage: import SoapySDRVirt as SoapySDR
#   call ChanEmu().reset() to clear the buffers.
#
#	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#	INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
#	PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
#	FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#	OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#	DEALINGS IN THE SOFTWARE.
#
#	(c) 2020 info@skylarkwireless.com 

import numpy as np

#these are included just to avoid errors.
#Constants
SOAPY_SDR_TX = 0
SOAPY_SDR_RX = 1
SOAPY_SDR_END_BURST = (1 << 1)
SOAPY_SDR_HAS_TIME = (1 << 2)
SOAPY_SDR_END_ABRUPT = (1 << 3)
SOAPY_SDR_ONE_PACKET = (1 << 4)
SOAPY_SDR_MORE_FRAGMENTS = (1 << 5)
SOAPY_SDR_WAIT_TRIGGER = (1 << 6)

#data types
SOAPY_SDR_CF64 = "CF64" 
SOAPY_SDR_CF32 = "CF32" 
SOAPY_SDR_CS32 = "CS32" 
SOAPY_SDR_CU32 = "CU32" 
SOAPY_SDR_CS16 = "CS16" 
SOAPY_SDR_CU16 = "CU16" 
SOAPY_SDR_CS12 = "CS12" 
SOAPY_SDR_CU12 = "CU12" 
SOAPY_SDR_CS8 = "CS8" 
SOAPY_SDR_CU8 = "CU8" 
SOAPY_SDR_CS4 = "CS4" 
SOAPY_SDR_CU4 = "CU4" 
SOAPY_SDR_F64 = "F64" 
SOAPY_SDR_F32 = "F32" 
SOAPY_SDR_S32 = "S32" 
SOAPY_SDR_U32 = "U32" 
SOAPY_SDR_S16 = "S16" 
SOAPY_SDR_U16 = "U16" 
SOAPY_SDR_S8 = "S8" 
SOAPY_SDR_U8 = "U8"

def ticksToTimeNs(ticks, rate):
    return ticks*1e9/rate

def timeNsToTicks(timeNs, rate):
    return timeNs*rate/1e9

def clip(a, m=1, nbits=12):
    np.clip(a.real, -m, m, out=a.real)
    np.clip(a.imag, -m, m, out=a.imag)
    if nbits is not None:
        #quick way to simulate limited bit precision (and make rx gain important)
        a.real[np.argwhere(np.abs(a.real) < 1/2**(nbits-1))] = 0 #highest bit is sign
        a.imag[np.argwhere(np.abs(a.imag) < 1/2**(nbits-1))] = 0
    return a

class Channel:
    ''' 
    A very basic multipath channel model with some number of taps over a delay spread, each with their own phase and attenuation.
    It implements various impairments including noise, CFO, delay, and DC offset.
    Parameters are static once instantiated.
    '''
    def __init__(self, noise=-70, phase_shift=True, attn=-40, attn_var=5, delay=48, delay_var=5, dc=.1, iq_imbal=.1, cfo=.00005, delay_spread=5, num_taps=4, tap_attn=12):
    #def __init__(self, noise=None, phase_shift=False, attn=-30, attn_var=0, delay=48, delay_var=0, dc=0, iq_imbal=0, cfo=0, delay_spread=1, num_taps=1, tap_attn=4):
        #cfo in phase rotation per sample in radians
        if num_taps < 1:
            print("There must be at least one tap.")
            num_taps = 1
        if num_taps > delay_spread:
            print("num_taps must be higher than delay_spread.  adjusting delay_spread.")
            delay_spread = num_taps + 1        
        self.delay = delay 
        self.delay_spread = delay_spread
        self.num_taps = num_taps
        if delay_var > 0: self.delay += np.random.randint(0,delay_var+1) #weird behavior, where delay_var=1 always returns 0
        self.dc_rx = 0 if dc == 0 else np.random.normal(scale=dc) + np.random.normal(scale=dc)*1j #randomize dc offset
        self.dc_tx = 0 if dc == 0 else np.random.normal(scale=dc) + np.random.normal(scale=dc)*1j #randomize dc offset
        self.iq_imbal_tx = 1 if iq_imbal == 0 else 1 + np.random.normal(scale=iq_imbal) #randomize IQ imbalance
        self.iq_imbal_rx = 1 if iq_imbal == 0 else 1 + np.random.normal(scale=iq_imbal) #randomize IQ imbalance
        self.noise = noise       
        self.cfo = cfo
        self.paths = []
        self.path_delays = [0]
        self.num_taps=num_taps
        for i in range(num_taps):
            new_path = 10**((attn + np.random.normal(scale=attn_var))/20)
            if i > 0: new_path /= i*10**(tap_attn/20)  #increasingly attenuate additional paths
            if phase_shift: new_path *= np.exp(np.random.uniform(high=2*np.pi)*1j)
            self.paths.append(new_path)
            if i > 0: self.path_delays.append(np.random.randint(low=i,high=delay_spread+1)) #weird behavior, high never happens #could result in two of the same delays -- but that's ok
            
    def channelize(self,samps):
        '''Apply the channel to a buffer of samples.'''
        out = np.zeros(samps.shape[0]+self.delay+self.delay_spread,dtype=np.complex64)
        samps_c = np.copy(samps) #create copy so we don't alter original
        
        for i in range(self.num_taps):
            out[self.delay+self.path_delays[i]:self.delay+self.path_delays[i]+samps.shape[0]] += samps_c*self.paths[i] #apply path phase shift, attenuation, and delay
        out *= self.genCFO(out.shape[0], self.cfo)  #apply cfo #each device should have a different CFO!
        out += self.dc_tx #apply dc #more physically accurate to do it for each path, but end result is just another constant dc offset
        out.real *= self.iq_imbal_tx #apply iq imbalance -- we just do real, but it can be more or less than 1, so result is fine
        if self.noise is not None:
            out += np.random.normal(scale=10**(self.noise/20), size=out.shape[0]) + np.random.normal(scale=10**(self.noise/20), size=out.shape[0])*1.j #add noise
        return out[:samps.shape[0]]

    @staticmethod
    def genCFO(nsamps, cfo):
        return np.exp(np.array(np.arange(0,nsamps)).transpose()*1.j*cfo).astype(np.complex64) #*2j*np.pi #cfo is radians per sample

        
        
class Stream:
    '''Simple abstraction layer to keep track of channel IDs for the channel emulator.'''
    
    def __init__(self, chan_ids):
        #print(chan_ids)
        self.chan_ids = chan_ids
        self.chan_em = ChanEmu()
        
    def write(self, stream, buffs, numElems, flags=0, timeNs=0, timeoutUs=int(1e6)):
        for i,buff in enumerate(buffs):
            self.chan_em.write(buff[:numElems],self.chan_ids[i])
        return StreamReturn(numElems)
    def read(self, stream, buffs, numElems, flags=0, timeNs=0, timeoutUs=int(1e6)):
        for i,buff in enumerate(buffs):
            buff[:numElems] = self.chan_em.read(numElems,self.chan_ids[i])
        return StreamReturn(numElems)
    
class ChanEmu:
    '''
    Implements shared buffers for every TX "stream", as well as an NxN set of channels for every SDR radio interface.
    When an rx radio "reads" the channel, it channelizes every TX buffer, using its unique channel to that rx radio, then sums them.
    This implementation is lacking any notion of rate or timestamps.
    '''
    _instance = None

    def __new__(cls, bufsize=204800):
        '''Singleton pattern.'''
        if cls._instance is None:
            cls._instance = super(ChanEmu, cls).__new__(cls)
            cls._bufsize=bufsize
            cls._bufs = []
            cls._channels = [[Channel()]]
            cls.tx_gains = []
            cls.rx_gains = []
            #cls._buf = np.zeros(bufsize, dtype=np.complex64)
        return cls._instance
    
    def add_chan(cls):
        #right now we make every radio tx and rx, and add them on device creation
        #we could be more efficient by only creating channels when the stream is created, and only for tx or rx
        cls._bufs.append(np.zeros(cls._bufsize, dtype=np.complex64)) #one buffer per radio
        if len(cls._bufs) > 1: #awkwardly grow square list of lists of channels
            for c in cls._channels:
                c.append(Channel())
            cls._channels.append([Channel() for i in range(len(cls._channels)+1)])
        cls.tx_gains.append(0)
        cls.rx_gains.append(0)
        
    def read(cls, num, chan_id):
        out = np.zeros(num,dtype=np.complex64)
        for i , (c,b) in enumerate(zip(cls._channels[chan_id],cls._bufs)):  #channelize and sum all buffers
            if i != chan_id: out += c.channelize(b[:num])  #assume you can't rx your own tx
        out *= 10**(cls.rx_gains[chan_id]/20) #apply rx gain
        out.real *= cls._channels[chan_id][chan_id].iq_imbal_rx #apply iq imbalance -- we just do real, but it can be more or less than 1, so result is fine #apply here so that gains don't affect it.
        out += cls._channels[chan_id][chan_id].dc_rx #apply dc #typically happens after amplification
        return clip(out) #clip after RX gain.  The rx gain doesn't do much in this sim, since it scales everything.  We may need to add another noise stage or quantization lower bound to be more realistic.
    
    def write(cls, vals, chan_id):
        cls._bufs[chan_id][:vals.shape[0]] = clip(vals)*10**(cls.tx_gains[chan_id]/20) #clip before TX gain
        
    def reset(cls):
        for buf in cls._bufs:
            buf[:] = 0

class StreamReturn:
    ''' Simple class to mimic stream status return syntax. '''
    def __init__(self, ret):
        self.ret = ret

class Device:
    ''' 
    Oversimplified virtual SoapySDR device to simply read/write stream operations.
    It has no notion of rate or timestamps, and doesn't mimic functionality, just syntax.
    '''
    
    _NEXT_CHAN = 0 #keep unique device identifiers for the channel emulation
    _TX_GAIN_RANGE = [-50,50]
    _RX_GAIN_RANGE = [-50,50]
    
    def __init__(self, *argv, num_chan=2):
        #to replicate this properly, we should be able to take a list of args in and return a list of devices.
        self.rate = None
        self.freq = None
        self.bandwidth = None
        self.chan_em = ChanEmu()
        self.num_chan = num_chan
        self.chan_ids = range(self._NEXT_CHAN,self._NEXT_CHAN+num_chan) 
        Device._NEXT_CHAN += num_chan #this will increment the chan_ids for the next instance
        for i in range(num_chan): self.chan_em.add_chan() #add these channels to the channel emulator
        self.serial = argv[0]['serial'] + '-SIM' if 'serial' in argv[0] else 'NoSerial-SIM'
        self.hw_info = { 'driver' : '2020.11.0.1-f0f0f0',
                         'firmware' : '2020.11.0.1-f0f0f0',
                         'fpga' : '2020.11.0.1-f0f0f0',
                         'frontend' : 'SIM',
                         'revision' : 'Simulated-1.00-MIMO',
                         'serial' : self.serial,
                         }
        
    
    def getSampleRate(self, direction, channel):
        return self.rate
    def setSampleRate(self, direction, channel, rate):
        self.rate = rate
    def getBandwidth(self, direction, channel):
        return self.bandwidth
    def setBandwidth(self, direction, channel, bw):
         self.bandwidth = bw
    def getGain(self, direction, channel, *argv, **kwargs):
        if direction == SOAPY_SDR_TX:
            return  self.chan_em.tx_gains[self.chan_ids[channel]]
        if direction == SOAPY_SDR_RX:
            return  self.chan_em.rx_gains[self.chan_ids[channel]]
    def getGainRange(self, direction, channel, *argv, **kwargs):
        if direction == SOAPY_SDR_TX:
            return  self._TX_GAIN_RANGE
        if direction == SOAPY_SDR_RX:
            return  self._RX_GAIN_RANGE
    def setGain(self, direction, channel, value, *argv, **kwargs):
        #Note: we have the ChanEmu keep track of gains since there is a layer of indirection in the 
        #Stream -- when we write stream, we actually don't know which channel is being written to, 
        #so it is easier to consider the gain as part of the channel.
        if direction == SOAPY_SDR_TX:
            self.chan_em.tx_gains[self.chan_ids[channel]] = np.clip(value, self._TX_GAIN_RANGE[0], self._TX_GAIN_RANGE[1])
        if direction == SOAPY_SDR_RX:
            self.chan_em.rx_gains[self.chan_ids[channel]] = np.clip(value, self._RX_GAIN_RANGE[0], self._RX_GAIN_RANGE[1])
    def getFrequency(self, direction, channel, name='RF'):
        return self.freq
    def setFrequency(self, direction, channel, name, frequency):
        self.freq = frequency
    def getAntenna(self, *argv, **kwargs):
        return
    def setAntenna(self, *argv, **kwargs):
        return
    def getDCOffsetMode(self, *argv, **kwargs):
        return
    def setDCOffsetMode(self, *argv, **kwargs):
        return
    def getHardwareInfo(self, *argv, **kwargs):
        return self.hw_info
    def setupStream(self, direction, packing_form, channels, kwargs):
        return Stream([self.chan_ids[i] for i in channels])
    def activateStream(self, *argv, **kwargs):
        return
    #these can be static...
    def writeStream(self, stream, buffs, numElems, flags=0, timeNs=0, timeoutUs=int(1e6)):            
        return stream.write(stream, buffs, numElems, flags, timeNs, timeoutUs)
    def readStream(self, stream, buffs, numElems, flags=0, timeNs=0, timeoutUs=int(1e6)):
        return stream.read(stream, buffs, numElems, flags, timeNs, timeoutUs)
    def deactivateStream(self, *argv, **kwargs):
        return
    def closeStream(self, *argv, **kwargs):
        return
    def readSetting(self, *argv, **kwargs):
        return
    def writeSetting(self, *argv, **kwargs):
        return
    def readRegister(self, *argv, **kwargs):
        return
    def writeRegister(self, *argv, **kwargs):
        return
    def getHardwareTime(self, *argv, **kwargs):
        return 0
    def setHardwareTime(self, *argv, **kwargs):
        return
    def listSensors(self, *argv, **kwargs):
        return
    def readSensor(self, *argv, **kwargs):
        return

    #generated using:
    #method_list = [func for func in dir(SoapySDR.Device) if callable(getattr(SoapySDR.Device, func))]
    #for m in method_list:
    #    print('    def ' + m + '(self, *argv, **kwargs):\n        return') 
    #import inspect
    #for m in method_list:
    #    inspect.getfullargspec(getattr(SoapySDR.Device,m)) #doesn't work because of the way SWIG bindings are set apparently

    def acquireReadBuffer(self, *argv, **kwargs):
        return
    def acquireWriteBuffer(self, *argv, **kwargs):
        return
    def close(self, *argv, **kwargs):
        return
    def getBandwidthRange(self, *argv, **kwargs):
        return
    def getChannelInfo(self, *argv, **kwargs):
        return
    def getClockSource(self, *argv, **kwargs):
        return
    def getDCOffset(self, *argv, **kwargs):
        return
    def getDirectAccessBufferAddrs(self, *argv, **kwargs):
        return
    def getDriverKey(self, *argv, **kwargs):
        return
    def getFrequencyArgsInfo(self, *argv, **kwargs):
        return
    def getFrequencyCorrection(self, *argv, **kwargs):
        return
    def getFrequencyRange(self, *argv, **kwargs):
        return
    def getFrontendMapping(self, *argv, **kwargs):
        return
    def getFullDuplex(self, *argv, **kwargs):
        return
    def getGainMode(self, *argv, **kwargs):
        return
    def getHardwareKey(self, *argv, **kwargs):
        return
    def getIQBalance(self, *argv, **kwargs):
        return
    def getMasterClockRate(self, *argv, **kwargs):
        return
    def getMasterClockRates(self, *argv, **kwargs):
        return
    def getNativeStreamFormat(self, *argv, **kwargs):
        return
    def getNumChannels(self, *argv, **kwargs):
        return
    def getNumDirectAccessBuffers(self, *argv, **kwargs):
        return
    def getSampleRateRange(self, *argv, **kwargs):
        return
    def getSensorInfo(self, *argv, **kwargs):
        return
    def getSettingInfo(self, *argv, **kwargs):
        return
    def getStreamArgsInfo(self, *argv, **kwargs):
        return
    def getStreamFormats(self, *argv, **kwargs):
        return
    def getStreamMTU(self, *argv, **kwargs):
        return
    def getTimeSource(self, *argv, **kwargs):
        return
    def hasDCOffset(self, *argv, **kwargs):
        return
    def hasDCOffsetMode(self, *argv, **kwargs):
        return
    def hasFrequencyCorrection(self, *argv, **kwargs):
        return
    def hasGainMode(self, *argv, **kwargs):
        return
    def hasHardwareTime(self, *argv, **kwargs):
        return
    def hasIQBalance(self, *argv, **kwargs):
        return
    def listAntennas(self, *argv, **kwargs):
        return
    def listBandwidths(self, *argv, **kwargs):
        return
    def listClockSources(self, *argv, **kwargs):
        return
    def listFrequencies(self, *argv, **kwargs):
        return
    def listGPIOBanks(self, *argv, **kwargs):
        return
    def listGains(self, *argv, **kwargs):
        return
    def listRegisterInterfaces(self, *argv, **kwargs):
        return
    def listSampleRates(self, *argv, **kwargs):
        return
    def listTimeSources(self, *argv, **kwargs):
        return
    def listUARTs(self, *argv, **kwargs):
        return
    def make(self, *argv, **kwargs):
        return
    def readGPIO(self, *argv, **kwargs):
        return
    def readGPIODir(self, *argv, **kwargs):
        return
    def readI2C(self, *argv, **kwargs):
        return
    def readRegisters(self, *argv, **kwargs):
        return
    def readSensorBool(self, *argv, **kwargs):
        return
    def readSensorFloat(self, *argv, **kwargs):
        return
    def readSensorInt(self, *argv, **kwargs):
        return
    def readSettingBool(self, *argv, **kwargs):
        return
    def readSettingFloat(self, *argv, **kwargs):
        return
    def readSettingInt(self, *argv, **kwargs):
        return
    def readStreamStatus(self, *argv, **kwargs):
        return
    def readStreamStatus__(self, *argv, **kwargs):
        return
    def readStream__(self, *argv, **kwargs):
        return
    def readUART(self, *argv, **kwargs):
        return
    def releaseReadBuffer(self, *argv, **kwargs):
        return
    def releaseWriteBuffer(self, *argv, **kwargs):
        return
    def setClockSource(self, *argv, **kwargs):
        return
    def setCommandTime(self, *argv, **kwargs):
        return
    def setDCOffset(self, *argv, **kwargs):
        return
    def setFrequencyCorrection(self, *argv, **kwargs):
        return
    def setFrontendMapping(self, *argv, **kwargs):
        return
    def setGainMode(self, *argv, **kwargs):
        return
    def setIQBalance(self, *argv, **kwargs):
        return
    def setMasterClockRate(self, *argv, **kwargs):
        return
    def setTimeSource(self, *argv, **kwargs):
        return
    def transactSPI(self, *argv, **kwargs):
        return
    def unmake(self, *argv, **kwargs):
        return
    def writeGPIO(self, *argv, **kwargs):
        return
    def writeGPIODir(self, *argv, **kwargs):
        return
    def writeI2C(self, *argv, **kwargs):
        return
    def writeRegisters(self, *argv, **kwargs):
        return
    def writeUART(self, *argv, **kwargs):
        return
