/* SPDX-License-Identifier: MIT */
/* OTR-4TS3-U1 FX3 firmware: GPIF II slave FIFO (thread 0) -> DMA AUTO -> EP1 IN.
 *
 * The FPGA (gpif_sfifo_wr) fills each 16 KiB DMA buffer completely before it
 * moves on (D-43), so the AUTO channel commits full buffers to USB only.
 * The GPIF configuration header comes from our GPIF II Designer project
 * (fx3/gpif, D-41). Until that exists, the build uses the SDK sync slave FIFO
 * example configuration in 16-bit mode, taken from the SDK at build time and
 * never committed (D-37). */
#include "cyu3system.h"
#include "cyu3os.h"
#include "cyu3error.h"
#include "cyu3dma.h"
#include "cyu3usb.h"
#include "cyu3gpif.h"
#include "cyu3pib.h"
#include "otr_fw.h"

#if defined(OTR_GPIF_FROM_SDK_EXAMPLE)
#define CY_FX_SLFIFO_GPIF_16_32BIT_CONF_SELECT 0
#include "cyfxgpif_syncsf.h"
#else
#include "cyfxgpif2config.h"
#endif

static CyU3PDmaChannel otrDma;
static CyBool_t otrDmaCreated;
static CyBool_t otrStreaming;
static CyBool_t otrGpifReady;

void OtrStreamInit (void)
{
    CyU3PPibClock_t pib;

    CyU3PMemSet ((uint8_t *)&pib, 0, sizeof (pib));
    pib.clkDiv      = 2;
    pib.clkSrc      = CY_U3P_SYS_CLK;
    pib.isHalfDiv   = CyFalse;
    pib.isDllEnable = CyFalse;   /* external PCLK from the FPGA (sync slave) */
    if (CyU3PPibInit (CyTrue, &pib) != CY_U3P_SUCCESS)
        return;
    if (CyU3PGpifLoad (&CyFxGpifConfig) != CY_U3P_SUCCESS)
        return;
    /* Thread 0 <-> PIB socket 0 (FPGA writes, FIFO address 0). The watermark
     * is irrelevant: the FPGA counts words and uses FLAGA only (D-43). */
    CyU3PGpifSocketConfigure (0, CY_U3P_PIB_SOCKET_0, 3, CyFalse, 1);
    otrGpifReady = CyTrue;
}

void OtrStreamOnSetConf (CyBool_t superSpeed)
{
    CyU3PEpConfig_t ep;
    CyU3PDmaChannelConfig_t dma;

    CyU3PMemSet ((uint8_t *)&ep, 0, sizeof (ep));
    ep.enable   = CyTrue;
    ep.epType   = CY_U3P_USB_EP_BULK;
    ep.burstLen = superSpeed ? OTR_SS_BURST : 1;
    ep.streams  = 0;
    ep.pcktSize = superSpeed ? 1024 : 512;
    CyU3PSetEpConfig (OTR_EP_TS, &ep);

    if (otrDmaCreated) {
        CyU3PDmaChannelDestroy (&otrDma);
        otrDmaCreated = CyFalse;
    }
    CyU3PMemSet ((uint8_t *)&dma, 0, sizeof (dma));
    dma.size           = OTR_DMA_BUF_SIZE;
    dma.count          = OTR_DMA_BUF_COUNT;
    dma.prodSckId      = CY_U3P_PIB_SOCKET_0;
    dma.consSckId      = OTR_EP_TS_SOCKET;
    dma.dmaMode        = CY_U3P_DMA_MODE_BYTE;
    dma.notification   = 0;
    dma.cb             = NULL;
    dma.prodHeader     = 0;
    dma.prodFooter     = 0;
    dma.consHeader     = 0;
    dma.prodAvailCount = 0;
    if (CyU3PDmaChannelCreate (&otrDma, CY_U3P_DMA_TYPE_AUTO, &dma) == CY_U3P_SUCCESS)
        otrDmaCreated = CyTrue;
    CyU3PUsbFlushEp (OTR_EP_TS);
    otrStreaming = CyFalse;
}

void OtrStreamOnReset (void)
{
    if (otrStreaming)
        OtrStreamSet (CyFalse);
    if (otrDmaCreated) {
        CyU3PDmaChannelDestroy (&otrDma);
        otrDmaCreated = CyFalse;
    }
}

CyBool_t OtrStreamConfigured (void)
{
    return otrDmaCreated && otrGpifReady;
}

CyBool_t OtrStreamSet (CyBool_t on)
{
    if (!OtrStreamConfigured ())
        return CyFalse;
    if (on) {
        if (otrStreaming)
            return CyTrue;
        if (CyU3PDmaChannelSetXfer (&otrDma, 0) != CY_U3P_SUCCESS)   /* 0 = infinite */
            return CyFalse;
        if (CyU3PGpifSMStart (RESET, ALPHA_RESET) != CY_U3P_SUCCESS) {
            CyU3PDmaChannelReset (&otrDma);
            return CyFalse;
        }
        otrStreaming = CyTrue;
        return CyTrue;
    }
    /* Stop: the host must stop the FPGA (CH_ENABLE = 0) first. A partially
     * filled buffer is discarded here (otr-userland design.md section 7). */
    CyU3PGpifDisable (CyFalse);
    CyU3PDmaChannelReset (&otrDma);
    CyU3PUsbFlushEp (OTR_EP_TS);
    if (CyU3PGpifLoad (&CyFxGpifConfig) == CY_U3P_SUCCESS)
        CyU3PGpifSocketConfigure (0, CY_U3P_PIB_SOCKET_0, 3, CyFalse, 1);
    otrStreaming = CyFalse;
    return CyTrue;
}
