% 	Simple SISO demo on SoapySDR for Matlab using SISO.py.
%   Note that this assumes that you have WinPyton 3.6.3 installed to C:\, and have its path
%   configured to find SISO.py.
%
% 	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
% 	INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
% 	PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
% 	FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
% 	OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
% 	DEALINGS IN THE SOFTWARE.
% 
% 	(c) 2018 info@skylarkwireless.com 

%clear all; clear; clear py; clear classes;  %I could never get py to clear quite right...
[version, executable, isloaded] = pyversion;
if ~isloaded
    pyversion C:\WinPython-64bit-3.6.3.0Qt5\python-3.6.3.amd64\python.exe
    py.print() %weird bug where py isn't loaded in an external script
end

rate = 7.68e6;
if ~exist('siso_sdr','var') %don't reload sdr everytime (and retune PLLs/Calibration)
    siso_sdr = py.SISO.SISO_SDR(rate, pyargs('txserial','0218', 'rxserial', '0197','freq',2450e6,'txGain',40,'rxGain',10)); 
end

if exist('timeDomainSig','var') %load custom signal if it exists.
    s = size(timeDomainSig);
    if s(2) == 1
        timeDomainSig = timeDomainSig.'/max(abs(timeDomainSig))/1.8;
    end
    x = siso_sdr.trx(real(timeDomainSig),imag(timeDomainSig));
else
    time = 0:(1/rate):2500/rate - 1/rate;
    frequency = 50e3;
    pilot_tone = [zeros(1,100), exp(sqrt(-1)*2*pi*frequency*time)*.5, zeros(1,100)];
    x = siso_sdr.trx(real(pilot_tone),imag(pilot_tone));
end

%hack to convert back to complex
rxData = double(py.array.array('d',py.numpy.nditer(py.numpy.real(x)))) + j*double(py.array.array('d',py.numpy.nditer(py.numpy.imag(x))));
figure; plot(real(rxData));
