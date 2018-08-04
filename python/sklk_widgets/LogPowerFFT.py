########################################################################
## Log power FFT for plotting
########################################################################
import numpy as np
import math
import scipy.signal

def LogPowerFFT(samps, peak=1.0, reorder=True, window=None):
    """
    Calculate the log power FFT bins of the complex samples.
    @param samps numpy array of complex samples
    @param peak maximum value of a sample (floats are usually 1.0, shorts are 32767)
    @param reorder True to reorder so the DC bin is in the center
    @param window function or None for default flattop window
    @return an array of real values FFT power bins
    """
    size = len(samps)
    numBins = size

    #scale by dividing out the peak, full scale is 0dB
    scaledSamps = samps/peak

    #calculate window
    if not window: window = scipy.signal.hann
    windowBins = window(size)
    windowPower = math.sqrt(sum(windowBins**2)/size)

    #apply window
    windowedSamps = np.multiply(windowBins, scaledSamps)

    #window and fft gain adjustment
    gaindB = 20*math.log10(size) + 20*math.log10(windowPower)

    #take fft
    fftBins = np.abs(np.fft.fft(windowedSamps))
    fftBins = np.maximum(fftBins, 1e-20) #clip
    powerBins = 20*np.log10(fftBins) - gaindB

    #bin reorder
    if reorder:
        idx = np.argsort(np.fft.fftfreq(len(powerBins)))
        powerBins = powerBins[idx]

    return powerBins
