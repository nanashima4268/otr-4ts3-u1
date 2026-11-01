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
          "4.7k": "C25900", "6.04k 1%": "C97819", "10k": "C25744", "22k": "C25768", "33k": "C25779",
          "100k": "C25741", "200k": "C25764", "910k": "C2909391", "27": "C25156", "45.3": "C5126226"}
LCSC_C = {("100n", "0402"): "C1525", ("1u", "0402"): "C52923", ("10u", "0603"): "C19702",
          ("22u", "0805"): "C45783", ("18p", "0402"): "C1549", ("10u25", "0805"): "C15850",
          ("1n", "0402"): "C1523", ("100p", "0402"): "C1546", ("1.2n", "0402"): "C3010430",
          ("75p", "0402"): "C107010", ("4.7u", "0402"): "C23733"}


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


def C(value, a, b="GND", size="0402", dnp=False):
    shown = "10uF 25V" if value == "10u25" else value + "F"
    return Part(ref("C"), "Device:C", shown, FP_C[size], {"1": a, "2": b},
                lcsc=LCSC_C[(value, size)], dnp=dnp)


def R0(a, b, size="0402", dnp=False):
    """0 ohm link (option selection); 1206 for supply currents."""
    fp = {"0402": FP_R["0402"], "1206": "Resistor_SMD:R_1206_3216Metric"}[size]
    return Part(ref("R"), "Device:R", "0", fp, {"1": a, "2": b},
                lcsc={"0402": "C17168", "1206": "C17888"}[size], dnp=dnp)


def L(value, a, b, fp, lcsc):
    return Part(ref("L"), "Device:L", value, fp, {"1": a, "2": b}, lcsc=lcsc)


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
    # USB precision resistors (SuperSpeed TX AC coupling is on the USB sheet,
    # after the Type-C switch, or in the header path)
    s.add(R("200 1%", "FX3_R_USB3", "GND"), R("6.04k 1%", "FX3_R_USB2", "GND"))
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


# FPGA pin plan (D-07): bank 0 = GPIF (3.3 V), banks 1 and 3 = serial TS
# (VCCIO = +VIO_TS, selectable because the demodulator TS level is not yet
# measured), bank 2 = 50 MHz clock, status LED and test pads. TS clocks and
# the system clock sit on global buffer pins (GBIN).
FPGA_PINS = {
    # bank 0 (top): GPIF II slave FIFO toward the FX3
    "dq[0]": 110, "dq[1]": 112, "dq[2]": 113, "dq[3]": 114, "dq[4]": 115, "dq[5]": 116,
    "dq[6]": 117, "dq[7]": 118, "dq[8]": 119, "dq[9]": 120, "dq[10]": 121, "dq[11]": 122,
    "dq[12]": 124, "dq[13]": 125, "dq[14]": 128, "dq[15]": 129,
    "slcs_n": 130, "slwr_n": 134, "sloe_n": 135, "slrd_n": 136, "pktend_n": 137,
    "fifo_addr[0]": 138, "fifo_addr[1]": 139, "flaga": 141, "flagb": 142,
    # bank 3 (left): TS channels 0 and 1, clocks on GBIN7/GBIN6
    "ts_clk[0]": 20, "ts_data[0]": 19, "ts_valid[0]": 18, "ts_sync[0]": 17,
    "ts_clk[1]": 21, "ts_data[1]": 22, "ts_valid[1]": 23, "ts_sync[1]": 24,
    # bank 1 (right): TS channels 2 and 3, clocks on GBIN3/GBIN2
    "ts_clk[2]": 93, "ts_data[2]": 91, "ts_valid[2]": 90, "ts_sync[2]": 88,
    "ts_clk[3]": 94, "ts_data[3]": 95, "ts_valid[3]": 96, "ts_sync[3]": 97,
    # bank 2 (bottom): 50 MHz on GBIN5, gpio_out[0] = LED, [1..3] = test pads
    "clk": 49, "gpio_out[0]": 37, "gpio_out[1]": 38, "gpio_out[2]": 39, "gpio_out[3]": 41,
    # configuration SPI pins, user I/O after configuration (D-47)
    "spi_miso": 67, "spi_mosi": 68, "spi_sck": 70, "spi_ss_n": 71,
}
GPIF_NET = {"slcs_n": "GPIF_SLCS_N", "slwr_n": "GPIF_SLWR_N", "sloe_n": "GPIF_SLOE_N",
            "slrd_n": "GPIF_SLRD_N", "pktend_n": "GPIF_PKTEND_N", "fifo_addr[0]": "GPIF_A0",
            "fifo_addr[1]": "GPIF_A1", "flaga": "GPIF_FLAGA", "flagb": "GPIF_FLAGB"}


