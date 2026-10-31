# FX3 firmware build environment.
# The FX3 SDK itself is not redistributable: download the Linux SDK (fx3_sdk_linux)
# from Infineon and mount it at /opt/fx3sdk (see ../README.md).
FROM ubuntu:22.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        gcc-arm-none-eabi libnewlib-arm-none-eabi make ca-certificates libusb-1.0-0-dev g++ \
    && rm -rf /var/lib/apt/lists/*
ENV FX3_INSTALL_PATH=/opt/fx3sdk \
    ARMGCC_INSTALL_PATH=/usr \
    ARMGCC_VERSION=10.3.1
WORKDIR /work
