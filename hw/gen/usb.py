# SPDX-License-Identifier: CERN-OHL-S-2.0
"""USB-C -> HD3SS3220 -> FX3: hand placement and the critical routes (D-70).

Guidelines followed (TI SLLSES1E section 9, Cypress FX3 practice):
- 90 ohm pairs (rules.py), top layer over the L2 ground where possible,
  few vias, pairs kept together, 0402 parts in line, no test points.
- Connector row B (under the receptacle body, staggered behind row A) is
  reached through vias just in front of the row: there is no room between
  the rows (0.61 mm) for a via, and a trace cannot pass between the 0.5 mm
  pitch row-A pads. In2 is ground under this area (zones), so bottom-layer
  pairs keep a solid reference.
- Lane order: TX1 and RX2 stay on top; RX1 and TX2 run on the bottom and
  come up next to the switch. On the host side TX stays on top and RX
  crosses under it on the bottom.
- TX1 is wired with + and - swapped at the receptacle (schematic): USB 3
  receivers must detect and correct lane polarity inversion, and this
  avoids a crossing. D+/D- (USB 2.0) are never swapped.
- The header-path 0 ohm links (DNP) share the FX3-side pad of the fitted
  link, turned 90 deg, so the unfitted option leaves no stub.
- D+/D- leave the receptacle towards the bracket, run up beside it on the
  bottom and then along y = 126.5 to the FX3: the only way past both
  bottom-layer lanes without crossing them.
"""
import pcbnew

from route import P

W_SS = 0.263          # 90 ohm pair (D-69)
W_NECK = 0.2          # at 0.4/0.5 mm pitch pins
W_LS = 0.2

# placements: ref -> (x, y, rot)
U8 = (71.0, 133.0, 180)
PLACE = {
    "U8": U8,
    # TX1 coupling caps (switch side = pad 1 to the right)
    "C57": (66.0, 130.3, 180), "C56": (66.0, 131.3, 180),
    # TX2 coupling caps upright below the switch's connector-side pins (pad 1 up)
    "C59": (67.4, 134.6, 270), "C58": (68.4, 134.6, 270),
    # host side: TX links (FX3 side = pad 1 to the right), RX links upright (pad 1 up)
    "R32": (75.2, 132.2, 180), "R30": (75.2, 133.2, 180),
    "R36": (73.4, 129.9, 270), "R34": (74.4, 129.9, 270),
    # D+/D- links next to the FX3
    "R40": (79.9, 123.6, 180), "R38": (79.9, 124.6, 180),
    # switch support parts
    "C55": (71.2, 128.0, 0), "R43": (71.2, 126.9, 0), "C54": (72.6, 136.7, 0), "R42": (75.0, 135.3, 0),
}
# areas the automatic placement must leave free for these routes: (x0, y0, x1, y1)
KEEP = [(56.5, 125.8, 83.6, 137.4), (76.0, 122.4, 81.0, 125.8)]
# header-option links sharing the FX3-side pad (pad 1) of the fitted link: (partner, direction)
SHARED = {"R33": ("R32", "up"), "R31": ("R30", "down"), "R37": ("R36", "left"), "R35": ("R34", "right"),
          "R41": ("R40", "up"), "R39": ("R38", "down")}


def pad_pos(fp, num):
    for p in fp.Pads():
        if p.GetNumber() == num:
            q = p.GetPosition()
            return pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
    raise KeyError(num)


def place(fps):
    """Fixed placement of the USB chain; returns the placed refs."""
    for ref, (x, y, rot) in PLACE.items():
        fps[ref].SetOrientationDegrees(rot)
        fps[ref].SetPosition(P(x, y))
    step = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
    for ref, (partner, d) in SHARED.items():
        tx, ty = pad_pos(fps[partner], "1")
        fp = fps[ref]
        for rot in (0, 90, 180, 270):
            fp.SetOrientationDegrees(rot)
            fp.SetPosition(P(0, 0))
            p1, p2 = pad_pos(fp, "1"), pad_pos(fp, "2")
            if round(p2[0] - p1[0]) == step[d][0] and round(p2[1] - p1[1]) == step[d][1]:
                fp.SetPosition(P(tx - p1[0], ty - p1[1]))
                break
    return list(PLACE) + list(SHARED)