def fpga_port_net(port):
    if port.startswith("dq["):
        return "GPIF_DQ" + port[3:-1]
    if port in GPIF_NET:
        return GPIF_NET[port]
    if port.startswith("ts_"):
        kind, ch = port[3:].split("[")
        return f"TS{ch[:-1]}_{kind.upper()}"
    if port == "clk":
        return "FPGA_CLK50"
    if port.startswith("gpio_out["):
        return "FPGA_GPIO" + port[9:-1]
    return {"spi_miso": "SPI_MISO", "spi_mosi": "SPI_MOSI", "spi_sck": "SPI_SCK",
            "spi_ss_n": "FPGA_SS_N"}[port]


def write_pcf(path):
    lines = ["# Generated by hw/gen/design.py from the schematic pin plan; do not edit.",
             "# iCE40HX4K-TQ144 (nextpnr: --hx8k --package tq144:4k)."]
    for port, pin in FPGA_PINS.items():
        lines.append(f"set_io {port} {pin}")
    open(path, "w").write("\n".join(lines) + "\n")


def fpga_sheet():
    s = d.sheet("fpga", "iCE40 FPGA (TS mux, GPIF writer)")
    lib_id = "FPGA_Lattice:ICE40HX4K-TQ144"
    pins = d.lib.pins(lib_id)
    by_pin = {pin: fpga_port_net(port) for port, pin in FPGA_PINS.items()}
    power = {"VCC": "+1V2_FPGA", "VCCPLL0": "+1V2_FPGA", "VCCPLL1": "+1V2_FPGA",
             "GNDPLL0": "GND", "GNDPLL1": "GND", "GND": "GND", "VPP_2V5": "+3V3",
             "VPP_FAST": "NC", "VCC_SPI": "+3V3", "VCCIO_0": "+3V3", "VCCIO_2": "+3V3",
             "VCCIO_1": "+VIO_TS", "VCCIO_3": "+VIO_TS", "CDONE": "FPGA_CDONE",
             "~{CRESET}": "FPGA_CRESET_B", "NC": "NC"}
    nets = {}
    for num, entries in pins.items():
        name = entries[0][3]
        if int(num) in by_pin:
            nets[num] = by_pin[int(num)]
        elif name in power:
            nets[num] = power[name]
        else:
            nets[num] = "NC"   # unused I/O
    s.add(Part(ref("U"), lib_id, "ICE40HX4K-TQ144", "Package_QFP:TQFP-144_20x20mm_P0.5mm", nets,
               lcsc="C1521989"))
    decouple(s, "+1V2_FPGA", n100=4, bulk=("10u", "0603"))
    decouple(s, "+3V3", n100=5)          # VCCIO_0 x2, VCCIO_2 x2, VCC_SPI/VPP
    decouple(s, "+VIO_TS", n100=4, bulk=("10u", "0603"))
    # configuration: CRESET_B held low until the FX3 loads the FPGA (D-49),
    # CDONE is open drain, SS_B idles high (shared SPI bus)
    s.add(R("10k", "FPGA_CRESET_B", "GND"), R("10k", "FPGA_CDONE", "+3V3"),
          R("10k", "FPGA_SS_N", "+3V3"))
    # 50 MHz: one oscillator for the FPGA and the FX3 PCLK, each through a
    # series resistor (the FPGA logic and the GPIF share this clock, D-39)
    s.add(Part(ref("X"), "Oscillator:XO32", "50MHz", "Oscillator:Oscillator_SMD_EuroQuartz_XO32-4Pin_3.2x2.5mm",
               {"1": "+3V3", "2": "GND", "3": "CLK50", "4": "+3V3"}, lcsc="C5203552"))
    decouple(s, "+3V3", n100=1)
    s.add(R("33", "CLK50", "FPGA_CLK50"), R("33", "CLK50", "GPIF_PCLK"))
    # status LED and test pads on gpio_out (FPGA register 0x08)
    s.add(R("1k", "FPGA_GPIO0", "FPGA_LED_A"))
    s.add(Part(ref("D"), "Device:LED", "LED", "LED_SMD:LED_0603_1608Metric",
               {"1": "GND", "2": "FPGA_LED_A"}, lcsc="C2286"))
    for i in (1, 2, 3):
        s.add(TP(f"FPGA_GPIO{i}", f"FPGA_IO{i}"))


