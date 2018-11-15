#!/usr/bin/python3
#
#	Demonstrate SoapySDR API capability as a vendor neutral abstraction layer for seamless interfacing with SDR devices.
#   Multiple SDRs from different vendors decode the physical cell id from an LTE frame transmitted by an Iris.
#
#	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#	INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
#	PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
#	FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#	OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#	DEALINGS IN THE SOFTWARE.
#
#	(c) info@skylarkwireless.com 2018

import sys

# lazy path addition for standard /usr/local install
try:
    import SoapySDR
except ImportError:
    sys.path.append('/usr/local/lib/python3/dist-packages')
import SoapySDR
from SoapySDR import *  # SOAPY_SDR_ constants
import numpy as np
import scipy as sp
import scipy.io as sio
from optparse import OptionParser
import time
import os
import math


def LTE_cellID_decoder_demo(iris_tx_ser, iris_rx_ser, usrp_rx_ser, lime_rx_ser, rtlsdr_rx_ser, bladerf_rx_ser):
    # Instantiate SoapySDR device objects for all SDRs
    iris_tx = SoapySDR.Device(dict(driver="iris", serial=iris_tx_ser))
    iris_rx = SoapySDR.Device(dict(driver="iris", serial=iris_rx_ser))
    usrp_rx = SoapySDR.Device(dict(driver="uhd", serial=usrp_rx_ser))
    lime_rx = SoapySDR.Device(dict(driver="lime", serial=lime_rx_ser))
    rtlsdr_rx = SoapySDR.Device(dict(driver="rtlsdr", serial=rtlsdr_rx_ser))
    bladerf_rx = SoapySDR.Device(dict(driver="bladerf", serial=bladerf_rx_ser))

    # Configure all SDRs
    centerFreq = 915e6
    bandwidth = 1.4e6  # We need only the middle 6 RBs to decode PSS ans SSS
    rate = 1.92e6

    ch = 0  # Just one channel for all SDRs

    # configure TX
    iris_tx.setFrequency(SOAPY_SDR_TX, ch, centerFreq)
    iris_tx.setBandwidth(SOAPY_SDR_TX, ch, bandwidth)
    iris_tx.setSampleRate(SOAPY_SDR_TX, ch, rate)
    iris_tx.setAntenna(SOAPY_SDR_TX, ch, "TRX")
    iris_tx.setGain(SOAPY_SDR_TX, ch, "PAD", 55)
    iris_tx.setGain(SOAPY_SDR_TX, ch, "IAMP", 55)

    # configure RXs
    for sdr in [iris_rx, usrp_rx, lime_rx, rtlsdr_rx, bladerf_rx]:
        sdr.setFrequency(SOAPY_SDR_RX, ch, centerFreq)
        sdr.setBandwidth(SOAPY_SDR_RX, ch, bandwidth)
        sdr.setSampleRate(SOAPY_SDR_RX, ch, rate)
        sdr.setDCOffsetMode(SOAPY_SDR_RX, ch, False)

    iris_rx.setAntenna(SOAPY_SDR_RX, ch, "RX")
    iris_rx.setGain(SOAPY_SDR_RX, ch, 35)

    usrp_rx.setAntenna(SOAPY_SDR_RX, ch, "RX2")
    usrp_rx.setGain(SOAPY_SDR_RX, ch, "ADC-digital", 3)  # range [0, 6, 0.5]
    usrp_rx.setGain(SOAPY_SDR_RX, ch, "ADC-fine", 0)  # range [0,0.5,0.05]
    usrp_rx.setGain(SOAPY_SDR_RX, ch, "PGA0", 25)  # range [0,31.5,0.5]

    lime_rx.setAntenna(SOAPY_SDR_RX, ch, "LNAH")
    lime_rx.setGain(SOAPY_SDR_RX, ch, "TIA", 10)
    lime_rx.setGain(SOAPY_SDR_RX, ch, "LNA", 25)

    rtlsdr_rx.setAntenna(SOAPY_SDR_RX, ch, "RX")
    rtlsdr_rx.setGain(SOAPY_SDR_RX, ch, "TUNER", 25)

    bladerf_rx.setAntenna(SOAPY_SDR_RX, ch, "RX")
    bladerf_rx.setGain(SOAPY_SDR_RX, ch, 38)

    # Transmit the LTE frame continuously using the replay buffer
    # LTE FDD downlink frame generated in MATLAB (1.4 MHz, Cell ID = 66)
    txwave = sio.loadmat('./lte_frames/txwave_14M_ID66.mat')['txwave_14M_ID66'].flatten()
    txwave = txwave.astype(np.complex64) * 0.25
    iris_txStream = iris_tx.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32, [0], {"REPLAY": 'true'})  # notice the replay
    flags = SOAPY_SDR_WAIT_TRIGGER | SOAPY_SDR_END_BURST
    iris_tx.activateStream(iris_txStream)
    sr_tx = iris_tx.writeStream(iris_txStream, [txwave], 19200, flags)
    print(sr_tx)
    iris_tx.writeSetting("TRIGGER_GEN", "")
    time.sleep(1)  # Wait fot things to settle

    # Initialize array for received samples for all receiving SDRs
    burstSize = 64 * 1024
    iris_waveRx = np.zeros(burstSize, dtype=np.complex64)
    usrp_waveRx = np.zeros(burstSize, dtype=np.complex64)
    lime_waveRx = np.zeros(burstSize, dtype=np.complex64)
    rtlsdr_waveRx = np.zeros(burstSize, dtype=np.complex64)
    bladerf_waveRx = np.zeros(burstSize, dtype=np.complex64)
    waveRxA = np.zeros(burstSize, dtype=np.complex64)

    # Setup receiving streams for receiving SDRs
    iris_rxStream = iris_rx.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [0])
    usrp_rxStream = usrp_rx.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [0])
    lime_rxStream = lime_rx.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [0])
    rtlsdr_rxStream = rtlsdr_rx.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [0])
    bladerf_rxStream = bladerf_rx.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [0], {"buflen": "65536", "buffers": "128"})

    # Activate all receiving streams
    for sdr in [iris_rx, usrp_rx, lime_rx]:
        sdr.activateStream(iris_rxStream, SOAPY_SDR_END_BURST, 0, burstSize)
    rtlsdr_rx.activateStream(rtlsdr_rxStream)
    bladerf_rx.activateStream(bladerf_rxStream)

    print("\n\n")
    sr_rx1 = iris_rx.readStream(iris_rxStream, [iris_waveRx], burstSize, timeoutUs=int(1e6))
    sio.savemat('./rcvd_IQsamples/rcvdSamples66_OTA_iris.mat', {'rcvdsamples': iris_waveRx})
    # print(sr_rx1)
    print("\nNo. of samples received from IRIS: {}".format(sr_rx1.ret))
    sr_rx2 = usrp_rx.readStream(usrp_rxStream, [usrp_waveRx], burstSize, timeoutUs=int(1e6))
    sio.savemat('./rcvd_IQsamples/rcvdSamples66_OTA_usrp.mat', {'rcvdsamples': usrp_waveRx})
    # print(sr_rx2)
    print("\nNo. of samples received from USRP: {}".format(sr_rx2.ret))
    sr_rx3 = lime_rx.readStream(lime_rxStream, [lime_waveRx], burstSize, timeoutUs=int(1e6))
    sio.savemat('./rcvd_IQsamples/rcvdSamples66_OTA_lime.mat', {'rcvdsamples': lime_waveRx})
    # print(sr_rx3)
    print("\nNo. of samples received from Lime: {}".format(sr_rx3.ret))

    print("\nClearing RTL-SDR buffers...")
    for i in range(10):
        rtlsdr_rx.readStream(rtlsdr_rxStream, [waveRxA], burstSize, timeoutUs=int(1e6))
    # print(sr_rx)
    print("\nRTL-SDR buffers cleared!")

    sr_rx4 = rtlsdr_rx.readStream(rtlsdr_rxStream, [rtlsdr_waveRx], burstSize, timeoutUs=int(1e6))
    sio.savemat('./rcvd_IQsamples/rcvdSamples66_OTA_rtlsdr.mat', {'rcvdsamples': rtlsdr_waveRx})
    # print(sr_rx4)
    print("\nNo. of samples received from RTL-SDR: {}".format(sr_rx4.ret))

    # Reading burst from bladeRF
    print("\nClearing bladeRF buffers...")
    for i in range(10):
        bladerf_rx.readStream(bladerf_rxStream, [waveRxA], burstSize, timeoutUs=int(1e6))
    # print(sr_rx)
    print("\nBladeRF buffers cleared!")

    sr_rx5 = bladerf_rx.readStream(bladerf_rxStream, [bladerf_waveRx], burstSize, timeoutUs=int(1e6))
    sio.savemat('./rcvd_IQsamples/rcvdSamples66_OTA_bladerf.mat', {'rcvdsamples': bladerf_waveRx})
    print("\nNumber of samples received from bladeRF: {}".format(sr_rx5.ret))
    # print(sr_rx5)

    # Closing streams
    # print("Closing all streams...")
    iris_rx.deactivateStream(iris_rxStream)
    iris_rx.closeStream(iris_rxStream)

    usrp_rx.deactivateStream(usrp_rxStream)
    usrp_rx.closeStream(usrp_rxStream)

    lime_rx.deactivateStream(lime_rxStream)
    lime_rx.closeStream(lime_rxStream)

    rtlsdr_rx.deactivateStream(rtlsdr_rxStream)
    rtlsdr_rx.closeStream(rtlsdr_rxStream)

    bladerf_rx.deactivateStream(bladerf_rxStream)
    bladerf_rx.closeStream(bladerf_rxStream)

    iris_tx.deactivateStream(iris_txStream)
    iris_tx.closeStream(iris_txStream)

    # End
    fft_size = 128
    cp_length = 9
    print("\nStopped receiving samples...\n\n")
    print("\nIRIS")
    print("-----------------------------")
    Nid_corr, subframeNo_rx = find_cellid_from_samples(iris_waveRx[5000:], fft_size, cp_length)
    print("Detected cell ID is: {}".format(Nid_corr))
    print("Subframe No.: {}".format(subframeNo_rx))

    print("\nUSRP")
    print("-----------------------------")
    Nid_corr, subframeNo_rx = find_cellid_from_samples(usrp_waveRx[5000:], fft_size, cp_length)
    print("Detected cell ID is: {}".format(Nid_corr))
    print("Subframe No.: {}".format(subframeNo_rx))

    print("\nLime")
    print("-----------------------------")
    Nid_corr, subframeNo_rx = find_cellid_from_samples(lime_waveRx, fft_size, cp_length)
    print("Detected cell ID is: {}".format(Nid_corr))
    print("Subframe No.: {}".format(subframeNo_rx))

    print("\nRTL-SDR")
    print("-----------------------------")
    Nid_corr, subframeNo_rx = find_cellid_from_samples(rtlsdr_waveRx, fft_size, cp_length)
    print("Detected cell ID is: {}".format(Nid_corr))
    print("Subframe No.: {}".format(subframeNo_rx))

    print("\nBladeRF")
    print("-----------------------------")
    Nid_corr, subframeNo_rx = find_cellid_from_samples(bladerf_waveRx, fft_size, cp_length)
    print("Detected cell ID is: {}".format(Nid_corr))
    print("Subframe No.: {}".format(subframeNo_rx))
    print("\n\n")

    return


