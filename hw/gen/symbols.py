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


def write_library(path, symbols):
    lib = ["kicad_symbol_lib", ["version", 20251024], ["generator", Q("otr-gen")],
           ["generator_version", Q("10.0")]] + symbols
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(dump(lib) + "\n")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    write_library(os.path.join(here, "..", "lib", "otr.kicad_sym"), [fx3_symbol()])
    print("wrote hw/lib/otr.kicad_sym")