def power_sheet():
    """Supplies (architecture.md section 3, D-08, D-30, D-54).

    12 V from the PCIe slot or the DC input (box use), OR-ed by Schottky
    diodes -> TPS54302 buck -> +3V3 (3 A). The slot 3.3 V can feed +3V3
    instead (DNP links). LDOs from +3V3: +1V2 (FX3 core), +1V2_FPGA, +1V8.
    +VIO_TS (FPGA TS banks) is +3V3 by default, +1V8 as an option, until the
    demodulator TS level is measured. Receiver rails come with the receiver
    sheet after the measurement.
    """
    s = d.sheet("power", "Power: PCIe/DC input, 3.3 V buck, LDOs")
    pcie = {"A2": "PCIE_12V", "A3": "PCIE_12V", "B1": "PCIE_12V", "B2": "PCIE_12V", "B3": "PCIE_12V",
            "A9": "PCIE_3V3", "A10": "PCIE_3V3", "B8": "PCIE_3V3",
            "A1": "PCIE_PRSNT", "B17": "PCIE_PRSNT"}   # x1 presence loop (PRSNT1# - PRSNT2#)
    for pin, entries in d.lib.pins("Connector:Bus_PCI_Express_x1").items():
        if pin not in pcie:
            pcie[pin] = "GND" if entries[0][3] == "GND" else "NC"
    s.add(Part(ref("J"), "Connector:Bus_PCI_Express_x1", "PCIe x1 (power only)",
               "Connector_PCBEdge:BUS_PCIexpress_x1", pcie))
    s.add(Part(ref("J"), "Connector_Generic:Conn_01x02", "DC 12V in", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
               {"1": "DC_12V", "2": "GND"}, lcsc="C158012"))
    for src in ("PCIE_12V", "DC_12V"):
        s.add(Part(ref("D"), "Device:D_Schottky", "SS34", "Diode_SMD:D_SMA", {"1": "+12V", "2": src},
                   lcsc="C8678"))
    # DC input present -> FX3 GPIO45 (LNB permission in firmware, D-30)
    s.add(R("100k", "DC_12V", "DC_IN_DET"), R("33k", "DC_IN_DET", "GND"))
    # buck 12 V -> 3.3 V, 3 A (TPS54302 datasheet 7.2): Vout = 0.596 (1 + 100k/22k) = 3.31 V,
    # L >= 5.9 uH at 13.2 V in, K_IND 0.35 -> 6.8 uH
    s.add(C("10u25", "+12V", size="0805"), C("10u25", "+12V", size="0805"), C("100n", "+12V"))
    s.add(Part(ref("U"), "Regulator_Switching:TPS54302", "TPS54302", "Package_TO_SOT_SMD:SOT-23-6",
               {"1": "GND", "2": "BUCK_SW", "3": "+12V", "4": "BUCK_FB", "5": "+12V", "6": "BUCK_BOOT"},
               lcsc="C311983"))
    s.add(C("100n", "BUCK_BOOT", "BUCK_SW"))
    s.add(L("6.8uH", "BUCK_SW", "+3V3_BUCK", "Inductor_SMD:L_6.3x6.3_H3", "C354631"))
    s.add(C("22u", "+3V3_BUCK", size="0805"), C("22u", "+3V3_BUCK", size="0805"))
    s.add(R("100k", "+3V3_BUCK", "BUCK_FB"), R("22k", "BUCK_FB", "GND"), C("75p", "+3V3_BUCK", "BUCK_FB"))
    # +3V3 source: buck (fitted) or slot 3.3 V (DNP), two 1206 links each for 3 A
    s.add(R0("+3V3_BUCK", "+3V3", "1206"), R0("+3V3_BUCK", "+3V3", "1206"))
    s.add(R0("PCIE_3V3", "+3V3", "1206", dnp=True), R0("PCIE_3V3", "+3V3", "1206", dnp=True))
    s.add(C("22u", "+3V3", size="0805"))
    # LDOs
    for out, part, lcsc in (("+1V2", "TLV75512PDBV", "C2877864"), ("+1V2_FPGA", "TLV75512PDBV", "C2877864"),
                            ("+1V8", "TLV75518PDBV", "C2877863")):
        s.add(C("1u", "+3V3"))
        s.add(Part(ref("U"), "Regulator_Linear:" + part, part.replace("PDBV", "PDBVR"),
                   "Package_TO_SOT_SMD:SOT-23-5", {"1": "+3V3", "2": "GND", "3": "+3V3", "4": "NC", "5": out},
                   lcsc=lcsc))
        s.add(C("4.7u", out))
    # FPGA TS bank voltage: 3.3 V fitted, 1.8 V option
    s.add(R0("+3V3", "+VIO_TS"), R0("+1V8", "+VIO_TS", dnp=True))
    # power flags: these nets are driven from connectors
    for net in ("+12V", "GND", "VBUS", "PCIE_12V", "PCIE_3V3"):
        s.add(Part(ref("#FLG"), "power:PWR_FLAG", "PWR_FLAG", "", {"1": net}))
    for net in ("+3V3", "+VIO_TS", "+1V2_FX3A", "+1V2_FX3U3"):
        s.add(Part(ref("#FLG"), "power:PWR_FLAG", "PWR_FLAG", "", {"1": net}))


