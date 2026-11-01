/* SPDX-License-Identifier: MIT */
/* OTR-4TS3-U1 FX3 firmware: USB descriptors, enumeration events and the
 * vendor-request handler (protocol v1). Windows binds WinUSB automatically
 * through the MS OS 2.0 descriptor set (no INF), as px4-userland expects. */
#include "cyu3system.h"
#include "cyu3os.h"
#include "cyu3error.h"
#include "cyu3usb.h"
#include "otr_fw.h"

#define ALIGN32 __attribute__ ((aligned (32)))
#define LO(x) ((uint8_t)((x) & 0xFF))
#define HI(x) ((uint8_t)(((x) >> 8) & 0xFF))

/* ---------------- Descriptors ---------------- */

static const uint8_t otrDevDescSS[] ALIGN32 = {
    0x12, CY_U3P_USB_DEVICE_DESCR, 0x20, 0x03,   /* USB 3.2 */
    0x00, 0x00, 0x00, 0x09,                      /* vendor class, EP0 512 bytes */
    LO(OTR_USB_VID), HI(OTR_USB_VID), LO(OTR_USB_PID), HI(OTR_USB_PID),
    LO(0x0100 | OTR_FW_VERSION_MINOR), HI(0x0100), 0x01, 0x02, 0x03, 0x01
};

static const uint8_t otrDevDescHS[] ALIGN32 = {
    0x12, CY_U3P_USB_DEVICE_DESCR, 0x10, 0x02,   /* USB 2.1: required for the BOS on USB 2 */
    0x00, 0x00, 0x00, 0x40,
    LO(OTR_USB_VID), HI(OTR_USB_VID), LO(OTR_USB_PID), HI(OTR_USB_PID),
    LO(0x0100 | OTR_FW_VERSION_MINOR), HI(0x0100), 0x01, 0x02, 0x03, 0x01
};

static const uint8_t otrDevQualDesc[] ALIGN32 = {
    0x0A, CY_U3P_USB_DEVQUAL_DESCR, 0x00, 0x02, 0x00, 0x00, 0x00, 0x40, 0x01, 0x00
};

#define OTR_CFG_SS(total)                                                                   \
    0x09, CY_U3P_USB_CONFIG_DESCR, LO(total), HI(total), 0x01, 0x01, 0x00, 0x80, 0x32,     \
    0x09, CY_U3P_USB_INTRFC_DESCR, 0x00, 0x00, 0x01, 0xFF, 0x00, 0x00, 0x00

static const uint8_t otrCfgDescSS[] ALIGN32 = {
    OTR_CFG_SS(31),
    0x07, CY_U3P_USB_ENDPNT_DESCR, OTR_EP_TS, CY_U3P_USB_EP_BULK, 0x00, 0x04, 0x00,
    0x06, CY_U3P_SS_EP_COMPN_DESCR, OTR_SS_BURST - 1, 0x00, 0x00, 0x00
};

static const uint8_t otrCfgDescHS[] ALIGN32 = {
    OTR_CFG_SS(25),
    0x07, CY_U3P_USB_ENDPNT_DESCR, OTR_EP_TS, CY_U3P_USB_EP_BULK, 0x00, 0x02, 0x00
};

static const uint8_t otrCfgDescFS[] ALIGN32 = {
    OTR_CFG_SS(25),
    0x07, CY_U3P_USB_ENDPNT_DESCR, OTR_EP_TS, CY_U3P_USB_EP_BULK, 0x40, 0x00, 0x00
};

#define OTR_MSOS20_TOTAL 0xA2   /* 10 + 20 + 132 */

