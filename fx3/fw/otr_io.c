/* SPDX-License-Identifier: MIT */
/* OTR-4TS3-U1 FX3 firmware: GPIO, the I2C program executor, the boot EEPROM. */
#include "cyu3system.h"
#include "cyu3os.h"
#include "cyu3error.h"
#include "cyu3gpio.h"
#include "cyu3i2c.h"
#include "otr_fw.h"
#include "otr_board.h"

/* ---------------- GPIO ---------------- */

static uint32_t otrGpioOut;   /* logical output state, OTR_GPIO_* bits */

static void OtrPinOut (uint8_t pin, CyBool_t value)
{
    CyU3PGpioSimpleConfig_t cfg;

    CyU3PMemSet ((uint8_t *)&cfg, 0, sizeof (cfg));
    cfg.outValue    = value;
    cfg.driveLowEn  = CyTrue;
    cfg.driveHighEn = CyTrue;
    cfg.inputEn     = CyFalse;
    cfg.intrMode    = CY_U3P_GPIO_NO_INTR;
    CyU3PGpioSetSimpleConfig (pin, &cfg);
}

static void OtrPinIn (uint8_t pin)
{
    CyU3PGpioSimpleConfig_t cfg;

    CyU3PMemSet ((uint8_t *)&cfg, 0, sizeof (cfg));
    cfg.inputEn  = CyTrue;
    cfg.intrMode = CY_U3P_GPIO_NO_INTR;
    CyU3PGpioSetSimpleConfig (pin, &cfg);
}

static CyBool_t OtrPinRead (uint8_t pin)
{
    CyBool_t v = CyFalse;
    CyU3PGpioSimpleGetValue (pin, &v);
    return v;
}

void OtrGpioInit (void)
{
    CyU3PGpioClock_t clk;
    uint8_t i;

    CyU3PMemSet ((uint8_t *)&clk, 0, sizeof (clk));
    clk.fastClkDiv = 2;
    clk.slowClkDiv = 0;
    clk.simpleDiv  = CY_U3P_GPIO_SIMPLE_DIV_BY_2;
    clk.clkSrc     = CY_U3P_SYS_CLK;
    clk.halfDiv    = 0;
    CyU3PGpioInit (&clk, NULL);

    /* Safe defaults: every channel powered down and held in reset, LNB off. */
    for (i = 0; i < OTR_I2C_CHANNELS; i++) {
        OtrPinOut (OTR_PIN_CH_PWR0 + i, CyFalse);
        OtrPinOut (OTR_PIN_CH_RST_N0 + i, CyFalse);
    }
    OtrPinOut (OTR_PIN_LNA_BYPASS, CyFalse);
    OtrPinOut (OTR_PIN_LNB_EN, CyFalse);
    OtrPinOut (OTR_PIN_LED, CyFalse);
    OtrPinOut (OTR_PIN_FPGA_CRESET_B, CyFalse);   /* FPGA held in reset until loaded */
    OtrPinIn (OTR_PIN_FPGA_CDONE);
    OtrPinIn (OTR_PIN_DC_IN_DET);
    otrGpioOut = 0;
}

void OtrGpioSet (uint32_t value, uint32_t mask, CyBool_t *ok)
{
    uint32_t next = (otrGpioOut & ~mask) | (value & mask);
    uint8_t i;

    *ok = CyFalse;
    if ((mask & ~OTR_GPIO_OUT_MASK) != 0)
        return;
    /* LNB power only with the external DC input present (D-30). */
    if ((next & OTR_GPIO_LNB_EN) && !OtrPinRead (OTR_PIN_DC_IN_DET))
        return;
    for (i = 0; i < OTR_I2C_CHANNELS; i++) {
        CyU3PGpioSetValue (OTR_PIN_CH_PWR0 + i, (next & OTR_GPIO_CH_PWR (i)) ? CyTrue : CyFalse);
        CyU3PGpioSetValue (OTR_PIN_CH_RST_N0 + i, (next & OTR_GPIO_CH_RST_N (i)) ? CyTrue : CyFalse);
    }
    CyU3PGpioSetValue (OTR_PIN_LNA_BYPASS, (next & OTR_GPIO_LNA_BYPASS) ? CyTrue : CyFalse);
    CyU3PGpioSetValue (OTR_PIN_LNB_EN, (next & OTR_GPIO_LNB_EN) ? CyTrue : CyFalse);
    CyU3PGpioSetValue (OTR_PIN_LED, (next & OTR_GPIO_LED) ? CyTrue : CyFalse);
    otrGpioOut = next;
    *ok = CyTrue;
}