def find_cellid_from_samples(rx_samples, FFT_SIZE, CP_LENGTH):
    """
    Decodes cell ID from directly received samples.
    :param rx_samples: vector of received IQ samples from SDR
    :param FFT_SIZE: 128 (PSS and SSS occupy the middle 6 RBs)
    :param CP_LENGTH: 9
    :return: cell ID and subframe No.
    """
    rx_samples = rx_samples - np.mean(rx_samples)
    corrs_pss, maxCorr_pss, pss_corr_lag, Nid2_corr = find_Nid2(rx_samples)

    cfo = estimate_cfo_cp(rx_samples, int(0))
    t = np.arange(len(rx_samples)) / 1.92e6
    rx_samples = np.multiply(rx_samples, np.exp(-1j * 2 * np.pi * cfo * t))
    Nid1_p = get_possible_Nids(Nid2_corr)
    SSSs = get_possible_sss(Nid1_p)

    rcvd_pss = np.fft.fftshift(sp.fft(rx_samples[pss_corr_lag - FFT_SIZE + 1:pss_corr_lag - FFT_SIZE + FFT_SIZE + 1]))
    tx_pss = np.fft.fftshift(
        np.concatenate((np.zeros(1), gen_lte_pss(Nid2_corr)[31:], np.zeros(65), gen_lte_pss(Nid2_corr)[0:31])))

    ch_est = np.divide(np.concatenate((rcvd_pss[33:33 + 31], rcvd_pss[33 + 32:65 + 31])),
                       np.concatenate((tx_pss[33:33 + 31], tx_pss[33 + 32:65 + 31])))

    rx_sss = np.fft.fftshift(sp.fft(rx_samples[
                                    pss_corr_lag - FFT_SIZE - FFT_SIZE - CP_LENGTH + 1:pss_corr_lag - FFT_SIZE - FFT_SIZE - CP_LENGTH + FFT_SIZE + 1]))
    rx_sss[33 + 31] = 0
    rx_sss_eq = np.real(
        np.divide(np.multiply(np.concatenate((rx_sss[33:33 + 31], rx_sss[33 + 32:65 + 31])), np.conj(ch_est)),
                  np.square(np.absolute(ch_est))))

    corrs, maxCorr, Nid1_corr, cellID, subframeNo_rx = find_Nid1(Nid2_corr, SSSs, rx_sss_eq)

    return cellID, subframeNo_rx


