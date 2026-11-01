/* SPDX-License-Identifier: MIT */
/* OTR-4TS3-U1 FX3 firmware: iCE40 SPI slave configuration (D-25), the FPGA
 * register access over the same SPI lines once configured (D-47), and the
 * start-up load of the bitstream stored in the boot flash (D-49).
 *
 * iCE40 SPI slave configuration (Lattice iCE40 programming guide):
 *   SS low, pulse CRESET_B low (>= 200 ns), release it and wait >= 1200 us,
 *   send the whole bitstream MSB first with SS low and without interruption,
 *   then send >= 49 dummy clocks; CDONE goes high when the device has started.
 *
 * The SPI bus is shared with the boot flash (D-49): the flash uses the FX3
 * SSN line, the FPGA uses a GPIO chip select (OTR_PIN_FPGA_SS_N). Because the
 * image must not be interrupted, the start-up load reads the whole bitstream
 * from the flash into RAM first and only then selects the FPGA. */
#include "cyu3system.h"
#include "cyu3os.h"
#include "cyu3error.h"
#include "cyu3gpio.h"
#include "cyu3spi.h"
#include "cyu3utils.h"
#include "otr_fw.h"
#include "otr_board.h"

static CyBool_t otrFpgaLoading;
static uint8_t  otrFpgaSrc;      /* OTR_FPGA_SRC_* of the current configuration */
static uint32_t otrSpiHz;

/* Configuration runs at 20 MHz (iCE40 slave limit 25 MHz). Register access
 * runs at 4 MHz because the FPGA oversamples SCK with its 50 MHz system clock
 * and needs SCK <= clk / 8 (fpga/rtl/spi_regs.v, D-47). */
void OtrSpiSetClock (uint32_t hz)
{
    CyU3PSpiConfig_t cfg;

    if (otrSpiHz == hz)
        return;
    CyU3PMemSet ((uint8_t *)&cfg, 0, sizeof (cfg));
    cfg.isLsbFirst = CyFalse;
    cfg.cpol       = CyTrue;     /* mode 3: the iCE40 and the flash both accept it */
    cfg.cpha       = CyTrue;
    cfg.ssnPol     = CyFalse;
    cfg.ssnCtrl    = CY_U3P_SPI_SSN_CTRL_FW;
    cfg.leadTime   = CY_U3P_SPI_SSN_LAG_LEAD_HALF_CLK;
    cfg.lagTime    = CY_U3P_SPI_SSN_LAG_LEAD_HALF_CLK;
    cfg.clock      = hz;
    cfg.wordLen    = 8;
    if (CyU3PSpiSetConfig (&cfg, NULL) == CY_U3P_SUCCESS)
        otrSpiHz = hz;
}

static void OtrFpgaSelect (CyBool_t on)
{
    CyU3PGpioSetValue (OTR_PIN_FPGA_SS_N, on ? CyFalse : CyTrue);
}

void OtrFpgaInit (void)
{
    CyU3PSpiInit ();
    otrSpiHz = 0;
    OtrSpiSetClock (OTR_SPI_CONFIG_HZ);
    CyU3PSpiSetSsnLine (CyTrue);     /* flash deselected */
    OtrFpgaSelect (CyFalse);
    otrFpgaLoading = CyFalse;
    otrFpgaSrc = OTR_FPGA_SRC_NONE;
}

CyBool_t OtrFpgaDone (void)
{
    CyBool_t v = CyFalse;
    CyU3PGpioSimpleGetValue (OTR_PIN_FPGA_CDONE, &v);
    return v;
}

/* A host FPGA_LOAD is in progress: the FPGA chip select is held low, so
 * nothing else may use the SPI bus until END. */
CyBool_t OtrFpgaBusy (void)
{
    return otrFpgaLoading;
}

uint8_t OtrFpgaSource (void)
{
    return OtrFpgaDone () ? otrFpgaSrc : OTR_FPGA_SRC_NONE;
}