static const uint8_t otrBosDesc[] ALIGN32 = {
    0x05, CY_U3P_BOS_DESCR, 0x32, 0x00, 0x03,                 /* 50 bytes, 3 capabilities */
    0x07, CY_U3P_DEVICE_CAPB_DESCR, CY_U3P_USB2_EXTN_CAPB_TYPE,
    0x02, 0x00, 0x00, 0x00,                                   /* LPM */
    0x0A, CY_U3P_DEVICE_CAPB_DESCR, CY_U3P_SS_USB_CAPB_TYPE,
    0x00, 0x0E, 0x00, 0x03, 0x00, 0x00, 0x00,                 /* FS/HS/SS, func >= FS */
    0x1C, CY_U3P_DEVICE_CAPB_DESCR, 0x05, 0x00,               /* platform capability */
    0xDF, 0x60, 0xDD, 0xD8, 0x89, 0x45, 0xC7, 0x4C,           /* MS OS 2.0 UUID */
    0x9C, 0xD2, 0x65, 0x9D, 0x9E, 0x64, 0x8A, 0x9F,           /* D8DD60DF-4589-4CC7-9CD2-659D9E648A9F */
    0x00, 0x00, 0x03, 0x06,                                   /* Windows 8.1+ */
    LO(OTR_MSOS20_TOTAL), HI(OTR_MSOS20_TOTAL), OTR_REQ_MS_OS_20, 0x00
};

/* MS OS 2.0 descriptor set: WINUSB compatible ID + DeviceInterfaceGUIDs.
 * {7A1C6C4E-5F3B-4E8D-9C1A-0B2E3D4F5A61} identifies the OTR interface. */
#define U16(c) (c), 0x00
static const uint8_t otrMsOs20Desc[] ALIGN32 = {
    0x0A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03, 0x06, LO(OTR_MSOS20_TOTAL), HI(OTR_MSOS20_TOTAL),
    0x14, 0x00, 0x03, 0x00, 'W', 'I', 'N', 'U', 'S', 'B', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0x84, 0x00, 0x04, 0x00, 0x07, 0x00, 0x2A, 0x00,
    U16('D'), U16('e'), U16('v'), U16('i'), U16('c'), U16('e'), U16('I'), U16('n'), U16('t'),
    U16('e'), U16('r'), U16('f'), U16('a'), U16('c'), U16('e'), U16('G'), U16('U'), U16('I'),
    U16('D'), U16('s'), U16(0),
    0x50, 0x00,
    U16('{'), U16('7'), U16('A'), U16('1'), U16('C'), U16('6'), U16('C'), U16('4'), U16('E'),
    U16('-'), U16('5'), U16('F'), U16('3'), U16('B'), U16('-'), U16('4'), U16('E'), U16('8'),
    U16('D'), U16('-'), U16('9'), U16('C'), U16('1'), U16('A'), U16('-'), U16('0'), U16('B'),
    U16('2'), U16('E'), U16('3'), U16('D'), U16('4'), U16('F'), U16('5'), U16('A'), U16('6'),
    U16('1'), U16('}'), U16(0), U16(0)
};

static const uint8_t otrStrLang[] ALIGN32 = {0x04, CY_U3P_USB_STRING_DESCR, 0x09, 0x04};
static const uint8_t otrStrManuf[] ALIGN32 = {
    0x18, CY_U3P_USB_STRING_DESCR, U16('O'), U16('T'), U16('R'), U16(' '), U16('P'), U16('r'),
    U16('o'), U16('j'), U16('e'), U16('c'), U16('t')
};
static const uint8_t otrStrProduct[] ALIGN32 = {
    0x18, CY_U3P_USB_STRING_DESCR, U16('O'), U16('T'), U16('R'), U16('-'), U16('4'), U16('T'),
    U16('S'), U16('3'), U16('-'), U16('U'), U16('1')
};
/* Serial: 16 hex digits of the boot flash's 64-bit unique ID, filled in by
 * OtrUsbInit (D-49). The zeros remain only if the flash cannot be read. */
static uint8_t otrStrSerial[] ALIGN32 = {
    0x22, CY_U3P_USB_STRING_DESCR, U16('0'), U16('0'), U16('0'), U16('0'), U16('0'), U16('0'),
    U16('0'), U16('0'), U16('0'), U16('0'), U16('0'), U16('0'), U16('0'), U16('0'), U16('0'),
    U16('1')
};