def find_Nid2(rx_samples):
    """
    Decodes the PSS to find Nid2
    :param rx_samples: vector of received IQ samples from SDR
    :return: Nid2 and correlation results
    """
    possible_pss_t = gen_possible_pss()
    corrs = np.zeros((np.size(possible_pss_t[:, 1]), np.size(possible_pss_t[1, :]) + np.size(rx_samples) - 1),
                     dtype=np.complex64)

    for i in range(np.size(corrs[:, 1])):
        corrs[i, :] = abs(np.correlate(rx_samples, possible_pss_t[i, :], 'full'))

    maxCorrs = np.amax(corrs, 1)
    maxCorr = np.amax(maxCorrs)
    Nid2_corr = np.argmax(maxCorrs)
    corr_lag = np.argmax(corrs[Nid2_corr, :])

    return corrs, maxCorr, corr_lag, Nid2_corr


def gen_possible_pss():
    """
    Generates all possible PSS sequences in time domain.
    :return: matrix of all possible PSS sequences in time domain
    """
    PSSs = np.zeros((3, FFT_SIZE)) + 1j * np.zeros((3, FFT_SIZE))
    for i in range(3):
        PSSs[i, :] = sp.ifft(np.concatenate((np.zeros(1), gen_lte_pss(i)[31:], np.zeros(65), gen_lte_pss(i)[0:31])))

    return PSSs


