/* SPDX-License-Identifier: MIT */
/* OTR-4TS3-U1 FX3 firmware: iCE40 SPI slave configuration (D-25) and the
 * FPGA register access over the same SPI lines once configured.
 *
 * iCE40 SPI slave configuration (Lattice iCE40 programming guide):
 *   SS low, pulse CRESET_B low (>= 200 ns), release it and wait >= 1200 us,
 *   send the bitstream MSB first with SS low, then send >= 49 dummy clocks;
 *   CDONE goes high when the device has started. */
#include "cyu3system.h"
#include "cyu3os.h"
#include "cyu3error.h"
#include "cyu3gpio.h"
#include "cyu3spi.h"
#include "cyu3utils.h"
#include "otr_fw.h"
#include "otr_board.h"

static CyBool_t otrFpgaLoading;
static uint32_t otrFpgaBytes;

static void OtrSpiConfig (void)
{
    CyU3PSpiConfig_t cfg;

    CyU3PMemSet ((uint8_t *)&cfg, 0, sizeof (cfg));
    cfg.isLsbFirst = CyFalse;
    cfg.cpol       = CyTrue;     /* iCE40 samples on the rising edge; mode 3 also works for config */
    cfg.cpha       = CyTrue;
    cfg.ssnPol     = CyFalse;
    cfg.ssnCtrl    = CY_U3P_SPI_SSN_CTRL_FW;
    cfg.leadTime   = CY_U3P_SPI_SSN_LAG_LEAD_HALF_CLK;
    cfg.lagTime    = CY_U3P_SPI_SSN_LAG_LEAD_HALF_CLK;
    cfg.clock      = 20000000;   /* <= 25 MHz for iCE40 slave configuration */
    cfg.wordLen    = 8;
    CyU3PSpiSetConfig (&cfg, NULL);
}

void OtrFpgaInit (void)
{
    CyU3PSpiInit ();
    OtrSpiConfig ();
    CyU3PSpiSetSsnLine (CyTrue);
    otrFpgaLoading = CyFalse;
    otrFpgaBytes = 0;
}

CyBool_t OtrFpgaDone (void)
{
    CyBool_t v = CyFalse;
    CyU3PGpioSimpleGetValue (OTR_PIN_FPGA_CDONE, &v);
    return v;
}

CyBool_t OtrFpgaLoad (uint16_t stage, const uint8_t *data, uint16_t len)
{
    static uint8_t dummy[8] __attribute__ ((aligned (32))) = {0};

    switch (stage) {
    case OTR_FPGA_LOAD_BEGIN:
        CyU3PSpiSetSsnLine (CyFalse);                    /* SS low selects SPI slave mode */
        CyU3PGpioSetValue (OTR_PIN_FPGA_CRESET_B, CyFalse);
        CyFx3BusyWait (10);
        CyU3PGpioSetValue (OTR_PIN_FPGA_CRESET_B, CyTrue);
        CyFx3BusyWait (1500);                            /* >= 1200 us to clear CRAM */
        otrFpgaLoading = CyTrue;
        otrFpgaBytes = 0;
        return CyTrue;
    case OTR_FPGA_LOAD_DATA:
        if (!otrFpgaLoading || len == 0 || len > OTR_FPGA_LOAD_CHUNK)
            return CyFalse;
        if (CyU3PSpiTransmitWords ((uint8_t *)data, len) != CY_U3P_SUCCESS) {
            otrFpgaLoading = CyFalse;   /* END then fails, reporting the error */
            return CyFalse;
        }
        otrFpgaBytes += len;
        return CyTrue;
    case OTR_FPGA_LOAD_END:
        if (!otrFpgaLoading) {
            CyU3PSpiSetSsnLine (CyTrue);
            return CyFalse;
        }
        otrFpgaLoading = CyFalse;
        CyU3PSpiSetSsnLine (CyTrue);
        CyU3PSpiTransmitWords (dummy, sizeof (dummy));   /* 64 >= 49 dummy clocks */
        CyU3PThreadSleep (2);
        return OtrFpgaDone ();
    default:
        return CyFalse;
    }
}

/* FPGA register access after configuration: one SPI transaction of
 * {cmd, d3, d2, d1, d0}, cmd = 0x80 | addr for a read, addr for a write.
 * The FPGA-side SPI register block is still TBD (otr-userland design.md
 * section 5); the framing is defined here so that both sides agree. */
CyBool_t OtrFpgaReg (CyBool_t write, uint8_t addr, uint32_t *value)
{
    uint8_t tx[5] __attribute__ ((aligned (32)));
    uint8_t rx[5] __attribute__ ((aligned (32)));

    if (!OtrFpgaDone () || otrFpgaLoading || addr > 0x7F)
        return CyFalse;
    tx[0] = write ? addr : (uint8_t)(0x80 | addr);
    tx[1] = (uint8_t)(*value >> 24);
    tx[2] = (uint8_t)(*value >> 16);
    tx[3] = (uint8_t)(*value >> 8);
    tx[4] = (uint8_t)(*value);
    CyU3PSpiSetSsnLine (CyFalse);
    if (CyU3PSpiTransferWords (tx, sizeof (tx), rx, sizeof (rx)) != CY_U3P_SUCCESS) {
        CyU3PSpiSetSsnLine (CyTrue);
        return CyFalse;
    }
    CyU3PSpiSetSsnLine (CyTrue);
    if (!write)
        *value = ((uint32_t)rx[1] << 24) | ((uint32_t)rx[2] << 16) | ((uint32_t)rx[3] << 8) | rx[4];
    return CyTrue;
}
