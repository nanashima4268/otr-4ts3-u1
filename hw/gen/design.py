# SPDX-License-Identifier: CERN-OHL-S-2.0
"""OTR-4TS3-U1 circuit description (phase 1: everything except the Sony
receiver core, which waits for the reference-board measurement).

Run `python3 hw/gen/design.py` to regenerate hw/kicad/*.kicad_sch and verify
that KiCad's netlist equals this description (D-51).

Net naming: +12V, +3V3, +1V2 (FX3 core), +1V2_FX3A (AVDD), +1V2_FX3U3 (USB3
PHY), +1V2_FPGA, VBUS, GND. Signals are named after their function.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from schgen import Design, Part, erc, verify          # noqa: E402
from symbols import fx3_balls                          # noqa: E402

OUT = os.path.join(HERE, "..", "kicad")
PROJECT = "otr-4ts3-u1"

# ---- part helpers ---------------------------------------------------------
FP_R = {"0402": "Resistor_SMD:R_0402_1005Metric"}
FP_C = {"0402": "Capacitor_SMD:C_0402_1005Metric", "0603": "Capacitor_SMD:C_0603_1608Metric",
        "0805": "Capacitor_SMD:C_0805_2012Metric"}
LCSC_R = {"0": "C17168", "33": "C25105", "200 1%": "C25087", "1k": "C11702", "2.2k": "C25879",
          "4.7k": "C25900", "6.04k 1%": "C97819", "10k": "C25744"}
LCSC_C = {("100n", "0402"): "C1525", ("1u", "0402"): "C52923", ("10u", "0603"): "C19702",
          ("22u", "0805"): "C45783", ("18p", "0402"): "C1549"}


class Refs:
    def __init__(self):
        self.n = {}

    def __call__(self, prefix):
        self.n[prefix] = self.n.get(prefix, 0) + 1
        return f"{prefix}{self.n[prefix]}"


ref = Refs()


def R(value, a, b, dnp=False):
    return Part(ref("R"), "Device:R", value.replace(" 1%", ""), FP_R["0402"], {"1": a, "2": b},
                lcsc=LCSC_R[value], dnp=dnp)


def C(value, a, b="GND", size="0402"):
    return Part(ref("C"), "Device:C", value + "F", FP_C[size], {"1": a, "2": b},
                lcsc=LCSC_C[(value, size)])


def FB(a, b):
    return Part(ref("FB"), "Device:FerriteBead", "120R@100MHz", "Inductor_SMD:L_0603_1608Metric",
                {"1": a, "2": b}, lcsc="C14709")


def TP(net, label=None):
    return Part(ref("TP"), "Connector:TestPoint", label or net, "TestPoint:TestPoint_Pad_D1.0mm",
                {"1": net})


def decouple(sheet, net, n100=1, bulk=None):
    for _ in range(n100):
        sheet.add(C("100n", net))
    if bulk:
        value, size = bulk
        sheet.add(C(value, net, size=size))


# ---- design -----------------------------------------------------------------
d = Design(PROJECT, {"otr": os.path.join(HERE, "..", "lib", "otr.kicad_sym")})


def fx3_sheet():
    """FX3 (CYUSB3014) with its clock, reset, boot flash and strapping.

    GPIO use follows fx3/fw/otr_board.h and the GPIF II header (D-39, D-48,
    D-49): GPIF 16-bit slave FIFO on GPIO 0-29, PMODE on 30-32 (SPI boot,
    USB fallback: PMODE[2:0] = 0,Z,1), board GPIOs on 33-45, FPGA SS on 50,
    SPI on 53-56 (SSN = boot flash), LED on 57, I2C on 58/59, UART TX on 48.
    """
    s = d.sheet("fx3", "FX3 USB3 bridge, boot flash")
    gpio = {i: "NC" for i in range(60)}
    for i in range(16):
        gpio[i] = f"GPIF_DQ{i}"
    gpio.update({16: "GPIF_PCLK", 17: "GPIF_SLCS_N", 18: "GPIF_SLWR_N", 19: "GPIF_SLOE_N",
                 20: "GPIF_SLRD_N", 21: "GPIF_FLAGA", 22: "GPIF_FLAGB", 24: "GPIF_PKTEND_N",
                 28: "GPIF_A1", 29: "GPIF_A0",
                 30: "FX3_PMODE0", 31: "NC", 32: "FX3_PMODE2",
                 33: "FPGA_CRESET_B", 34: "FPGA_CDONE", 43: "LNA_BYPASS", 45: "DC_IN_DET",
                 48: "FX3_UART_TX", 50: "FPGA_SS_N", 53: "SPI_SCK", 54: "SPI_SSN",
                 55: "SPI_MISO", 56: "SPI_MOSI", 57: "FX3_LED", 58: "I2C_SCL", 59: "I2C_SDA"})
    for ch in range(4):
        gpio[35 + ch] = f"CH{ch}_PWR_EN"
        gpio[39 + ch] = f"CH{ch}_RST_N"
    fixed = {"VDD": "+1V2", "AVDD": "+1V2_FX3A", "U3TXVDDQ": "+1V2_FX3U3", "U3RXVDDQ": "+1V2_FX3U3",
             "CVDDQ": "+3V3", "VIO1": "+3V3", "VIO2": "+3V3", "VIO3": "+3V3", "VIO4": "+3V3",
             "VIO5": "+3V3", "VBATT": "VBUS", "VBUS": "VBUS", "VSS": "GND", "AVSS": "GND",
             "U3VSSQ": "GND", "NC": "NC", "DP": "USB_DP", "DM": "USB_DM", "SSRXP": "USB_SSRX_P",
             "SSRXM": "USB_SSRX_N", "SSTXP": "FX3_SSTX_P", "SSTXM": "FX3_SSTX_N",
             "R_USB3": "FX3_R_USB3", "R_USB2": "FX3_R_USB2", "OTG_ID": "NC",
             "FSLC[0]": "GND", "FSLC[1]": "GND", "FSLC[2]": "GND",   # 19.2 MHz crystal
             "XTALIN": "FX3_XTALIN", "XTALOUT": "FX3_XTALOUT", "CLKIN": "NC", "CLKIN_32": "NC",
             "RESET#": "FX3_RESET_N", "TDI": "FX3_TDI", "TDO": "FX3_TDO", "TMS": "FX3_TMS",
             "TCK": "FX3_TCK", "TRST#": "FX3_TRST_N", "INT#": "FX3_INT_N"}
    nets = {}
    for ball, name in fx3_balls().items():
        if name.startswith(("GPIO[", "I2C_GPIO[")):
            nets[ball] = gpio[int(name.split("[")[1].rstrip("]"))]
        else:
            nets[ball] = fixed[name]
    s.add(Part(ref("U"), "otr:CYUSB3014-BZXI", "CYUSB3014-BZXI",
               "Package_BGA:TFBGA-121_10x10mm_Layout11x11_P0.8mm", nets, lcsc="C57294"))

    # supplies: core 1.2 V, AVDD and USB3 PHY through ferrites (same 1.2 V rail)
    decouple(s, "+1V2", n100=4, bulk=("22u", "0805"))
    s.add(FB("+1V2", "+1V2_FX3A"))
    decouple(s, "+1V2_FX3A", n100=1, bulk=("10u", "0603"))
    s.add(FB("+1V2", "+1V2_FX3U3"))
    decouple(s, "+1V2_FX3U3", n100=2, bulk=("10u", "0603"))
    decouple(s, "+3V3", n100=6, bulk=("10u", "0603"))
    s.add(C("1u", "VBUS"), C("100n", "VBUS"))
    # USB precision resistors, SuperSpeed TX AC coupling
    s.add(R("200 1%", "FX3_R_USB3", "GND"), R("6.04k 1%", "FX3_R_USB2", "GND"))
    s.add(C("100n", "FX3_SSTX_P", "USB_SSTX_P"), C("100n", "FX3_SSTX_N", "USB_SSTX_N"))
    # 19.2 MHz crystal, CL 12 pF -> 2 x (12 - ~3 pF stray) = 18 pF
    s.add(Part(ref("Y"), "Device:Crystal_GND24", "19.2MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
               {"1": "FX3_XTALIN", "2": "GND", "3": "FX3_XTALOUT", "4": "GND"}, lcsc="C358650"))
    s.add(C("18p", "FX3_XTALIN"), C("18p", "FX3_XTALOUT"))
    # reset: RC (>= 1 ms after the supplies settle) and a test pad
    s.add(R("10k", "FX3_RESET_N", "+3V3"), C("1u", "FX3_RESET_N"), TP("FX3_RESET_N", "RESET"))
    # boot mode SPI with USB fallback: PMODE0 = 1, PMODE1 = Z, PMODE2 = 0
    s.add(R("10k", "FX3_PMODE0", "+3V3"), R("10k", "FX3_PMODE2", "GND"))
    # JTAG on pads, TRST# held low; INT# unused (pulled up)
    s.add(R("10k", "FX3_TRST_N", "GND"), R("10k", "FX3_INT_N", "+3V3"))
    for n in ("FX3_TDI", "FX3_TDO", "FX3_TMS", "FX3_TCK", "FX3_TRST_N"):
        s.add(TP(n, n.replace("FX3_", "")))
    s.add(TP("FX3_UART_TX", "UART_TX"))
    # I2C pull-ups (TCA9546A upstream side, 3.3 V)
    s.add(R("2.2k", "I2C_SCL", "+3V3"), R("2.2k", "I2C_SDA", "+3V3"))
    # LED
    s.add(R("1k", "FX3_LED", "FX3_LED_K"))
    s.add(Part(ref("D"), "Device:LED", "LED", "LED_SMD:LED_0603_1608Metric",
               {"1": "GND", "2": "FX3_LED_K"}, lcsc="C2286"))

    # boot flash (D-49): SSN through 1 k so that the BOOT_USB jumper can hold
    # CS# high; SPI boot then fails and the ROM falls back to USB boot.
    s.add(R("1k", "SPI_SSN", "FLASH_CS_N"))
    s.add(Part(ref("JP"), "Jumper:SolderJumper_2_Open", "BOOT_USB",
               "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm",
               {"1": "FLASH_CS_N", "2": "+3V3"}))
    s.add(Part(ref("U"), "Memory_Flash:W25Q32JVSS", "W25Q32JVSSIQ", "Package_SO:SOIC-8_5.3x5.3mm_P1.27mm",
               {"1": "FLASH_CS_N", "2": "SPI_MISO", "3": "FLASH_WP_N", "4": "GND", "5": "SPI_MOSI",
                "6": "SPI_SCK", "7": "FLASH_HOLD_N", "8": "+3V3"}, lcsc="C179173"))
    s.add(R("10k", "FLASH_WP_N", "+3V3"), R("10k", "FLASH_HOLD_N", "+3V3"))
    decouple(s, "+3V3", n100=1)


def build():
    fx3_sheet()
    d.write(OUT)
    ok, msgs = verify(d, OUT)
    print("netlist matches description:", ok)
    for m in msgs[:20]:
        print("  ", m)
    rpt = erc(d, OUT)
    print([l for l in rpt.splitlines() if "ERC messages" in l])
    return ok


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
