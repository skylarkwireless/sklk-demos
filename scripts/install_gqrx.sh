#!/bin/sh
#   This is an *example* script of how to setup GQRX, a spectrum analyzer, for use with Iris
#   on Ubuntu 18.04.  You should modify based on what you already have installed.
#
#   This script requires SoapySDR to be installed, we suggest using the install_soapy.sh
#   script provided in sklk-soapyiris/utils.
#
#   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#   INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
#   PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
#   FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#   OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#   DEALINGS IN THE SOFTWARE.
#
#   (c) info@skylarkwireless.com 2019

SoapySDRUtil -i |grep Iris
if [[ $? != 0 ]]; then
    echo "SoapySDR with Iris support not found.  Please run install_soapy.sh from sklk-soapyiris/utils."
    exit 1
fi

sudo apt update

#on 18.04 this is all that is needed (perhaps in addition to what is installed with install_soapy.sh)
sudo apt install -y qtbase5-dev libqt5svg5-dev gnuradio libpulse-dev

#repo version is outdated
#sudo apt install -y gqrx-sdr

mkdir gqrx_build
cd gqrx_build

# I don't think osmo should be required to build gqrx, but apparently it is (maybe just a bug in their cmake...).
# While osmo is in the official repos, it doesn't seem to work correctly
#sudo apt install -y osmo-sdr
echo "Building and Installing gr-OsmoSDR"
git clone git://git.osmocom.org/gr-osmosdr
cd gr-osmosdr
mkdir build
cd build
cmake ..
make -j
sudo make install
cd ../..

# While gqrx is in the official repos, it does not support SoapySDR by default.
#sudo apt install -y gqrx-sdr 
echo "Building and installing gqrx"
git clone https://github.com/csete/gqrx.git
cd gqrx
mkdir build
cd build
cmake ..
make -j
sudo make install
cd ../..

cd ..

sudo ldconfig


echo '
To run use: "gqrx", then simply select your Iris from the dropdown list. 
Make sure to set the sample rate (e.g., input frequency: 30000000) and bandwidth.
To initialize correctly you have to set the LNB LO to something (e.g., LNB LO: 200 MHz).
After you set the carrier frequency, you should go back to the input controls tab and LNB LO to 0.
You may need to select the antenna under input controls.

Hit the play button to start.



If your Iris does not appear in the list, try closing, running "SoapySDRUtil --find", verifying your Iris is found, then running again.
Also, make sure "soapy" shows up as a supported device when starting.'

exit


#on older versions of Ubuntu you may need to compile gnuradio from source, here is an example:
echo "Installing dependencies. (May not be comprehensive.)"
sudo apt install -y  git cmake build-essential libpython-dev python-numpy python3-numpy swig avahi-daemon libavahi-client-dev qtbase5-dev qtdeclarative5-dev libqt5svg5-dev libpulse-dev 

#While gnuradio is in the official repos, Osmo needs a later version on 16.04.
sudo apt install -y gnuradio
git clone --recursive https://github.com/gnuradio/gnuradio.git
cd gnuradio
#change to tag you want (latest osmo needs 3.7.10 or later)
git checkout maint-3.8
mkdir build
cd build
cmake ..
make -j
sudo make install
cd ../..




