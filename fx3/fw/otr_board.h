/* SPDX-License-Identifier: MIT */
/* FX3 pin assignment for OTR-4TS3-U1.
 * PROVISIONAL: there is no schematic yet. With the GPIF bus at 16 bits
 * (D-39), GPIO 33..44 (DQ16..27 in 32-bit mode) are free. SPI uses
 * GPIO 53..56 and I2C uses the dedicated pins. Update this file together
 * with the schematic. */
#ifndef OTR_BOARD_H
#define OTR_BOARD_H

#define OTR_PIN_FPGA_CRESET_B   33   /* out, iCE40 CRESET_B */
#define OTR_PIN_FPGA_CDONE      34   /* in,  iCE40 CDONE */
#define OTR_PIN_CH_PWR0         35   /* out, per-channel LDO enable 0..3 (35..38) */
#define OTR_PIN_CH_RST_N0       39   /* out, per-channel demod/tuner reset 0..3 (39..42) */
#define OTR_PIN_LNA_BYPASS      43   /* out */
#define OTR_PIN_LNB_EN          44   /* out, DNP circuit (D-15) */
#define OTR_PIN_DC_IN_DET       45   /* in,  12 V DC input present (D-30) */
#define OTR_PIN_LED             57   /* out */

#endif /* OTR_BOARD_H */