def estimate_cfo_cp(rx_samples, timeOffset):
    """
    Corrects CFO using Cyclic Prefix (CP)
    :param rx_samples: vector of received IQ samples from SDR
    :param timeOffset: marks start of frame
    :return: an estimate of the CFO
    """
    tSample = 1 / 15e3
    slotSamples = 960  # No. of samples in a slot

    symbols_starts = np.array([138, 275, 412, 549, 686, 823, 960], dtype=int)

    rx_samples = rx_samples[timeOffset:]

    arm1 = rx_samples[:-128]
    arm2 = rx_samples[128:]

    cp_corr = np.multiply(arm1, np.conj(arm2))
    cp_corr_MA = np.convolve(cp_corr, np.ones(9))[9 - 1:]
    cp_corr_avg = cp_corr_MA[:(np.fix(len(cp_corr_MA) / slotSamples) * slotSamples).astype(int)]

    slotsNo = (len(cp_corr_avg) // slotSamples)

    freq_ind = []

    for i in range(1, slotsNo + 1):
        for start in symbols_starts:
            freq_ind.append(slotSamples * (i - 1) + start)

    freq_ind = np.array(freq_ind[:-1])

    estimates = []
    for add in range(4, 9):
        estimates.append(cp_corr[freq_ind + add])

    estimates = np.concatenate(tuple(estimates))

    cfo_est = -np.angle(np.mean(estimates)) / (2 * np.pi * tSample)

    return cfo_est


def get_possible_Nids(Nid2):
    """
    Gets all possible cell identities (168) after decoding only the PSS
    :param Nid2: From decoding the PSS (identity within the physical layer cell group)
    :return: vector of possible cell identities
    """
    Nid1_p = np.zeros(168)

    for i in range(168):
        Nid1_p[i] = 3 * i + Nid2

    return Nid1_p.astype(int)


def get_possible_sss(Nid1_p):
    """
    Gets all possible SSS sequences corresponding to all possible cell identities (168) after decoding only the PSS
    :param Nid1_p: all possible cell identities (168) after decoding only the PSS
    :return: a matrix of all possible SSSs sequences
    """
    SSSs = np.zeros((len(Nid1_p) * 2, 62))

    for i in range(np.size(SSSs[:, 1])):
        SSSs[i, :] = gen_sss_d(Nid1_p[np.mod(i, len(Nid1_p))], (i >= 168) * 5)

    return SSSs


def gen_lte_genNid12(Nid):
    if Nid not in range(504):
        raise ValueError
    else:
        Nid2 = np.mod(Nid, 3)
        Nid1 = (Nid - Nid2) // 3
        return Nid1, Nid2


def gen_sss_d(Nid, subframeNo):
    """
    Generates SSS sequence given the cell ID and subframe No.
    :param Nid: cell ID
    :param subframeNo: subframe number (0 or 5) -- FDD Only
    :return:
    """
    Nid1, Nid2 = gen_lte_genNid12(Nid)
    m0, m1 = gen_sss_m0m1(Nid1)
    s0_m0, s1_m1 = gen_sss_s01(m0, m1)
    c0, c1 = gen_sss_c01(Nid2)
    z1_m0, z1_m1 = gen_sss_z01(m0, m1)

    d = np.zeros(31 * 2)

    if subframeNo == 0:

        for n in range(31):
            d[2 * n] = s0_m0[n] * c0[n]
            d[2 * n + 1] = s1_m1[n] * c1[n] * z1_m0[n]

    elif subframeNo == 5:

        for n in range(31):
            d[2 * n] = s1_m1[n] * c0[n]
            d[2 * n + 1] = s0_m0[n] * c1[n] * z1_m1[n]


    else:

        raise ValueError

    return d


def gen_sss_m0m1(Nid1):
    """
    See 6.11.2.1 from ETSI 36.211
    """
    m0_vec = np.concatenate(
        (np.arange(30), np.arange(29), np.arange(28), np.arange(27), np.arange(26), np.arange(25), np.arange(3)))
    m1_vec = np.concatenate((np.arange(1, 31), np.arange(2, 31), np.arange(3, 31), np.arange(4, 31), np.arange(5, 31),
                             np.arange(6, 31), np.arange(7, 10)))

    return m0_vec[Nid1], m1_vec[Nid1]


def gen_sss_s01(m0, m1):
    """
    See 6.11.2.1 from ETSI 36.211
    """
    # Generate x 6.11.2.1 from ETSI 36.211
    x = np.zeros(31)
    x[4] = 1
    for i in range(5, 31):
        x[i] = np.logical_xor(x[i - 3], x[i - 5])

    # Generate s_tilde 6.11.2.1 from ETSI 36.211
    s_tilde = 1 - 2 * x

    # Generate s0_m0 and s1_m1
    s0_m0 = np.zeros(31)
    s1_m1 = np.zeros(31)

    for n in range(31):
        s0_m0[n] = s_tilde[np.mod(n + m0, 31)]
        s1_m1[n] = s_tilde[np.mod(n + m1, 31)]

    return (s0_m0, s1_m1)


def gen_sss_c01(Nid2):
    """
    See 6.11.2.1 from ETSI 36.211
    """
    # Generate x 6.11.2.1 from ETSI 36.211
    x = np.zeros(31)
    x[4] = 1
    for i in range(5, 31):
        x[i] = np.logical_xor(x[i - 2], x[i - 5])

    # Generate c_tilde 6.11.2.1 from ETSI 36.211
    c_tilde = 1 - 2 * x

    # Generate c0 and c1
    c0 = np.zeros(31)
    c1 = np.zeros(31)

    for n in range(31):
        c0[n] = c_tilde[np.mod(n + Nid2, 31)]
        c1[n] = c_tilde[np.mod(n + Nid2 + 3, 31)]

    return c0, c1


def gen_sss_z01(m0, m1):
    """
    See 6.11.2.1 from ETSI 36.211
    """
    # Generate x 6.11.2.1 from ETSI 36.211
    x = np.zeros(31)
    x[4] = 1
    for i in range(5, 31):
        x[i] = np.mod(x[i - 1] + x[i - 3] + x[i - 4] + x[i - 5], 2)

    # Generate s_tilde 6.11.2.1 from ETSI 36.211
    z_tilde = 1 - 2 * x

    # Generate s0_m0 and s1_m1
    z1_m0 = np.zeros(31)
    z1_m1 = np.zeros(31)

    for n in range(31):
        z1_m0[n] = z_tilde[np.mod(n + np.mod(m0, 8), 31)]
        z1_m1[n] = z_tilde[np.mod(n + np.mod(m1, 8), 31)]

    return z1_m0, z1_m1


def gen_lte_pss(Nid2):
    """
    Generates the PSS sequence given Nid2 (identity within the physical layer cell identity group)
    :param Nid2: identity within the physical layer cell identity group (0, 1, 2)
    :return: PSS sequence for the given Nid2
    """
    if Nid2 == 0:
        root = 25
    elif Nid2 == 1:
        root = 29
    elif Nid2 == 2:
        root = 34
    else:
        raise ValueError

    return np.concatenate((np.exp(-1j * np.pi * root * np.multiply(np.arange(31), np.arange(1, 32)) / 63),
                           np.exp(-1j * np.pi * root * np.multiply(np.arange(32, 63), np.arange(33, 64)) / 63)))


def find_Nid1(Nid2, SSSs, fftOP_IQ):
    """
    Decodes the SSS using post-FFT correlation
    :param Nid2: identity within the physical layer cell identity group (0, 1, 2)
    :param SSSs: a matrix of all possible SSS sequences
    :param fftOP_IQ: FFT output (frequency domain samples)
    :return: cell ID and subframe No.
    """
    corrs = np.zeros((np.size(SSSs[:, 1]), np.size(SSSs[1, :]) * 2 - 1))

    for i in range(np.size(corrs[:, 1])):
        corrs[i, :] = np.correlate(fftOP_IQ, SSSs[i, :], 'full')

    maxCorrs = np.amax(corrs, 1)
    maxCorr = np.amax(maxCorrs)
    secCellID = np.mod(np.argmax(maxCorrs), 168)
    cellID = (3 * secCellID + Nid2).astype(int)
    subframeNo = (np.argmax(maxCorrs) >= 168) * 5

    return corrs, maxCorr, secCellID, cellID, subframeNo


def main():
    parser = OptionParser()
    parser.add_option("--iris_tx_ser", type="string", dest="iris_tx_ser", help="Transmitting IRIS serial", default="")
    parser.add_option("--iris_rx_ser", type="string", dest="iris_rx_ser", help="Receiving IRIS serial", default="")
    parser.add_option("--usrp_rx_ser", type="string", dest="usrp_rx_ser", help="Receiving USRP serial", default="")
    parser.add_option("--lime_rx_ser", type="string", dest="lime_rx_ser", help="Receiving Lime serial", default="")
    parser.add_option("--rtlsdr_rx_ser", type="string", dest="rtlsdr_rx_ser", help="Receiving RTL-SDR serial",
                      default="")
    parser.add_option("--bladerf_rx_ser", type="string", dest="bladerf_rx_ser", help="Receiving BladeRF serial",
                      default="")
    (options, args) = parser.parse_args()
    LTE_cellID_decoder_demo(
        iris_tx_ser=options.iris_tx_ser,
        iris_rx_ser=options.iris_rx_ser,
        usrp_rx_ser=options.usrp_rx_ser,
        lime_rx_ser=options.lime_rx_ser,
        rtlsdr_rx_ser=options.rtlsdr_rx_ser,
        bladerf_rx_ser=options.bladerf_rx_ser
    )


if __name__ == '__main__': main()
