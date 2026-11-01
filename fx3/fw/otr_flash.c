/* SPDX-License-Identifier: MIT */
/* OTR-4TS3-U1 FX3 firmware: the SPI boot flash (W25Q32JV, D-49).
 *
 * The flash sits on the FX3 SPI block with the SSN line as its chip select;
 * the FX3 ROM boots from it (PMODE = SPI, USB boot on failure). The FPGA
 * shares SCK/MOSI/MISO and has its own chip select on a GPIO, so every
 * access here keeps the FPGA deselected (otr_fpga.c owns that pin).
 *
 * Layout (otr_fw.h):
 *   0x000000  FX3 boot image (elf2img output)
 *   0x100000  FPGA slot: 256-byte header {"OTRB", length (LE)} + bitstream
 *
 * Commands used: 03h read, 02h page program, 20h 4 KiB sector erase,
 * 06h write enable, 05h status 1, 4Bh unique ID, 9Fh JEDEC ID. */
#include "cyu3system.h"
#include "cyu3os.h"
#include "cyu3error.h"
#include "cyu3spi.h"
#include "otr_fw.h"

#define FLASH_READ      0x03
#define FLASH_PROGRAM   0x02
#define FLASH_ERASE_4K  0x20
#define FLASH_WREN      0x06
#define FLASH_RDSR1     0x05
#define FLASH_UID       0x4B
#define FLASH_JEDEC     0x9F
#define FLASH_SR1_BUSY  0x01

static uint8_t otrFlashUid[8];
static CyBool_t otrFlashPresent;

static CyBool_t OtrFlashCmd (const uint8_t *tx, uint16_t txLen, uint8_t *rx, uint32_t rxLen)
{
    CyBool_t ok;

    OtrSpiSetClock (OTR_SPI_FLASH_HZ);
    CyU3PSpiSetSsnLine (CyFalse);
    ok = CyU3PSpiTransmitWords ((uint8_t *)tx, txLen) == CY_U3P_SUCCESS ? CyTrue : CyFalse;
    if (ok && rxLen != 0)
        ok = CyU3PSpiReceiveWords (rx, rxLen) == CY_U3P_SUCCESS ? CyTrue : CyFalse;
    CyU3PSpiSetSsnLine (CyTrue);
    return ok;
}

uint8_t OtrFlashStatus (void)
{
    uint8_t cmd = FLASH_RDSR1, sr = 0xFF;

    if (!OtrFlashCmd (&cmd, 1, &sr, 1))
        return 0xFF;
    return sr;
}

/* Waits for a program or erase to finish. A 4 KiB erase takes up to 400 ms. */
static CyBool_t OtrFlashWaitIdle (uint32_t timeoutMs)
{
    uint32_t t;

    for (t = 0; t <= timeoutMs; t++) {
        if ((OtrFlashStatus () & FLASH_SR1_BUSY) == 0)
            return CyTrue;
        CyU3PThreadSleep (1);
    }
    return CyFalse;
}

static CyBool_t OtrFlashWriteEnable (void)
{
    uint8_t cmd = FLASH_WREN;
    return OtrFlashCmd (&cmd, 1, NULL, 0);
}

static void OtrFlashAddrCmd (uint8_t *cmd, uint8_t op, uint32_t addr)
{
    cmd[0] = op;
    cmd[1] = (uint8_t)(addr >> 16);
    cmd[2] = (uint8_t)(addr >> 8);
    cmd[3] = (uint8_t)addr;
}

CyBool_t OtrFlashRead (uint32_t addr, uint8_t *data, uint32_t len)
{
    uint8_t cmd[4] __attribute__ ((aligned (32)));

    if (!otrFlashPresent || len == 0 || addr + len > OTR_FLASH_SIZE)
        return CyFalse;
    if (!OtrFlashWaitIdle (500))
        return CyFalse;
    OtrFlashAddrCmd (cmd, FLASH_READ, addr);
    return OtrFlashCmd (cmd, 4, data, len);
}

/* One page program (<= 256 bytes, not crossing a page boundary); waits for
 * completion (typically 0.4 ms, at most 3 ms). */
CyBool_t OtrFlashProgram (uint32_t addr, const uint8_t *data, uint16_t len)
{
    static uint8_t buf[4 + OTR_FLASH_PAGE] __attribute__ ((aligned (32)));

    if (!otrFlashPresent || len == 0 || len > OTR_FLASH_PAGE ||
        (addr % OTR_FLASH_PAGE) + len > OTR_FLASH_PAGE || addr + len > OTR_FLASH_SIZE)
        return CyFalse;
    if (!OtrFlashWaitIdle (500) || !OtrFlashWriteEnable ())
        return CyFalse;
    OtrFlashAddrCmd (buf, FLASH_PROGRAM, addr);
    CyU3PMemCopy (&buf[4], (uint8_t *)data, len);
    if (!OtrFlashCmd (buf, (uint16_t)(4 + len), NULL, 0))
        return CyFalse;
    return OtrFlashWaitIdle (10);
}

/* Starts a 4 KiB sector erase and returns without waiting; the host polls
 * FLASH_STATUS, and every other flash access waits for it anyway. */
CyBool_t OtrFlashErase (uint32_t addr)
{
    uint8_t cmd[4] __attribute__ ((aligned (32)));

    if (!otrFlashPresent || (addr % OTR_FLASH_SECTOR) != 0 || addr >= OTR_FLASH_SIZE)
        return CyFalse;
    if (!OtrFlashWaitIdle (500) || !OtrFlashWriteEnable ())
        return CyFalse;
    OtrFlashAddrCmd (cmd, FLASH_ERASE_4K, addr);
    return OtrFlashCmd (cmd, 4, NULL, 0);
}

const uint8_t *OtrFlashUid (void)
{
    return otrFlashPresent ? otrFlashUid : NULL;
}

void OtrFlashInit (void)
{
    uint8_t cmd[5] __attribute__ ((aligned (32))) = {FLASH_JEDEC, 0, 0, 0, 0};
    uint8_t id[8] __attribute__ ((aligned (32)));

    otrFlashPresent = CyFalse;
    /* JEDEC ID: manufacturer, memory type, capacity (0x16 = 32 Mbit). */
    if (!OtrFlashCmd (cmd, 1, id, 3) || id[0] == 0x00 || id[0] == 0xFF)
        return;
    if (id[2] < 0x16)
        return;   /* smaller than the layout needs */
    /* Unique ID: 4Bh followed by four dummy bytes, then 64 bits. */
    cmd[0] = FLASH_UID;
    if (!OtrFlashCmd (cmd, 5, otrFlashUid, 8))
        return;
    otrFlashPresent = CyTrue;
}