/* ---------------- Vendor requests ---------------- */

static uint8_t otrEp0Buf[OTR_FPGA_LOAD_CHUNK] ALIGN32;
static uint8_t *otrI2cLast;
static uint16_t otrI2cLastLen;

static void OtrPut32 (uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

static uint32_t OtrGet32 (const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static CyBool_t OtrSendIn (const uint8_t *data, uint16_t len, uint16_t wLength)
{
    if (len > wLength)
        len = wLength;
    return CyU3PUsbSendEP0Data (len, (uint8_t *)data) == CY_U3P_SUCCESS;
}

static CyBool_t OtrGetOut (uint16_t wLength)
{
    uint16_t got = 0;
    if (wLength > sizeof (otrEp0Buf))
        return CyFalse;
    if (wLength == 0)
        return CyTrue;
    return CyU3PUsbGetEP0Data (wLength, otrEp0Buf, &got) == CY_U3P_SUCCESS && got == wLength;
}

static CyBool_t OtrVendorRequest (uint8_t bReqType, uint8_t bRequest, uint16_t wValue,
                                  uint16_t wIndex, uint16_t wLength)
{
    const CyBool_t in = (bReqType & 0x80) ? CyTrue : CyFalse;
    CyBool_t ok = CyFalse;
    uint32_t v;

    switch (bRequest) {
    case OTR_REQ_GET_INFO:
        if (!in)
            return CyFalse;
        CyU3PMemSet (otrEp0Buf, 0, 32);
        otrEp0Buf[0] = 'O'; otrEp0Buf[1] = 'T'; otrEp0Buf[2] = 'R'; otrEp0Buf[3] = '1';
        otrEp0Buf[4] = LO(OTR_PROTOCOL_VERSION); otrEp0Buf[5] = HI(OTR_PROTOCOL_VERSION);
        otrEp0Buf[6] = OTR_FW_VERSION_MINOR;     otrEp0Buf[7] = OTR_FW_VERSION_MAJOR;
        otrEp0Buf[8] = OtrFpgaDone () ? 1 : 0;
        otrEp0Buf[9] = OtrStreamConfigured () ? 1 : 0;
        otrEp0Buf[10] = OtrFpgaSource ();
        otrEp0Buf[11] = OtrFlashUid () != NULL ? 1 : 0;
        OtrPut32 (&otrEp0Buf[12], OTR_DMA_BUF_SIZE);
        otrEp0Buf[16] = LO(OTR_I2C_MAX_PROGRAM); otrEp0Buf[17] = HI(OTR_I2C_MAX_PROGRAM);
        otrEp0Buf[18] = LO(OTR_I2C_MAX_READ);    otrEp0Buf[19] = HI(OTR_I2C_MAX_READ);
        if (OtrFlashUid () != NULL)
            CyU3PMemCopy (&otrEp0Buf[20], (uint8_t *)OtrFlashUid (), 8);
        return OtrSendIn (otrEp0Buf, 32, wLength);

    case OTR_REQ_I2C_RUN:
        if (in || wLength == 0 || wLength > OTR_I2C_MAX_PROGRAM || !OtrGetOut (wLength))
            return CyFalse;
        otrI2cLast = OtrI2cRun (wIndex, otrEp0Buf, wLength, &otrI2cLastLen);
        return CyTrue;

    case OTR_REQ_I2C_RESULT:
        if (!in || otrI2cLast == NULL)
            return CyFalse;
        return OtrSendIn (otrI2cLast, otrI2cLastLen, wLength);

    case OTR_REQ_GPIO:
        if (in) {
            OtrPut32 (otrEp0Buf, OtrGpioGet ());
            return OtrSendIn (otrEp0Buf, 4, wLength);
        }
        OtrGpioSet (wValue, wIndex, &ok);
        if (ok)
            CyU3PUsbAckSetup ();
        return ok;

    case OTR_REQ_FPGA_LOAD:
        if (in)
            return CyFalse;
        if (wLength == 0) {
            /* BEGIN/END carry no data: do the work, then ACK or stall. */
            ok = OtrFpgaLoad (wValue, otrEp0Buf, 0);
            if (ok)
                CyU3PUsbAckSetup ();
            return ok;
        }
        /* With a data stage the status is already ACKed once the data has
         * arrived, so a failed DATA chunk shows up as END reporting CDONE low. */
        if (!OtrGetOut (wLength))
            return CyFalse;
        return OtrFpgaLoad (wValue, otrEp0Buf, wLength);

    case OTR_REQ_FPGA_REG:
        if (in) {
            v = 0;
            if (!OtrFpgaReg (CyFalse, (uint8_t)wValue, &v))
                return CyFalse;
            OtrPut32 (otrEp0Buf, v);
            return OtrSendIn (otrEp0Buf, 4, wLength);
        }
        if (wLength != 4 || !OtrGetOut (4))
            return CyFalse;
        v = OtrGet32 (otrEp0Buf);
        return OtrFpgaReg (CyTrue, (uint8_t)wValue, &v);

    case OTR_REQ_STREAM:
        if (in)
            return CyFalse;
        ok = OtrStreamSet (wValue ? CyTrue : CyFalse);
        if (ok)
            CyU3PUsbAckSetup ();
        return ok;

    case OTR_REQ_FLASH_WRITE:
        /* A failure after the data stage cannot stall any more: the host
         * verifies by reading back. */
        if (in || OtrFpgaBusy () || wLength == 0 || wLength > OTR_FLASH_PAGE || !OtrGetOut (wLength))
            return CyFalse;
        return OtrFlashProgram (((uint32_t)wIndex << 16) | wValue, otrEp0Buf, wLength);

    case OTR_REQ_FLASH_READ:
        if (!in || OtrFpgaBusy () || wLength == 0 || wLength > OTR_FLASH_READ_MAX)
            return CyFalse;
        if (!OtrFlashRead (((uint32_t)wIndex << 16) | wValue, otrEp0Buf, wLength))
            return CyFalse;
        return OtrSendIn (otrEp0Buf, wLength, wLength);

    case OTR_REQ_FLASH_ERASE:
        if (in || OtrFpgaBusy () || wLength != 0)
            return CyFalse;
        ok = OtrFlashErase (((uint32_t)wIndex << 16) | wValue);
        if (ok)
            CyU3PUsbAckSetup ();
        return ok;

    case OTR_REQ_FLASH_STATUS:
        if (!in || OtrFpgaBusy ())
            return CyFalse;
        otrEp0Buf[0] = OtrFlashStatus ();
        return OtrSendIn (otrEp0Buf, 1, wLength);

    case OTR_REQ_MS_OS_20:
        if (!in || wIndex != 0x07)   /* MS_OS_20_DESCRIPTOR_INDEX */
            return CyFalse;
        return OtrSendIn (otrMsOs20Desc, sizeof (otrMsOs20Desc), wLength);

    default:
        return CyFalse;
    }
}

/* Returning CyFalse lets the library stall EP0. */
static CyBool_t OtrSetupCallback (uint32_t setupdat0, uint32_t setupdat1)
{
    const uint8_t bReqType  = (uint8_t)(setupdat0 & CY_U3P_USB_REQUEST_TYPE_MASK);
    const uint8_t bType     = (uint8_t)(bReqType & CY_U3P_USB_TYPE_MASK);
    const uint8_t bRequest  = (uint8_t)((setupdat0 & CY_U3P_USB_REQUEST_MASK) >> CY_U3P_USB_REQUEST_POS);
    const uint16_t wValue   = (uint16_t)((setupdat0 & CY_U3P_USB_VALUE_MASK) >> CY_U3P_USB_VALUE_POS);
    const uint16_t wIndex   = (uint16_t)((setupdat1 & CY_U3P_USB_INDEX_MASK) >> CY_U3P_USB_INDEX_POS);
    const uint16_t wLength  = (uint16_t)((setupdat1 & CY_U3P_USB_LENGTH_MASK) >> CY_U3P_USB_LENGTH_POS);

    if (bType != CY_U3P_USB_VENDOR_RQT)
        return CyFalse;   /* standard requests are handled by fast enumeration */
    return OtrVendorRequest (bReqType, bRequest, wValue, wIndex, wLength);
}

static void OtrUsbEventCallback (CyU3PUsbEventType_t evtype, uint16_t evdata)
{
    (void)evdata;
    switch (evtype) {
    case CY_U3P_USB_EVENT_SETCONF:
        OtrStreamOnSetConf (CyU3PUsbGetSpeed () == CY_U3P_SUPER_SPEED ? CyTrue : CyFalse);
        break;
    case CY_U3P_USB_EVENT_RESET:
    case CY_U3P_USB_EVENT_DISCONNECT:
        OtrStreamOnReset ();
        break;
    default:
        break;
    }
}

static CyBool_t OtrLpmCallback (CyU3PUsbLinkPowerMode link_mode)
{
    (void)link_mode;
    return CyTrue;
}

static void OtrSerialFromUid (void)
{
    static const char hex[] = "0123456789ABCDEF";
    const uint8_t *uid = OtrFlashUid ();
    uint8_t i;

    if (uid == NULL)
        return;
    for (i = 0; i < 8; i++) {
        otrStrSerial[2 + 4 * i] = (uint8_t)hex[uid[i] >> 4];
        otrStrSerial[2 + 4 * i + 2] = (uint8_t)hex[uid[i] & 0x0F];
    }
}

void OtrUsbInit (void)
{
    OtrSerialFromUid ();
    if (CyU3PUsbStart () != CY_U3P_SUCCESS)
        return;
    CyU3PUsbRegisterSetupCallback (OtrSetupCallback, CyTrue);
    CyU3PUsbRegisterEventCallback (OtrUsbEventCallback);
    CyU3PUsbRegisterLPMRequestCallback (OtrLpmCallback);

    CyU3PUsbSetDesc (CY_U3P_USB_SET_SS_DEVICE_DESCR, 0, (uint8_t *)otrDevDescSS);
    CyU3PUsbSetDesc (CY_U3P_USB_SET_HS_DEVICE_DESCR, 0, (uint8_t *)otrDevDescHS);
    CyU3PUsbSetDesc (CY_U3P_USB_SET_SS_BOS_DESCR, 0, (uint8_t *)otrBosDesc);
    CyU3PUsbSetDesc (CY_U3P_USB_SET_DEVQUAL_DESCR, 0, (uint8_t *)otrDevQualDesc);
    CyU3PUsbSetDesc (CY_U3P_USB_SET_SS_CONFIG_DESCR, 0, (uint8_t *)otrCfgDescSS);
    CyU3PUsbSetDesc (CY_U3P_USB_SET_HS_CONFIG_DESCR, 0, (uint8_t *)otrCfgDescHS);
    CyU3PUsbSetDesc (CY_U3P_USB_SET_FS_CONFIG_DESCR, 0, (uint8_t *)otrCfgDescFS);
    CyU3PUsbSetDesc (CY_U3P_USB_SET_STRING_DESCR, 0, (uint8_t *)otrStrLang);
    CyU3PUsbSetDesc (CY_U3P_USB_SET_STRING_DESCR, 1, (uint8_t *)otrStrManuf);
    CyU3PUsbSetDesc (CY_U3P_USB_SET_STRING_DESCR, 2, (uint8_t *)otrStrProduct);
    CyU3PUsbSetDesc (CY_U3P_USB_SET_STRING_DESCR, 3, otrStrSerial);

    CyU3PConnectState (CyTrue, CyTrue);   /* SuperSpeed enabled, falls back to USB 2 */
}
