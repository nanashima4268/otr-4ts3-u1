/* SPDX-License-Identifier: MIT */
/* OTR-4TS3-U1 FX3 firmware: device bring-up and the application thread. */
#include "cyu3system.h"
#include "cyu3os.h"
#include "cyu3error.h"
#include "cyu3usb.h"
#include "cyu3uart.h"
#include "otr_fw.h"
#include "otr_board.h"

#define OTR_APP_THREAD_STACK    0x1000
#define OTR_APP_THREAD_PRIO     8

static CyU3PThread otrAppThread;

static void OtrErrorHalt (void)
{
    for (;;)
        CyU3PThreadSleep (100);
}

static void OtrDebugInit (void)
{
    CyU3PUartConfig_t cfg;

    if (CyU3PUartInit () != CY_U3P_SUCCESS)
        return;
    CyU3PMemSet ((uint8_t *)&cfg, 0, sizeof (cfg));
    cfg.baudRate = CY_U3P_UART_BAUDRATE_115200;
    cfg.stopBit  = CY_U3P_UART_ONE_STOP_BIT;
    cfg.parity   = CY_U3P_UART_NO_PARITY;
    cfg.txEnable = CyTrue;
    cfg.rxEnable = CyFalse;
    cfg.flowCtrl = CyFalse;
    cfg.isDma    = CyTrue;
    if (CyU3PUartSetConfig (&cfg, NULL) != CY_U3P_SUCCESS)
        return;
    CyU3PUartTxSetBlockXfer (0xFFFFFFFF);
    CyU3PDebugInit (CY_U3P_LPP_SOCKET_UART_CONS, 8);
    CyU3PDebugPreamble (CyFalse);
}

static void OtrAppThreadEntry (uint32_t input)
{
    (void)input;
    OtrDebugInit ();
    CyU3PDebugPrint (4, "OTR-4TS3-U1 fx3 fw %d.%d (protocol %d)\r\n",
                     OTR_FW_VERSION_MAJOR, OTR_FW_VERSION_MINOR, OTR_PROTOCOL_VERSION);
    OtrGpioInit ();
    OtrI2cInit ();
    OtrFpgaInit ();
    OtrFlashInit ();
    /* Before USB starts: the load borrows the DMA buffer area (D-49). */
    CyU3PDebugPrint (4, "FPGA autoload: %s\r\n", OtrFpgaAutoload () ? "ok" : "none");
    OtrStreamInit ();
    OtrUsbInit ();
    for (;;)
        CyU3PThreadSleep (1000);
}

/* Called by the RTOS once the kernel is running. */
void CyFxApplicationDefine (void)
{
    void *stack = CyU3PMemAlloc (OTR_APP_THREAD_STACK);
    uint32_t rc;

    if (stack == NULL)
        OtrErrorHalt ();
    rc = CyU3PThreadCreate (&otrAppThread, "21:OTR app", OtrAppThreadEntry, 0, stack,
                            OTR_APP_THREAD_STACK, OTR_APP_THREAD_PRIO, OTR_APP_THREAD_PRIO,
                            CYU3P_NO_TIME_SLICE, CYU3P_AUTO_START);
    if (rc != CY_U3P_SUCCESS)
        OtrErrorHalt ();
}

int main (void)
{
    CyU3PIoMatrixConfig_t io;
    CyU3PSysClockConfig_t clk;

    clk.setSysClk400  = CyTrue;    /* 403.2 MHz SYS_CLK, needed for a 100 MHz GPIF */
    clk.cpuClkDiv     = 2;
    clk.dmaClkDiv     = 2;
    clk.mmioClkDiv    = 2;
    clk.useStandbyClk = CyFalse;
    clk.clkSrc        = CY_U3P_SYS_CLK;
    if (CyU3PDeviceInit (&clk) != CY_U3P_SUCCESS)
        goto fail;
    if (CyU3PDeviceCacheControl (CyTrue, CyFalse, CyFalse) != CY_U3P_SUCCESS)
        goto fail;

    CyU3PMemSet ((uint8_t *)&io, 0, sizeof (io));
    io.isDQ32Bit        = CyFalse;          /* 16-bit GPIF keeps the SPI block (D-39, D-25) */
    io.useUart          = CyTrue;
    io.useI2C           = CyTrue;
    io.useI2S           = CyFalse;
    io.useSpi           = CyTrue;
    io.lppMode          = CY_U3P_IO_MATRIX_LPP_DEFAULT;
    /* Simple GPIOs 33..45, 50 and 57 (otr_board.h). 33..44 are DQ16..27, unused at 16 bits. */
    io.gpioSimpleEn[0]  = 0;
    io.gpioSimpleEn[1]  = (0x1FFFu << (33 - 32)) | (1u << (50 - 32)) | (1u << (57 - 32));
    io.gpioComplexEn[0] = 0;
    io.gpioComplexEn[1] = 0;
    if (CyU3PDeviceConfigureIOMatrix (&io) != CY_U3P_SUCCESS)
        goto fail;

    CyU3PKernelEntry ();
fail:
    for (;;)
        ;
    return 0;
}