def usb_sheet():
    """USB: Type-C on the bracket with HD3SS3220 (UFP, D-56), or the internal
    USB3 header (D-09). The FX3 side is selected with 0 ohm links: C path
    fitted, header path DNP. SuperSpeed TX AC coupling sits after the switch
    (TI figure 7-3); the header path has its own TX capacitors.
    """
    s = d.sheet("usb", "USB: Type-C with SS switch, internal USB3 header")
    # FX3 side -> selection links
    for a, b_c, b_h in (("FX3_SSTX_P", "MUX_TX_P", "HDR_TX_P"), ("FX3_SSTX_N", "MUX_TX_N", "HDR_TX_N"),
                        ("USB_SSRX_P", "MUX_RX_P", "HDR_SSTX_P"), ("USB_SSRX_N", "MUX_RX_N", "HDR_SSTX_N"),
                        ("USB_DP", "USBC_DP", "HDR_DP"), ("USB_DM", "USBC_DM", "HDR_DM")):
        s.add(R0(a, b_c), R0(a, b_h, dnp=True))
    # HD3SS3220: UFP (PORT low), GPIO mode (ADDR open), CC and mux enabled
    hd = {1: "USBC_CC2", 2: "USBC_CC1", 3: "NC", 4: "GND", 5: "HD_VBUS_DET", 6: "MUX_TX_P", 7: "MUX_TX_N",
          8: "+3V3", 9: "MUX_RX_P", 10: "MUX_RX_N", 11: "HD_DIR", 12: "GND", 13: "GND", 14: "USBC_RX1_N",
          15: "USBC_RX1_P", 16: "MUX_TX1_N", 17: "MUX_TX1_P", 18: "USBC_RX2_N", 19: "USBC_RX2_P",
          20: "MUX_TX2_N", 21: "MUX_TX2_P", 22: "NC", 23: "NC", 24: "NC", 25: "NC", 26: "NC", 27: "NC",
          28: "GND", 29: "GND", 30: "VBUS", 31: "GND"}
    s.add(Part(ref("U"), "otr:HD3SS3220", "HD3SS3220IRNHR",
               "Package_DFN_QFN:Texas_RNH0030A_WQFN-30-1EP_2.5x4.5mm_P0.4mm_EP1.2x3.2mm",
               {str(k): v for k, v in hd.items()}, lcsc="C701817"))
    s.add(R("910k", "VBUS", "HD_VBUS_DET"), R("200k", "HD_DIR", "+3V3"))
    s.add(C("100n", "VBUS"), C("100n", "+3V3"))
    for p_, n_ in (("TX1_P", "USBC_TX1_P"), ("TX1_N", "USBC_TX1_N"), ("TX2_P", "USBC_TX2_P"), ("TX2_N", "USBC_TX2_N")):
        s.add(C("100n", "MUX_" + p_, n_))
    usbc = {"A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "A4": "VBUS", "A9": "VBUS", "B4": "VBUS",
            "B9": "VBUS", "A5": "USBC_CC1", "B5": "USBC_CC2", "A6": "USBC_DP", "B6": "USBC_DP",
            "A7": "USBC_DM", "B7": "USBC_DM", "A8": "NC", "B8": "NC", "A2": "USBC_TX1_P", "A3": "USBC_TX1_N",
            "B11": "USBC_RX1_P", "B10": "USBC_RX1_N", "B2": "USBC_TX2_P", "B3": "USBC_TX2_N",
            "A11": "USBC_RX2_P", "A10": "USBC_RX2_N", "SH": "GND"}
    s.add(Part(ref("J"), "Connector:USB_C_Receptacle", "USB-C (USB 3.2)",
               "Connector_USB:USB_C_Receptacle_Molex_105450-0101", usbc, lcsc="C134092"))
    # internal USB3 header (Intel 20-pin, port 1 pins; pin 20 = key), DNP by default
    s.add(C("100n", "HDR_TX_P", "HDR_SSRX_P", dnp=True), C("100n", "HDR_TX_N", "HDR_SSRX_N", dnp=True))
    hdr = {"1": "HDR_VBUS", "2": "NC", "3": "NC", "4": "GND", "5": "NC", "6": "NC", "7": "GND", "8": "NC",
           "9": "NC", "10": "NC", "11": "HDR_DP", "12": "HDR_DM", "13": "GND", "14": "HDR_SSTX_P",
           "15": "HDR_SSTX_N", "16": "GND", "17": "HDR_SSRX_P", "18": "HDR_SSRX_N", "19": "HDR_VBUS",
           "20": "NC"}
    s.add(Part(ref("J"), "Connector_Generic:Conn_02x10_Odd_Even", "USB3 header (DNP)",
               "Connector_PinHeader_2.00mm:PinHeader_2x10_P2.00mm_Vertical", hdr, dnp=True))
    s.add(R0("HDR_VBUS", "VBUS", dnp=True))


