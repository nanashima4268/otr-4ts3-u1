# fx3

CYUSB3014 firmware: GPIF II slave FIFO to USB3 bulk IN; vendor requests for I2C (via TCA9546A), GPIO, and iCE40 SPI configuration.
License: MIT (see ../LICENSES). The FX3 SDK libraries are proprietary, so firmware binaries are subject to the Cypress/Infineon license terms.

## Build environment (Docker)

1. Download the FX3 SDK for Linux from Infineon (an account may be required). Extract the firmware package inside it (`fx3_firmware_linux.tar.gz`) so that `~/opt/fx3sdk` directly contains `fw_build/`, `fw_lib/`, and `firmware/`.
2. `docker build -t otr-fx3 fx3/docker`
3. `docker run --rm -v ~/opt/fx3sdk:/opt/fx3sdk:ro -v "$PWD/fx3":/work otr-fx3 make`

The SDK is mounted, never copied into the image or the repository, because it is not redistributable.
