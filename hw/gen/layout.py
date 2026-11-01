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

# F jack: the body front (14.0 mm ahead of the rear hole) meets the bracket's
# inner face, 1.03 mm outside the card edge -> rear hole 13.0 mm inside the edge.
# To be checked against the real part and bracket at the placement checkpoint.
F_REAR_INSET = 13.0
CONN_Y = {"J6": 102.0, "J5": 118.0, "J3": 133.0}      # ANT-S, ANT-T, USB-C centres

# Placement of the large parts: ref -> (x, y, rotation deg, side)
FIXED = {
    "J1": (PCIE_X, PCIE_Y, 0, "F"),
    "J6": (BRACKET_X + F_REAR_INSET, CONN_Y["J6"], 180, "F"),
    "J5": (BRACKET_X + F_REAR_INSET, CONN_Y["J5"], 180, "F"),
    "J3": (BRACKET_X, CONN_Y["J3"], 270, "F"),          # footprint's PCB-edge line on the card edge
    "U1": (87.0, 127.0, 0, "F"),                        # FX3
    "U3": (113.0, 126.5, 0, "F"),                       # FPGA
    "J2": (164.5, 115.5, 0, "F"),                       # DC 12 V in (box use)
    "J4": (169.5, 121.0, 0, "F"),                       # USB3 header (DNP), pins run downwards
    "H1": HOLES[0] + (0, "F"),
    "H2": HOLES[1] + (0, "F"),
}

# Where the remaining parts of each group are packed: (x0, y0, x1, y1)
ZONES = {
    "rf_S": (70.5, 91.5, 83.5, 110.0),
    "rf_T": (70.5, 110.5, 83.5, 124.5),
    "usb": (64.0, 125.0, 77.0, SHOULDER_Y - 0.3),
    "fx3": (77.5, 113.0, 98.0, SHOULDER_Y - 0.3),
    "fpga": (98.5, 112.5, 129.5, SHOULDER_Y - 0.3),
    "power": (130.0, 112.5, 152.0, SHOULDER_Y - 0.3),
    "control": (152.5, 112.5, 165.5, 127.0),
}

# Receiver channels (tuner CXD2858ER + demodulator CXD2856ER), drawn as
# reserved areas until the reference-board measurement (receiver sheet).
RX_BAND = (84.0, TOP_Y + 0.5, FAR_X - 0.5, 112.0)
RX_COUNT = 4

# B-CAS full-size card slot (DNP, D-63) on the solder side, card inserted from the far end
BCAS_CARD = (85.6, 54.0)