def control_sheet():
    """I2C: FX3 -> TCA9546A (0x70, D-24) -> one channel per receiver. The
    downstream pull-ups go to +VIO_TS until the demodulator I/O level is
    measured. LNA bypass control with its complement for the AS179 switches.
    """
    s = d.sheet("control", "I2C mux, LNA bypass control")
    mux = {"1": "GND", "2": "GND", "13": "GND", "3": "I2C_MUX_RST_N", "8": "GND", "16": "+3V3",
           "14": "I2C_SCL", "15": "I2C_SDA"}
    for ch, (sd, sc) in enumerate((("4", "5"), ("6", "7"), ("9", "10"), ("11", "12"))):
        mux[sd] = f"I2C{ch}_SDA"
        mux[sc] = f"I2C{ch}_SCL"
        s.add(R("4.7k", f"I2C{ch}_SDA", "+VIO_TS"), R("4.7k", f"I2C{ch}_SCL", "+VIO_TS"))
    s.add(Part(ref("U"), "Interface_Expansion:TCA9546APW", "TCA9546APWR", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
               mux, lcsc="C201653"))
    s.add(R("10k", "I2C_MUX_RST_N", "+3V3"), C("100n", "+3V3"))
    # LNA_BYPASS (FX3 GPIO43): 0 = LNA in path (pulled down while the FX3 boots)
    s.add(R("100k", "LNA_BYPASS", "GND"))
    s.add(Part(ref("U"), "74xGxx:74LVC1G04", "74LVC1G04", "Package_TO_SOT_SMD:SOT-353_SC-70-5",
               {"1": "NC", "2": "LNA_BYPASS", "3": "GND", "4": "LNA_BYPASS_N", "5": "+3V3"}, lcsc="C264081"))
    s.add(C("100n", "+3V3"))


