# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Board outline and floorplan for OTR-4TS3-U1 (D-51, D-52).

Coordinates are KiCad board millimetres (y grows downwards). The frame is
tied to the PCIe x1 edge footprint (KiCad Connector_PCBEdge:BUS_PCIexpress_x1):
its origin is pin B1/A1, the finger tips are 3.45 mm below it.

Card outline (PCIe CEM low profile, as drawn in the CEM-derived KiCad
templates of ULX4M-PCIe-IO, CERN-OHL): 68.90 mm from the finger tips to
the top edge, card bottom edge 12.75 mm above the finger tips, card end at
the bracket 45.15 mm from the first finger edge, a tab down to 4.50 mm
above the finger tips for the lower bracket screw. The bracket feet sit on
the solder side; the screws come from the component side.

Component side = F.Cu = PCIe side B. Viewed from it, the bracket is on the
left and the fingers at the bottom. Bracket connectors, from the top (away
from the motherboard): ANT-S, ANT-T, USB-C (D-61).
"""

# PCIe footprint origin (pin B1) on the board
PCIE_X, PCIE_Y = 100.0, 150.0
TIP_Y = PCIE_Y + 3.45                 # finger tips
TOP_Y = TIP_Y - 68.90                 # card top edge (low profile)
SHOULDER_Y = TIP_Y - 12.75            # card bottom edge beside the fingers
BRACKET_X = PCIE_X - 0.5 - 45.15      # card end at the bracket
LENGTH = 120.0                        # D-52 target
FAR_X = BRACKET_X + LENGTH
TAB_X = PCIE_X - 0.5 - 30.15          # lower bracket tab, right side
TAB_Y = TIP_Y - 4.50
FINGER_L, FINGER_R = PCIE_X - 0.65, PCIE_X + 19.65   # footprint's own edge lines
FINGER_TOP_Y = PCIE_Y - 4.95

# bracket screw holes (CEM low-profile bracket feet): 9.35 and 63.25 mm above the tips
HOLE_X = PCIE_X - 0.5 - 37.65
HOLES = [(HOLE_X, TIP_Y - 63.25), (HOLE_X, TIP_Y - 9.35)]
SCREW_HEAD_R = 3.5                    # keep footprints clear of the screw heads (top side)

# F jack (footprint origin = its front body hole, thread towards -x): the hole's
# pad needs ~2 mm to the card edge, so the hole sits 2.2 mm inside it. The
# collar front is then 0.2 mm inside the edge and 1.2 mm short of the
# bracket's inner face (1.03 mm outside the edge); the thread stands about
# 12 mm out of the bracket.
F_FRONT_INSET = 2.2
CONN_Y = {"J6": 102.0, "J5": 118.0, "J3": 133.0}      # ANT-S, ANT-T, USB-C centres

# Placement of the large parts: ref -> (x, y, rotation deg, side)
FIXED = {
    "J1": (PCIE_X, PCIE_Y, 0, "F"),
    "J6": (BRACKET_X + F_FRONT_INSET, CONN_Y["J6"], 0, "F"),
    "J5": (BRACKET_X + F_FRONT_INSET, CONN_Y["J5"], 0, "F"),
    "J3": (BRACKET_X, CONN_Y["J3"], 270, "F"),          # footprint's PCB-edge line on the card edge
    "U1": (87.0, 127.0, 90, "F"),                       # FX3: USB balls to the left, GPIF to the upper right
    "U3": (113.0, 125.5, 0, "F"),                       # FPGA
    "J2": (164.5, 115.5, 0, "F"),                       # DC 12 V in (box use)
    "J4": (169.5, 121.0, 0, "F"),                       # USB3 header (DNP), pins run downwards
    "H1": HOLES[0] + (0, "F"),
    "H2": HOLES[1] + (0, "F"),
}

# Where the remaining parts of each group are packed: (x0, y0, x1, y1)
ZONES = {
    "rf_S": (66.5, 91.5, 83.5, 110.0),
    "rf_T": (66.5, 110.5, 83.5, 124.5),
    "usb": (64.0, 125.0, 77.0, SHOULDER_Y - 0.3),
    "fx3": (77.5, 113.0, 98.0, SHOULDER_Y - 0.3),
    "fpga": (98.5, 112.5, 129.5, SHOULDER_Y - 0.3),
    "power": (130.0, 112.5, 152.0, SHOULDER_Y - 0.3),
    "control": (152.5, 112.5, 165.5, 127.0),
    "usb_hdr": (152.5, 127.5, 168.2, SHOULDER_Y - 0.3),
}

# Receiver channels (tuner CXD2858ER + demodulator CXD2856ER), drawn as
# reserved areas until the reference-board measurement (receiver sheet).
RX_BAND = (84.0, TOP_Y + 0.5, FAR_X - 0.5, 112.0)
RX_COUNT = 4

# B-CAS full-size card slot (DNP, D-63) on the solder side, card inserted from the far end
BCAS_CARD = (85.6, 54.0)

# Parts packed (not attracted): regulators, RF ICs, power magnetics
PACKED_MAJORS = {"U4", "U5", "U6", "U7", "L1", "D3", "D4", "U8", "U9", "U10",
                 "U11", "U12", "U13", "U14", "U15", "U16"}


def TARGET_OVERRIDE(fps):
    """Explicit targets, applied in order before the affinity pass:
    (ref, () -> (x, y, net to put on the point)). X1 (50 MHz) sits between
    the FPGA clock pin; its 33 ohm series resistors go right next to its
    output (source termination, D-60): R17 short to the FPGA, R18 drives the
    line along the FPGA's lower edge to the FX3 PCLK ball."""
    def pad_of(ref, net):
        for p in fps[ref].Pads():
            if p.GetNetname() == net:
                q = p.GetPosition()
                return q.x / 1e6, q.y / 1e6
        raise KeyError((ref, net))
    def x1():
        fx, fy = pad_of("U3", "FPGA_CLK50")
        return fx, fy, "CLK50"
    def near_x1():
        x, y = pad_of("X1", "CLK50")
        return x, y, "CLK50"
    return [("X1", x1), ("R17", near_x1), ("R18", near_x1)]
