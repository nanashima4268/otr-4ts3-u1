# host

Host software (D-40). It is built on [px4-userland](https://github.com/Khronos31/px4-userland) (C++, GPL-2.0), a user-space driver suite. In that suite, a daemon (`px4d`) owns the USB device, and clients (`px4-ts`, `px4ctl`) attach over IPC. It runs on Linux, macOS, Windows, and Android, with no kernel driver.

Plan: add an OTR-4TS3-U1 backend to px4-userland, made of an FX3 transport (vendor requests for I2C/GPIO/FPGA config, bulk IN for the tagged TS stream) and a model profile. The CXD2856ER/CXD2858ER frontend code is reused as is.

px4-userland v0.2.1 was verified on the reference board DTV02A-4TS-P (docs/reference/px4-userland-dtv02a-4ts-p.md).

License: GPL-2.0-only (see ../LICENSES).
