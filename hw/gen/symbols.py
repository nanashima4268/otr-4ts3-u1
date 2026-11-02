# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Project symbols that the KiCad library lacks, written to hw/lib/otr.kicad_sym.

CYUSB3014-BZXI (FX3, 121-ball BGA): ball map from the FX3 datasheet
(001-79276, figure "121 Ball BGA ball map", top view). Pins are grouped by
function on four sides; stacked power balls of one rail are separate pins.
"""
import os
import uuid

from sexp import Q, dump

FX3_BALLS = {
    "A": "U3VSSQ U3RXVDDQ SSRXM SSRXP SSTXP SSTXM AVDD VSS DP DM NC",
    "B": "VIO4 FSLC[0] R_USB3 FSLC[1] U3TXVDDQ CVDDQ AVSS VSS VSS VDD TRST#",
    "C": "GPIO[54] GPIO[55] VDD GPIO[57] RESET# XTALIN XTALOUT R_USB2 OTG_ID TDO VIO5",
    "D": "GPIO[50] GPIO[51] GPIO[52] GPIO[53] GPIO[56] CLKIN_32 CLKIN VSS I2C_GPIO[58] I2C_GPIO[59] NC",
    "E": "GPIO[47] VSS VIO3 GPIO[49] GPIO[48] FSLC[2] TDI TMS VDD VBATT VBUS",
    "F": "VIO2 GPIO[45] GPIO[44] GPIO[41] GPIO[46] TCK GPIO[2] GPIO[5] GPIO[1] GPIO[0] VDD",
    "G": "VSS GPIO[42] GPIO[43] GPIO[30] GPIO[25] GPIO[22] GPIO[21] GPIO[15] GPIO[4] GPIO[3] VSS",
    "H": "VDD GPIO[39] GPIO[40] GPIO[31] GPIO[29] GPIO[26] GPIO[20] GPIO[24] GPIO[7] GPIO[6] VIO1",
    "J": "GPIO[38] GPIO[36] GPIO[37] GPIO[34] GPIO[28] GPIO[16] GPIO[19] GPIO[14] GPIO[9] GPIO[8] VDD",
    "K": "GPIO[35] GPIO[33] VSS VSS GPIO[27] GPIO[23] GPIO[18] GPIO[17] GPIO[13] GPIO[12] GPIO[10]",
    "L": "VSS VSS VSS GPIO[32] VDD VSS VDD INT# VIO1 GPIO[11] VSS",
}

POWER = ("VDD", "AVDD", "U3TXVDDQ", "U3RXVDDQ", "CVDDQ", "VIO1", "VIO2", "VIO3", "VIO4", "VIO5",
         "VBATT", "VBUS")
GROUND = ("VSS", "AVSS", "U3VSSQ")


def fx3_balls():
    """{ball: name} for all 121 balls."""
    out = {}
    for row, names in FX3_BALLS.items():
        for col, name in enumerate(names.split(), start=1):
            out[f"{row}{col}"] = name
    assert len(out) == 121
    return out


def _ptype(name):
    if name in POWER:
        return "power_in"
    if name in GROUND:
        return "power_in"
    if name == "NC":
        return "no_connect"
    if name.startswith(("GPIO", "I2C_GPIO", "DP", "DM")):
        return "bidirectional"
    if name in ("SSTXP", "SSTXM", "TDO"):
        return "output"
    if name in ("SSRXP", "SSRXM", "RESET#", "TRST#", "TDI", "TMS", "TCK", "CLKIN", "CLKIN_32",
                "OTG_ID", "INT#") or name.startswith("FSLC"):
        return "input"
    return "passive"


def _pin(ptype, x, y, angle, name, number, hide_name=False):
    return ["pin", ptype, "line", ["at", x, y, angle], ["length", 2.54],
            ["name", Q(name), ["effects", ["font", ["size", 1.0, 1.0]]]],
            ["number", Q(number), ["effects", ["font", ["size", 1.0, 1.0]]]]]


def _gpio_key(name):
    digits = "".join(c for c in name if c.isdigit())
    return int(digits) if digits else 999


def fx3_symbol():
    balls = fx3_balls()
    left, right, top, bottom = [], [], [], []
    for ball, name in balls.items():
        if name in GROUND:
            bottom.append((ball, name))
        elif name in POWER:
            top.append((ball, name))
        elif name.startswith("GPIO") and _gpio_key(name) <= 32:
            right.append((ball, name))
        elif name.startswith(("GPIO", "I2C_GPIO")):
            right.append((ball, name))
        else:
            left.append((ball, name))
    right.sort(key=lambda b: _gpio_key(b[1]))
    left.sort(key=lambda b: b[1])
    top.sort(key=lambda b: (POWER.index(b[1]), b[0]))
    bottom.sort(key=lambda b: (b[1], b[0]))
    pitch = 2.54
    h = max(len(left), len(right)) * pitch + 5.08
    w = max(len(top), len(bottom)) * pitch + 5.08
    w = max(w, 60.96)
    hw_, hh = round(w / 2 / pitch) * pitch, round(h / 2 / pitch) * pitch
    pins = []
    for i, (ball, name) in enumerate(left):
        pins.append(_pin(_ptype(name), -hw_ - 2.54, hh - 2.54 - i * pitch, 0, name, ball))
    for i, (ball, name) in enumerate(right):
        pins.append(_pin(_ptype(name), hw_ + 2.54, hh - 2.54 - i * pitch, 180, name, ball))
    for i, (ball, name) in enumerate(top):
        pins.append(_pin(_ptype(name), -hw_ + 2.54 + i * pitch, hh + 2.54, 270, name, ball))
    for i, (ball, name) in enumerate(bottom):
        pins.append(_pin(_ptype(name), -hw_ + 2.54 + i * pitch, -hh - 2.54, 90, name, ball))
    name = "CYUSB3014-BZXI"
    return ["symbol", Q(name), ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
            ["property", Q("Reference"), Q("U"), ["at", 0, hh + 6.0, 0], ["effects", ["font", ["size", 1.27, 1.27]]]],
            ["property", Q("Value"), Q(name), ["at", 0, -hh - 6.0, 0], ["effects", ["font", ["size", 1.27, 1.27]]]],
            ["property", Q("Footprint"), Q("Package_BGA:TFBGA-121_10x10mm_Layout11x11_P0.8mm"),
             ["at", 0, 0, 0], ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]]],
            ["property", Q("Datasheet"), Q("Infineon 001-79276"), ["at", 0, 0, 0],
             ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]]],
            ["symbol", Q(name + "_0_1"),
             ["rectangle", ["start", -hw_, hh], ["end", hw_, -hh], ["stroke", ["width", 0.254], ["type", "default"]],
              ["fill", ["type", "background"]]]],
            ["symbol", Q(name + "_1_1")] + pins]


# HD3SS3220 (TI SLLSES1E, RNH WQFN-30): pin number -> (name, type, side)
HD3SS3220_PINS = {
    1: ("CC2", "bidirectional", "R"), 2: ("CC1", "bidirectional", "R"),
    3: ("CURRENT_MODE", "input", "L"), 4: ("PORT", "input", "L"), 5: ("VBUS_DET", "input", "L"),
    6: ("TXp", "bidirectional", "L"), 7: ("TXn", "bidirectional", "L"), 8: ("VCC33", "power_in", "T"),
    9: ("RXp", "bidirectional", "L"), 10: ("RXn", "bidirectional", "L"), 11: ("DIR", "open_collector", "L"),
    12: ("ENn_MUX", "input", "L"), 13: ("GND", "power_in", "B"), 14: ("RX1n", "bidirectional", "R"),
    15: ("RX1p", "bidirectional", "R"), 16: ("TX1n", "bidirectional", "R"), 17: ("TX1p", "bidirectional", "R"),
    18: ("RX2n", "bidirectional", "R"), 19: ("RX2p", "bidirectional", "R"), 20: ("TX2n", "bidirectional", "R"),
    21: ("TX2p", "bidirectional", "R"), 22: ("ADDR", "input", "L"), 23: ("INT_N/OUT3", "open_collector", "L"),
    24: ("VCONN_FAULT_N", "open_collector", "L"), 25: ("SDA/OUT1", "bidirectional", "L"),
    26: ("SCL/OUT2", "bidirectional", "L"), 27: ("ID", "open_collector", "L"), 28: ("GND", "power_in", "B"),
    29: ("ENn_CC", "input", "L"), 30: ("VDD5", "power_in", "T"), 31: ("EP", "power_in", "B"),
}


def boxed_symbol(name, pins, footprint, datasheet, ref="U"):
    """Generic box symbol from {number: (name, type, side)}; L/R/T/B sides."""
    sides = {k: sorted([(n, v) for n, v in pins.items() if v[2] == k]) for k in "LRTB"}
    pitch = 2.54
    hh = max(len(sides["L"]), len(sides["R"]), 2) * pitch / 2 + 2.54
    hw_ = max(len(sides["T"]), len(sides["B"]), 4) * pitch / 2 + 7.62
    hh, hw_ = round(hh / pitch) * pitch, round(hw_ / pitch) * pitch
    out = []
    for i, (n, (nm, t, _)) in enumerate(sides["L"]):
        out.append(_pin(t, -hw_ - 2.54, hh - 2.54 - i * pitch, 0, nm, str(n)))
    for i, (n, (nm, t, _)) in enumerate(sides["R"]):
        out.append(_pin(t, hw_ + 2.54, hh - 2.54 - i * pitch, 180, nm, str(n)))
    for i, (n, (nm, t, _)) in enumerate(sides["T"]):
        out.append(_pin(t, -hw_ + 5.08 + i * pitch, hh + 2.54, 270, nm, str(n)))
    for i, (n, (nm, t, _)) in enumerate(sides["B"]):
        out.append(_pin(t, -hw_ + 5.08 + i * pitch, -hh - 2.54, 90, nm, str(n)))
    return ["symbol", Q(name), ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
            ["property", Q("Reference"), Q(ref), ["at", 0, hh + 3.0, 0], ["effects", ["font", ["size", 1.27, 1.27]]]],
            ["property", Q("Value"), Q(name), ["at", 0, -hh - 3.0, 0], ["effects", ["font", ["size", 1.27, 1.27]]]],
            ["property", Q("Footprint"), Q(footprint), ["at", 0, 0, 0],
             ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]]],
            ["property", Q("Datasheet"), Q(datasheet), ["at", 0, 0, 0],
             ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]]],
            ["symbol", Q(name + "_0_1"),
             ["rectangle", ["start", -hw_, hh], ["end", hw_, -hh], ["stroke", ["width", 0.254], ["type", "default"]],
              ["fill", ["type", "background"]]]],
            ["symbol", Q(name + "_1_1")] + out]


def f_connector_footprint():
    """DOSIN DS803FPR0016 right-angle F jack (75 ohm, DC-3 GHz), from the
    maker's recommended layout: centre pin 1.30 mm drill; three 2.70 mm body
    holes. Origin = the single body hole, which is at the FRONT: the mating
    axis points to -X (thread side). The centre pin is 5.6 mm and the two
    side legs 6.8 mm behind it. Body outline from the maker's drawing and
    LCSC's footprint (C2979612): square body x -1.0..+8.0, collar -2.0..-1.0,
    thread to -16.0. (Corrected 2026-11-02: the first version had the axis
    reversed.)"""
    def pad(num, x, y, drill, size):
        return ["pad", Q(num), "thru_hole", "circle", ["at", x, y], ["size", size, size], ["drill", drill],
                ["layers", Q("*.Cu"), Q("*.Mask")], ["uuid", Q(stable_fp_uuid("pad", num, x, y))]]
    def line(x1, y1, x2, y2, layer, w=0.12):
        return ["fp_line", ["start", x1, y1], ["end", x2, y2], ["stroke", ["width", w], ["type", "solid"]],
                ["layer", Q(layer)], ["uuid", Q(stable_fp_uuid(layer, x1, y1, x2, y2))]]
    def rect(x0, y0, x1, y1, layer, w):
        return [line(*a, layer, w) for a in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0))]
    fp = ["footprint", Q("F_Female_DOSIN_DS803FPR0016_Horizontal"), ["version", 20241229],
          ["generator", Q("otr-gen")], ["layer", Q("F.Cu")],
          ["descr", Q("DOSIN DS803FPR0016 F-type jack, right angle, 75 ohm, DC-3 GHz (LCSC C2979612). "
                      "Origin = front body hole, thread towards -X")],
          ["attr", "through_hole"],
          ["property", Q("Reference"), Q("REF**"), ["at", 10.2, 0, 90], ["layer", Q("F.SilkS")],
           ["uuid", Q(stable_fp_uuid("ref"))], ["effects", ["font", ["size", 1, 1], ["thickness", 0.15]]]],
          ["property", Q("Value"), Q("DS803FPR0016"), ["at", 3.5, 8.3, 0], ["layer", Q("F.Fab")],
           ["uuid", Q(stable_fp_uuid("value"))], ["effects", ["font", ["size", 1, 1], ["thickness", 0.15]]]],
          pad("2", 0.0, 0.0, 2.7, 3.6), pad("1", 5.6, 0.0, 1.3, 2.2),
          pad("2", 6.8, -5.65, 2.7, 3.6), pad("2", 6.8, 5.65, 2.7, 3.6)]
    h = 10.75 / 2
    fp += rect(-1.0, -h, 8.0, h, "F.Fab", 0.1)            # body
    fp += rect(-2.0, -5.2, -1.0, 5.2, "F.Fab", 0.1)       # collar
    fp += rect(-16.0, -4.85, -2.0, 4.85, "F.Fab", 0.1)    # thread (outside the bracket)
    fp += rect(-2.5, -7.75, 8.75, 7.75, "F.CrtYd", 0.05)
    # silk: body sides up to the leg pads, rear edge behind them
    fp += [line(8.9, -3.6, 8.9, 3.6, "F.SilkS"), line(-1.0, -h - 0.4, 4.6, -h - 0.4, "F.SilkS"),
           line(-1.0, h + 0.4, 4.6, h + 0.4, "F.SilkS")]
    fp.append(["model", Q("${KIPRJMOD}/../lib/otr.3dshapes/F_Female_DOSIN_DS803FPR0016_simple.wrl"),
               ["offset", ["xyz", 0, 0, 0]], ["scale", ["xyz", 1, 1, 1]], ["rotate", ["xyz", 0, 0, 0]]])
    return fp


USB_C_SS_NAME = "USB_C_Receptacle_SameSky_UJ32-C-H-G-H2-SMT"
USB_C_FACE = 7.75            # mating face, in front of the origin (local +Y)


def usb_c_samesky_footprint():
    """Same Sky UJ32-C-H-G-H2-SMT-TR hybrid USB-C receptacle (USB 3.2,
    LCSC C22359755), drawn from the maker's recommended layout for a 1.6 mm
    board (datasheet 2023-11-13, sheets 2-3; D-73). Row A: 12 SMT pads at
    the rear. Row B: through-hole in two staggered sub-rows, the front one on
    the origin line, the rear one 0.70 mm behind; the THT pads carry paste
    (pin-in-paste reflow). Shell: two plated slots 1.5 mm behind the origin;
    two unplated locating holes on the origin line. Origin = centre of the
    front B sub-row; mating face at +Y 7.75 mm. Top view as in the
    datasheet: A1 on the left (-X)."""
    def uid(*k):
        return ["uuid", Q(stable_fp_uuid("usbc", *k))]
    def line(x1, y1, x2, y2, layer, w=0.1):
        return ["fp_line", ["start", x1, y1], ["end", x2, y2], ["stroke", ["width", w], ["type", "solid"]],
                ["layer", Q(layer)], uid(layer, x1, y1, x2, y2)]
    def rect(x0, y0, x1, y1, layer, w=0.1):
        return [line(*a, layer, w) for a in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0))]
    pads = []
    for i in range(12):                                  # row A, SMT 0.30 x 1.70, rear
        x = round(-2.75 + 0.5 * i, 3)
        pads.append(["pad", Q(f"A{i + 1}"), "smd", "rect", ["at", x, -2.31], ["size", 0.30, 1.70],
                     ["layers", Q("F.Cu"), Q("F.Paste"), Q("F.Mask")], uid("A", i)])
    rows = {0.0: {"B11": -2.4, "B10": -1.6, "B8": -0.8, "B5": 0.8, "B3": 1.6, "B2": 2.4},
            -0.70: {"B12": -3.05, "B9": -1.2, "B7": -0.4, "B6": 0.4, "B4": 1.2, "B1": 3.05}}
    for y, row in rows.items():
        for name, x in row.items():
            pads.append(["pad", Q(name), "thru_hole", "circle", ["at", x, y], ["size", 0.65, 0.65],
                         ["drill", 0.40], ["layers", Q("*.Cu"), Q("*.Mask"), Q("F.Paste")], uid(name)])
    for x in (-4.5, 4.5):                                # shell legs: plated slots
        pads.append(["pad", Q("SH"), "thru_hole", "oval", ["at", x, -1.5], ["size", 1.0, 1.6],
                     ["drill", "oval", 0.5, 1.1], ["layers", Q("*.Cu"), Q("*.Mask")], uid("SH", x)])
    pads.append(["pad", Q(""), "np_thru_hole", "circle", ["at", -3.725, 0.0], ["size", 0.65, 0.65],
                 ["drill", 0.65], ["layers", Q("*.Cu"), Q("*.Mask")], uid("np", -1)])
    pads.append(["pad", Q(""), "np_thru_hole", "oval", ["at", 3.725, 0.0], ["size", 0.95, 0.65],
                 ["drill", "oval", 0.95, 0.65], ["layers", Q("*.Cu"), Q("*.Mask")], uid("np", 1)])
    fp = ["footprint", Q(USB_C_SS_NAME), ["version", 20241229], ["generator", Q("otr-gen")],
          ["layer", Q("F.Cu")],
          ["descr", Q("Same Sky UJ32-C-H-G-H2-SMT-TR USB-C receptacle, USB 3.2, hybrid (row A SMT, row B THT), "
                      "1.6 mm PCB (LCSC C22359755). Origin = front B sub-row, mating face +Y 7.75 mm")],
          ["attr", "smd"],
          ["property", Q("Reference"), Q("REF**"), ["at", 0, -4.3, 0], ["layer", Q("F.SilkS")],
           uid("ref"), ["effects", ["font", ["size", 1, 1], ["thickness", 0.15]]]],
          ["property", Q("Value"), Q("UJ32-C-H-G-H2-SMT-TR"), ["at", 0, 4.0, 0], ["layer", Q("F.Fab")],
           uid("value"), ["effects", ["font", ["size", 0.8, 0.8], ["thickness", 0.12]]]]] + pads
    fp += rect(-4.825, -2.25, 4.825, USB_C_FACE, "F.Fab")
    fp += rect(-5.75, -3.45, 5.75, USB_C_FACE + 0.2, "F.CrtYd", 0.05)
    # maker's keep-out areas beside the body (shell side tabs): no copper on top
    for x0 in (-5.71, 4.70):
        fp += rect(x0, 1.94, x0 + 1.01, 3.23, "Dwgs.User", 0.05)
    fp += [line(-5.2, -3.3, -3.3, -3.3, "F.SilkS", 0.12), line(3.3, -3.3, 5.2, -3.3, "F.SilkS", 0.12)]
    fp.append(["model", Q("${KIPRJMOD}/../lib/otr.3dshapes/" + USB_C_SS_NAME + "_simple.wrl"),
               ["offset", ["xyz", 0, 0, 0]], ["scale", ["xyz", 1, 1, 1]], ["rotate", ["xyz", 0, 0, 0]]])
    return fp


def stable_fp_uuid(*names):
    return str(uuid.uuid5(uuid.UUID("2b7c1f0e-8d4a-4f5e-9a3b-6c1d2e3f4a5b"), "/".join(map(str, names))))


def write_footprint(dirpath, fp):
    os.makedirs(dirpath, exist_ok=True)
    open(os.path.join(dirpath, fp[1] + ".kicad_mod"), "w").write(dump(fp) + "\n")


def write_library(path, symbols):
    lib = ["kicad_symbol_lib", ["version", 20251024], ["generator", Q("otr-gen")],
           ["generator_version", Q("10.0")]] + symbols
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(dump(lib) + "\n")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    write_library(os.path.join(here, "..", "lib", "otr.kicad_sym"), [
        fx3_symbol(),
        boxed_symbol("HD3SS3220", HD3SS3220_PINS,
                     "Package_DFN_QFN:Texas_RNH0030A_WQFN-30-1EP_2.5x4.5mm_P0.4mm_EP1.2x3.2mm",
                     "TI SLLSES1E"),
    ])
    write_footprint(os.path.join(here, "..", "lib", "otr.pretty"), f_connector_footprint())
    write_footprint(os.path.join(here, "..", "lib", "otr.pretty"), usb_c_samesky_footprint())
    import models
    models.write_all(os.path.join(here, "..", "lib", "otr.3dshapes"))
    print("wrote hw/lib/otr.kicad_sym and hw/lib/otr.pretty")
