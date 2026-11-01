/* SPDX-License-Identifier: MIT */
/* OTR-4TS3-U1 FX3 firmware: shared definitions.
 * The vendor-request protocol must stay in sync with otr-userland
 * src/fx3_protocol.h (protocol v1, docs/design.md section 4). */
#ifndef OTR_FW_H
#define OTR_FW_H

#include "cyu3types.h"

#define OTR_PROTOCOL_VERSION    1
#define OTR_FW_VERSION_MAJOR    0
#define OTR_FW_VERSION_MINOR    1

/* USB identity (D-31: pid.codes test VID/PID during development) */
#define OTR_USB_VID             0x1209
#define OTR_USB_PID             0x0001

/* Vendor requests */
#define OTR_REQ_GET_INFO        0xB0
#define OTR_REQ_I2C_RUN         0xB1
#define OTR_REQ_I2C_RESULT      0xB2
#define OTR_REQ_GPIO            0xB3
#define OTR_REQ_FPGA_LOAD       0xB4
#define OTR_REQ_FPGA_REG        0xB5
#define OTR_REQ_STREAM          0xB6
#define OTR_REQ_FLASH_WRITE     0xB7    /* wIndex:wValue = address, <= 256 bytes within one page */
#define OTR_REQ_FLASH_READ      0xB8    /* wIndex:wValue = address, wLength <= 4096 */
#define OTR_REQ_FLASH_ERASE     0xB9    /* wIndex:wValue = 4 KiB sector address, no data; poll FLASH_STATUS */
#define OTR_REQ_FLASH_STATUS    0xBA    /* IN 1 byte: status register 1 (bit 0 = busy) */
#define OTR_REQ_MS_OS_20        0xBF    /* bMS_VendorCode in the BOS platform capability */

/* I2C program format (I2C_RUN data stage) */
#define OTR_I2C_OP_WRITE        0x01
#define OTR_I2C_OP_READ         0x02
#define OTR_I2C_OP_HEADER       4
#define OTR_I2C_MAX_PROGRAM     512
#define OTR_I2C_MAX_READ        512
#define OTR_I2C_CHANNELS        4

#define OTR_I2C_OK              0x00
#define OTR_I2C_NAK_ADDRESS     0x01
#define OTR_I2C_NAK_DATA        0x02
#define OTR_I2C_BUS_ERROR       0x03
#define OTR_I2C_BAD_PROGRAM     0x04
#define OTR_I2C_RESULT_HEADER   4

/* FPGA_LOAD stages (wValue) */
#define OTR_FPGA_LOAD_BEGIN     0
#define OTR_FPGA_LOAD_DATA      1
#define OTR_FPGA_LOAD_END       2
#define OTR_FPGA_LOAD_CHUNK     4096

/* GPIO request bit layout (wValue = value, wIndex = mask; IN returns 4 bytes) */
#define OTR_GPIO_CH_PWR(n)      (1u << (n))         /* bits 0..3 */
#define OTR_GPIO_CH_RST_N(n)    (1u << (4 + (n)))   /* bits 4..7, active low */
#define OTR_GPIO_LNA_BYPASS     (1u << 8)
#define OTR_GPIO_LNB_EN         (1u << 9)
#define OTR_GPIO_LED            (1u << 10)
#define OTR_GPIO_OUT_MASK       0x07FFu
#define OTR_GPIO_IN_CDONE       (1u << 16)
#define OTR_GPIO_IN_DC_IN       (1u << 17)

/* Streaming: GPIF thread 0 -> EP1 IN. DMA buffer size must equal the FPGA
 * gpif_sfifo_wr BUFW parameter (8192 words = 16 KiB, D-43). */
#define OTR_EP_TS               0x81
#define OTR_EP_TS_SOCKET        CY_U3P_UIB_SOCKET_CONS_1
#define OTR_DMA_BUF_SIZE        16384
#define OTR_DMA_BUF_COUNT       4
#define OTR_SS_BURST            16

/* I2C addresses on the FX3 bus */
#define OTR_I2C_ADDR_MUX        0x70    /* TCA9546A */

/* SPI boot flash (W25Q32JV, D-49) and its layout */
#define OTR_FLASH_SIZE          0x400000u
#define OTR_FLASH_PAGE          256
#define OTR_FLASH_SECTOR        4096u
#define OTR_FLASH_READ_MAX      4096
#define OTR_FLASH_FX3_IMAGE     0x000000u   /* FX3 boot image (elf2img output) */
#define OTR_FLASH_FPGA_SLOT     0x100000u   /* header {"OTRB", u32 length LE}, then the bitstream */
#define OTR_FLASH_FPGA_HDR      256u
#define OTR_FPGA_MAX_BITSTREAM  (160u * 1024u)  /* HX8K: 135100 bytes; must fit the DMA buffer area */

/* SPI clocks: flash and FPGA configuration share the bus (D-47, D-49) */
#define OTR_SPI_CONFIG_HZ       20000000u
#define OTR_SPI_FLASH_HZ        20000000u
#define OTR_SPI_REG_HZ          4000000u

/* Where the current FPGA configuration came from (GET_INFO byte 10) */
#define OTR_FPGA_SRC_NONE       0
#define OTR_FPGA_SRC_FLASH      1
#define OTR_FPGA_SRC_HOST       2

/* Module entry points */
void OtrUsbInit (void);
void OtrI2cInit (void);
uint8_t *OtrI2cRun (uint16_t channel, const uint8_t *program, uint16_t len, uint16_t *resultLen);
void OtrFlashInit (void);
CyBool_t OtrFlashRead (uint32_t addr, uint8_t *data, uint32_t len);
CyBool_t OtrFlashProgram (uint32_t addr, const uint8_t *data, uint16_t len);
CyBool_t OtrFlashErase (uint32_t addr);
uint8_t OtrFlashStatus (void);
const uint8_t *OtrFlashUid (void);
void OtrSpiSetClock (uint32_t hz);
void OtrGpioInit (void);
void OtrGpioSet (uint32_t value, uint32_t mask, CyBool_t *ok);
uint32_t OtrGpioGet (void);
void OtrFpgaInit (void);
CyBool_t OtrFpgaLoad (uint16_t stage, const uint8_t *data, uint16_t len);
CyBool_t OtrFpgaDone (void);
CyBool_t OtrFpgaBusy (void);
uint8_t OtrFpgaSource (void);
CyBool_t OtrFpgaAutoload (void);
CyBool_t OtrFpgaReg (CyBool_t write, uint8_t addr, uint32_t *value);
void OtrStreamInit (void);
CyBool_t OtrStreamSet (CyBool_t on);
CyBool_t OtrStreamConfigured (void);
void OtrStreamOnSetConf (CyBool_t superSpeed);
void OtrStreamOnReset (void);

#endif /* OTR_FW_H */