uint32_t OtrGpioGet (void)
{
    uint32_t v = otrGpioOut;
    if (OtrPinRead (OTR_PIN_FPGA_CDONE))
        v |= OTR_GPIO_IN_CDONE;
    if (OtrPinRead (OTR_PIN_DC_IN_DET))
        v |= OTR_GPIO_IN_DC_IN;
    return v;
}

/* ---------------- I2C ---------------- */

static uint8_t otrI2cResult[OTR_I2C_RESULT_HEADER + OTR_I2C_MAX_READ] __attribute__ ((aligned (32)));
static int16_t otrMuxChannel = -1;

void OtrI2cInit (void)
{
    CyU3PI2cConfig_t cfg;

    CyU3PI2cInit ();
    CyU3PMemSet ((uint8_t *)&cfg, 0, sizeof (cfg));
    cfg.bitRate    = 400000;
    cfg.isDma      = CyFalse;
    cfg.busTimeout = 0xFFFFFFFF;
    cfg.dmaTimeout = 0xFFFF;
    CyU3PI2cSetConfig (&cfg, NULL);
}

static CyU3PReturnStatus_t OtrI2cWrite (uint8_t addr, const uint8_t *data, uint16_t len)
{
    CyU3PI2cPreamble_t pre;

    pre.buffer[0] = (uint8_t)(addr << 1);
    pre.length    = 1;
    pre.ctrlMask  = 0;
    if (len == 0)   /* address-only probe */
        return CyU3PI2cTransmitBytes (&pre, NULL, 0, 0);
    return CyU3PI2cTransmitBytes (&pre, (uint8_t *)data, len, 0);
}

static CyU3PReturnStatus_t OtrI2cRead (uint8_t addr, uint8_t *data, uint16_t len)
{
    CyU3PI2cPreamble_t pre;

    pre.buffer[0] = (uint8_t)((addr << 1) | 1);
    pre.length    = 1;
    pre.ctrlMask  = 0;
    return CyU3PI2cReceiveBytes (&pre, data, len, 0);
}

/* Write then read with a repeated start (register read), when the write fits
 * the 8-byte preamble: {addr|W, wdata..., addr|R}. */
static CyU3PReturnStatus_t OtrI2cWriteRead (uint8_t addr, const uint8_t *wdata, uint16_t wlen,
                                            uint8_t *rdata, uint16_t rlen)
{
    CyU3PI2cPreamble_t pre;
    uint16_t i;

    pre.buffer[0] = (uint8_t)(addr << 1);
    for (i = 0; i < wlen; i++)
        pre.buffer[1 + i] = wdata[i];
    pre.buffer[1 + wlen] = (uint8_t)((addr << 1) | 1);
    pre.length   = (uint8_t)(wlen + 2);
    pre.ctrlMask = (uint16_t)(1u << wlen);   /* start condition after the last write byte */
    return CyU3PI2cReceiveBytes (&pre, rdata, rlen, 0);
}

static CyBool_t OtrMuxSelect (uint16_t channel)
{
    uint8_t v = (uint8_t)(1u << channel);

    if (otrMuxChannel == (int16_t)channel)
        return CyTrue;
    if (OtrI2cWrite (OTR_I2C_ADDR_MUX, &v, 1) != CY_U3P_SUCCESS) {
        otrMuxChannel = -1;
        return CyFalse;
    }
    otrMuxChannel = (int16_t)channel;
    return CyTrue;
}