CyBool_t OtrFpgaLoad (uint16_t stage, const uint8_t *data, uint16_t len)
{
    static uint8_t dummy[8] __attribute__ ((aligned (32))) = {0};

    switch (stage) {
    case OTR_FPGA_LOAD_BEGIN:
        OtrSpiSetClock (OTR_SPI_CONFIG_HZ);
        CyU3PSpiSetSsnLine (CyTrue);                     /* keep the flash off the bus */
        OtrFpgaSelect (CyTrue);                          /* SS low selects SPI slave mode */
        CyU3PGpioSetValue (OTR_PIN_FPGA_CRESET_B, CyFalse);
        CyFx3BusyWait (10);
        CyU3PGpioSetValue (OTR_PIN_FPGA_CRESET_B, CyTrue);
        CyFx3BusyWait (1500);                            /* >= 1200 us to clear CRAM */
        otrFpgaLoading = CyTrue;
        otrFpgaSrc = OTR_FPGA_SRC_NONE;
        return CyTrue;
    case OTR_FPGA_LOAD_DATA:
        if (!otrFpgaLoading || len == 0 || len > OTR_FPGA_LOAD_CHUNK)
            return CyFalse;
        if (CyU3PSpiTransmitWords ((uint8_t *)data, len) != CY_U3P_SUCCESS) {
            otrFpgaLoading = CyFalse;   /* END then fails, reporting the error */
            return CyFalse;
        }
        return CyTrue;
    case OTR_FPGA_LOAD_END:
        if (!otrFpgaLoading) {
            OtrFpgaSelect (CyFalse);
            return CyFalse;
        }
        otrFpgaLoading = CyFalse;
        OtrFpgaSelect (CyFalse);
        CyU3PSpiTransmitWords (dummy, sizeof (dummy));   /* 64 >= 49 dummy clocks */
        CyU3PThreadSleep (2);
        if (!OtrFpgaDone ())
            return CyFalse;
        otrFpgaSrc = OTR_FPGA_SRC_HOST;
        return CyTrue;
    default:
        return CyFalse;
    }
}

/* Start-up load from the flash slot. Returns CyFalse when the slot is empty
 * or the load fails; the host can still load a bitstream with FPGA_LOAD. */
CyBool_t OtrFpgaAutoload (void)
{
    uint8_t hdr[8] __attribute__ ((aligned (32)));
    uint32_t len, off, n;
    uint8_t *buf;
    CyBool_t ok;

    if (!OtrFlashRead (OTR_FLASH_FPGA_SLOT, hdr, sizeof (hdr)))
        return CyFalse;
    if (hdr[0] != 'O' || hdr[1] != 'T' || hdr[2] != 'R' || hdr[3] != 'B')
        return CyFalse;
    len = (uint32_t)hdr[4] | ((uint32_t)hdr[5] << 8) | ((uint32_t)hdr[6] << 16) |
          ((uint32_t)hdr[7] << 24);
    if (len == 0 || len > OTR_FPGA_MAX_BITSTREAM)
        return CyFalse;
    /* The DMA buffer area is still free here: USB, and with it the TS DMA
     * channel, starts only after this load. */
    buf = (uint8_t *)CyU3PDmaBufferAlloc (len);
    if (buf == NULL)
        return CyFalse;
    ok = OtrFlashRead (OTR_FLASH_FPGA_SLOT + OTR_FLASH_FPGA_HDR, buf, len);
    if (ok)
        ok = OtrFpgaLoad (OTR_FPGA_LOAD_BEGIN, NULL, 0);
    for (off = 0; ok && off < len; off += n) {
        n = len - off;
        if (n > OTR_FPGA_LOAD_CHUNK)
            n = OTR_FPGA_LOAD_CHUNK;
        ok = OtrFpgaLoad (OTR_FPGA_LOAD_DATA, buf + off, (uint16_t)n);
    }
    if (ok)
        ok = OtrFpgaLoad (OTR_FPGA_LOAD_END, NULL, 0);
    else
        (void)OtrFpgaLoad (OTR_FPGA_LOAD_END, NULL, 0);   /* release SS */
    CyU3PDmaBufferFree (buf);
    if (ok)
        otrFpgaSrc = OTR_FPGA_SRC_FLASH;
    return ok;
}

/* FPGA register access after configuration: one SPI transaction of
 * {cmd, d3, d2, d1, d0}, cmd = 0x80 | addr for a read, addr for a write
 * (fpga/rtl/spi_regs.v; register map in otr-userland docs/design.md 5). */
CyBool_t OtrFpgaReg (CyBool_t write, uint8_t addr, uint32_t *value)
{
    uint8_t tx[5] __attribute__ ((aligned (32)));
    uint8_t rx[5] __attribute__ ((aligned (32)));
    CyBool_t ok;

    if (!OtrFpgaDone () || otrFpgaLoading || addr > 0x7F)
        return CyFalse;
    OtrSpiSetClock (OTR_SPI_REG_HZ);
    CyU3PSpiSetSsnLine (CyTrue);
    tx[0] = write ? addr : (uint8_t)(0x80 | addr);
    tx[1] = (uint8_t)(*value >> 24);
    tx[2] = (uint8_t)(*value >> 16);
    tx[3] = (uint8_t)(*value >> 8);
    tx[4] = (uint8_t)(*value);
    OtrFpgaSelect (CyTrue);
    ok = CyU3PSpiTransferWords (tx, sizeof (tx), rx, sizeof (rx)) == CY_U3P_SUCCESS ? CyTrue : CyFalse;
    OtrFpgaSelect (CyFalse);
    if (ok && !write)
        *value = ((uint32_t)rx[1] << 24) | ((uint32_t)rx[2] << 16) | ((uint32_t)rx[3] << 8) | rx[4];
    return ok;
}