def route(cu):
    J = "J3"
    v = cu.via
    small = dict(d=0.3, drill=0.15)          # between the receptacle rows (paid option, D-70)
    # ---- receptacle row B: small vias in the 0.6 mm gap between the rows
    XG = 61.245
    for pin in ("B11", "B10", "B9", "B7", "B6", "B5", "B4", "B3", "B2"):
        net = cu.pad_net(J, pin)
        x, y = XG, cu.pad(J, pin)[1]
        cu.track(net, [(J, pin), (x, y)], W_NECK)
        v(net, x, y, **small)

    # ---- TX1 (top): J3 A2/A3 -> C57/C56 -> U8 16/17
    cu.track("USBC_TX1_N", [(J, "A2"), (62.8, 130.5), (63.0, 130.3), ("C57", "2")], W_SS)
    cu.track("USBC_TX1_P", [(J, "A3"), (62.9, 131.0), (63.2, 131.3), ("C56", "2")], W_SS)
    cu.track("MUX_TX1_N", [("C57", "1"), (67.6, 130.3), (68.5, 131.2), ("U8", "16")], W_NECK)
    cu.track("MUX_TX1_P", [("C56", "1"), (67.6, 131.3), (67.9, 131.6), ("U8", "17")], W_NECK)

    # ---- RX2 (top): J3 A10/A11 -> U8 18/19, rising over the bottom-layer TX2
    cu.track("USBC_RX2_N", [(J, "A10"), (63.4, 135.0), (66.2, 132.2), (66.6, 132.0)], W_SS)
    cu.track("USBC_RX2_N", [(66.6, 132.0), ("U8", "18")], W_NECK)
    cu.track("USBC_RX2_P", [(J, "A11"), (63.6, 135.5), (66.5, 132.6), (66.9, 132.4)], W_SS)
    cu.track("USBC_RX2_P", [(66.9, 132.4), ("U8", "19")], W_NECK)

    # ---- TX2 (bottom): gap vias -> east along y 136.0/136.41 -> up to vias under C59/C58
    cu.track("USBC_TX2_N", [(XG, 134.75), (62.6, 134.75), (63.85, 136.0), (67.4, 136.0), (67.4, 135.65)], W_SS, "B")
    cu.track("USBC_TX2_P", [(XG, 135.25), (62.4, 135.25), (63.6, 136.45), (68.4, 136.45), (68.4, 135.65)], W_SS, "B")
    v("USBC_TX2_N", 67.4, 135.65)
    v("USBC_TX2_P", 68.4, 135.65)
    cu.track("USBC_TX2_N", [(67.4, 135.65), ("C59", "2")], W_SS)
    cu.track("USBC_TX2_P", [(68.4, 135.65), ("C58", "2")], W_SS)
    cu.track("MUX_TX2_N", [("C59", "1"), (67.4, 132.8), ("U8", "20")], W_NECK)
    cu.track("MUX_TX2_P", [("C58", "1"), (68.4, 133.2), ("U8", "21")], W_NECK)

    # ---- RX1 (bottom): N detours forward so that it runs north of P; small vias at the switch
    cu.track("USBC_RX1_N", [(XG, 131.25), (60.6, 131.25), (60.6, 130.0), (70.6, 130.0), (70.6, 129.4)], W_SS, "B")
    # RX1+ is ~4.4 mm shorter (RX1- detours forward to run north of it): four
    # 0.55 mm bumps right after the detour, i.e. next to where the mismatch arises
    bumps, x = [], 62.4
    for _ in range(4):
        bumps += [(x, 130.45), (x, 131.0), (x + 0.6, 131.0), (x + 0.6, 130.45)]
        x += 1.4
    cu.track("USBC_RX1_P", [(XG, 130.75), (61.2, 130.45)] + bumps + [(69.6, 130.45), (69.6, 130.55)], W_SS, "B")
    v("USBC_RX1_N", 70.6, 129.4, **small)
    v("USBC_RX1_P", 69.6, 130.55, **small)
    cu.track("USBC_RX1_N", [(70.6, 129.4), ("U8", "14")], W_NECK)
    cu.track("USBC_RX1_P", [(69.6, 130.55), (70.0, 130.55), (70.2, 130.75), ("U8", "15")], W_NECK)

    # ---- host TX (top): U8 7/6 -> R32/R30 -> FX3 A6/A5
    cu.track("MUX_TX_N", [("U8", "7"), (74.3, 132.4), (74.5, 132.2), ("R32", "2")], W_NECK)
    cu.track("MUX_TX_P", [("U8", "6"), (73.6, 132.8), (74.0, 133.2), ("R30", "2")], W_NECK)
    cu.track("FX3_SSTX_N", [("R32", "1"), (76.316, 132.2), (81.516, 127.0), ("U1", "A6")], W_SS)
    cu.track("FX3_SSTX_P", [("R30", "1"), (75.9, 133.2), (81.3, 127.8), ("U1", "A5")], W_SS)

    # ---- host RX: U8 10/9 -> R36/R34 (upright) -> vias -> bottom -> vias -> FX3 A3/A4
    cu.track("MUX_RX_N", [("U8", "10"), (72.9, 131.2), (73.4, 130.7), ("R36", "2")], W_NECK)
    cu.track("MUX_RX_P", [("U8", "9"), (73.9, 131.6), (74.4, 131.1), ("R34", "2")], W_NECK)
    v("USB_SSRX_N", 73.4, 128.65)
    v("USB_SSRX_P", 74.4, 128.0)
    cu.track("USB_SSRX_N", [("R36", "1"), (73.4, 128.65)], W_SS)
    cu.track("USB_SSRX_P", [("R34", "1"), (74.4, 128.0)], W_SS)
    v("USB_SSRX_P", 82.1, 128.6)
    v("USB_SSRX_N", 82.1, 129.4)
    cu.track("USB_SSRX_P", [(74.4, 128.0), (81.5, 128.0), (82.1, 128.6)], W_SS, "B")
    cu.track("USB_SSRX_N", [(73.4, 128.65), (73.45, 128.6), (81.3, 128.6), (82.1, 129.4)], W_SS, "B")
    cu.track("USB_SSRX_P", [(82.1, 128.6), ("U1", "A4")], W_SS)
    cu.track("USB_SSRX_N", [(82.1, 129.4), ("U1", "A3")], W_SS)

    # ---- D+/D-: rows tied on the bottom (DP) and on In2 (DM), pair runs forward under the
    # receptacle, up beside the bracket (DP west), along y 126.5/126.9 (DP north), and
    # crosses over at the FX3 end (DP comes up first and runs on top over DM)
    v("USBC_DP", 63.0, 132.5)
    v("USBC_DM", 63.0, 133.5)
    cu.track("USBC_DP", [(J, "A6"), (63.0, 132.5)], W_NECK)
    cu.track("USBC_DM", [(J, "A7"), (63.0, 133.5)], W_NECK)
    cu.track("USBC_DP", [(63.0, 132.5), (62.25, 133.25), (XG, 133.25)], W_LS, "B")
    cu.track("USBC_DM", [(63.0, 133.5), (62.3, 132.8), (XG, 132.75)], W_LS, "In2")
    # (the receptacle's front shield slots reach x 57.42: the pair runs at 57.85/58.3)
    cu.track("USBC_DP", [(XG, 133.25), (57.85, 133.25), (57.85, 127.3), (58.7, 126.45),
                         (77.7, 126.45), (77.7, 124.6)], W_SS, "B")
    cu.track("USBC_DM", [(XG, 132.75), (58.3, 132.75), (58.3, 127.5), (58.9, 126.9),
                         (78.4, 126.9), (78.4, 123.6)], W_SS, "B")
    v("USBC_DP", 77.7, 124.6)
    v("USBC_DM", 78.4, 123.6)
    cu.track("USBC_DP", [(77.7, 124.6), ("R38", "2")], W_NECK)
    cu.track("USBC_DM", [(78.4, 123.6), ("R40", "2")], W_NECK)
    cu.track("USB_DP", [("R38", "1"), ("U1", "A9")], W_SS)
    cu.track("USB_DM", [("R40", "1"), ("U1", "A10")], W_SS)