/* Executes an I2C program (see otr_fw.h). Returns the I2C_RESULT buffer. */
uint8_t *OtrI2cRun (uint16_t channel, const uint8_t *program, uint16_t len, uint16_t *resultLen)
{
    uint16_t pos = 0, nread = 0;
    uint8_t opIndex = 0, status = OTR_I2C_OK;

    if (channel >= OTR_I2C_CHANNELS) {
        status = OTR_I2C_BAD_PROGRAM;
        goto done;
    }
    if (!OtrMuxSelect (channel)) {
        status = OTR_I2C_BUS_ERROR;
        goto done;
    }
    while (pos < len) {
        uint8_t op, addr;
        uint16_t n;

        if (len - pos < OTR_I2C_OP_HEADER) {
            status = OTR_I2C_BAD_PROGRAM;
            break;
        }
        op   = program[pos];
        addr = program[pos + 1];
        n    = (uint16_t)(program[pos + 2] | (program[pos + 3] << 8));
        pos += OTR_I2C_OP_HEADER;
        if (addr > 0x7F || addr == OTR_I2C_ADDR_MUX || addr == OTR_I2C_ADDR_EEPROM) {
            status = OTR_I2C_BAD_PROGRAM;   /* the host may not touch the mux or the EEPROM here */
            break;
        }
        if (op == OTR_I2C_OP_WRITE) {
            if (n > len - pos) {
                status = OTR_I2C_BAD_PROGRAM;
                break;
            }
            /* A short write directly followed by a read of the same device
             * becomes one repeated-start transaction. */
            if (n >= 1 && n <= 6 && pos + n + OTR_I2C_OP_HEADER <= len &&
                program[pos + n] == OTR_I2C_OP_READ && program[pos + n + 1] == addr) {
                uint16_t rn = (uint16_t)(program[pos + n + 2] | (program[pos + n + 3] << 8));
                if (rn == 0 || nread + rn > OTR_I2C_MAX_READ) {
                    status = OTR_I2C_BAD_PROGRAM;
                    break;
                }
                if (OtrI2cWriteRead (addr, &program[pos], n,
                                     &otrI2cResult[OTR_I2C_RESULT_HEADER + nread], rn) != CY_U3P_SUCCESS) {
                    status = OTR_I2C_NAK_ADDRESS;
                    break;
                }
                nread += rn;
                pos += n + OTR_I2C_OP_HEADER;
                opIndex += 2;
                continue;
            }
            if (OtrI2cWrite (addr, &program[pos], n) != CY_U3P_SUCCESS) {
                status = OTR_I2C_NAK_ADDRESS;
                break;
            }
            pos += n;
        } else if (op == OTR_I2C_OP_READ) {
            if (n == 0 || nread + n > OTR_I2C_MAX_READ) {
                status = OTR_I2C_BAD_PROGRAM;
                break;
            }
            if (OtrI2cRead (addr, &otrI2cResult[OTR_I2C_RESULT_HEADER + nread], n) != CY_U3P_SUCCESS) {
                status = OTR_I2C_NAK_ADDRESS;
                break;
            }
            nread += n;
        } else {
            status = OTR_I2C_BAD_PROGRAM;
            break;
        }
        opIndex++;
    }
done:
    if (status != OTR_I2C_OK)
        nread = 0;
    otrI2cResult[0] = status;
    otrI2cResult[1] = opIndex;
    otrI2cResult[2] = (uint8_t)(nread & 0xFF);
    otrI2cResult[3] = (uint8_t)(nread >> 8);
    *resultLen = (uint16_t)(OTR_I2C_RESULT_HEADER + nread);
    return otrI2cResult;
}

/* ---------------- Boot EEPROM (24LC256, 2-byte addressing) ---------------- */

CyBool_t OtrEepromWrite (uint16_t addr, const uint8_t *data, uint16_t len)
{
    CyU3PI2cPreamble_t pre;

    if (len == 0 || len > OTR_EEPROM_PAGE || (addr % OTR_EEPROM_PAGE) + len > OTR_EEPROM_PAGE)
        return CyFalse;   /* one page per request */
    pre.buffer[0] = (uint8_t)(OTR_I2C_ADDR_EEPROM << 1);
    pre.buffer[1] = (uint8_t)(addr >> 8);
    pre.buffer[2] = (uint8_t)(addr & 0xFF);
    pre.length    = 3;
    pre.ctrlMask  = 0;
    if (CyU3PI2cTransmitBytes (&pre, (uint8_t *)data, len, 0) != CY_U3P_SUCCESS)
        return CyFalse;
    /* Wait for the internal write cycle (ACK polling). */
    pre.length = 1;
    return CyU3PI2cWaitForAck (&pre, 200) == CY_U3P_SUCCESS ? CyTrue : CyFalse;
}

CyBool_t OtrEepromRead (uint16_t addr, uint8_t *data, uint16_t len)
{
    CyU3PI2cPreamble_t pre;

    pre.buffer[0] = (uint8_t)(OTR_I2C_ADDR_EEPROM << 1);
    pre.buffer[1] = (uint8_t)(addr >> 8);
    pre.buffer[2] = (uint8_t)(addr & 0xFF);
    pre.buffer[3] = (uint8_t)((OTR_I2C_ADDR_EEPROM << 1) | 1);
    pre.length    = 4;
    pre.ctrlMask  = 1u << 2;
    return CyU3PI2cReceiveBytes (&pre, data, len, 0) == CY_U3P_SUCCESS ? CyTrue : CyFalse;
}