def rf_path(s, band, conn_net):
    """One antenna input: F jack -> ESD -> SPDT -> (LNA | bypass) -> SPDT ->
    resistive 4-way star (45.3 ohm arms, 75 ohm) -> RF_<band><ch>.
    AS179: V1 high/V2 low = J1-J3 (LNA), V1 low/V2 high = J1-J2 (bypass);
    every switch port needs a DC block (positive control).
    T (90-770 MHz): 1 nF blocks, choke 1 uH + 600 ohm bead.
    S (1-3.2 GHz IF): 100 pF blocks, choke 12 nH + bead.
    """
    blk = "1n" if band == "T" else "100p"
    p = f"RF{band}_"
    s.add(Part(ref("J"), "Connector:Conn_Coaxial", f"ANT-{band} (F)", "otr:F_Female_DOSIN_DS803FPR0016_Horizontal",
               {"1": conn_net, "2": "GND"}, lcsc="C2979612"))
    s.add(Part(ref("D"), "Device:D_TVS", "PESD0402-140", "Diode_SMD:D_0402_1005Metric",
               {"1": conn_net, "2": "GND"}, lcsc="C10662"))
    s.add(C(blk, conn_net, p + "SWA_J1"))
    for sw, j1 in (("A", p + "SWA_J1"), ("B", p + "SWB_J1")):
        s.add(Part(ref("U"), "RF_Switch:AS179-92LF", "HXAS179-92LF", "Package_TO_SOT_SMD:SOT-363_SC-70-6",
                   {"1": p + f"SW{sw}_J3", "2": "GND", "3": p + f"SW{sw}_J2", "4": "LNA_BYPASS_N", "5": j1,
                    "6": "LNA_BYPASS"}, lcsc="C49010110"))
    s.add(C(blk, p + "SWA_J3", p + "LNA_IN"), C(blk, p + "LNA_OUT", p + "SWB_J3"))
    s.add(C(blk, p + "SWA_J2", p + "SWB_J2"))      # bypass line
    s.add(Part(ref("U"), "RF_Amplifier:SGL0622Z", "SGL0622Z", "Package_DFN_QFN:DFN-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm",
               {"1": p + "LNA_OUT", "4": p + "LNA_IN", **{str(k): "GND" for k in (2, 3, 5, 6, 7, 8, 9)}},
               lcsc="C470895"))
    # bias: +3V3 -> 27 ohm (current limit, datasheet note 3) -> bead -> inductor -> RF OUT/VD
    s.add(R("27", "+3V3", p + "VS"), C("1u", p + "VS"), C("1.2n", p + "VS"))
    s.add(Part(ref("FB"), "Device:FerriteBead", "600R@100MHz", "Inductor_SMD:L_0402_1005Metric",
               {"1": p + "VS", "2": p + "CHOKE"}, lcsc="C76890"))
    if band == "T":
        s.add(L("1uH", p + "CHOKE", p + "LNA_OUT", "Inductor_SMD:L_0603_1608Metric", "C98326"))
    else:
        s.add(L("12nH", p + "CHOKE", p + "LNA_OUT", "Inductor_SMD:L_0402_1005Metric", "C77104"))
    # 4-way resistive star from SWB J1: R = Z0 (N-1)/(N+1) = 45 ohm, one per arm
    s.add(C(blk, p + "SWB_J1", p + "SPLIT_IN"))
    s.add(R("45.3", p + "SPLIT_IN", p + "STAR"))
    for ch in range(4):
        s.add(R("45.3", p + "STAR", f"RF_{band}{ch}"))


def rf_sheet():
    s = d.sheet("rf", "RF front end: F jacks, LNA with bypass, 4-way splitters")
    rf_path(s, "T", "ANT_T")
    rf_path(s, "S", "ANT_S")


def write_lib_tables(outdir):
    """Project library tables for every library the design uses."""
    syms, fps = {"otr"}, {"otr"}
    for sh in d.sheets:
        for part in sh.parts:
            syms.add(part.lib_id.split(":")[0])
            if part.footprint:
                fps.add(part.footprint.split(":")[0])
    def row(name, uri):
        return f'  (lib (name "{name}")(type "KiCad")(uri "{uri}")(options "")(descr ""))'
    sym = ["(sym_lib_table", "  (version 7)"]
    for n in sorted(syms):
        sym.append(row(n, "${KIPRJMOD}/../lib/otr.kicad_sym" if n == "otr" else "${KICAD10_SYMBOL_DIR}/" + n + ".kicad_sym"))
    fp = ["(fp_lib_table", "  (version 7)"]
    for n in sorted(fps):
        fp.append(row(n, "${KIPRJMOD}/../lib/otr.pretty" if n == "otr" else "${KICAD10_FOOTPRINT_DIR}/" + n + ".pretty"))
    open(os.path.join(outdir, "sym-lib-table"), "w").write("\n".join(sym + [")"]) + "\n")
    open(os.path.join(outdir, "fp-lib-table"), "w").write("\n".join(fp + [")"]) + "\n")


def build():
    fx3_sheet()
    fpga_sheet()
    power_sheet()
    usb_sheet()
    control_sheet()
    rf_sheet()
    write_pcf(os.path.join(HERE, "..", "..", "fpga", "syn", "otr_top.pcf"))
    d.write(OUT)
    write_lib_tables(OUT)
    ok, msgs = verify(d, OUT)
    print("netlist matches description:", ok)
    for m in msgs[:20]:
        print("  ", m)
    rpt = erc(d, OUT)
    print([l for l in rpt.splitlines() if "ERC messages" in l])
    return ok


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
