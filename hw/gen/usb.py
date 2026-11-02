# SPDX-License-Identifier: CERN-OHL-S-2.0
"""USB-C -> HD3SS3220 -> FX3: hand placement and the critical routes (D-70, D-73).

Guidelines followed (TI SLLSES1E section 9, Cypress AN70707 section 12.1):
- 90 ohm pairs (rules.py), top layer over the In1 ground where possible,
  few vias, pairs kept together, 0402 parts in line, no test points.
- The receptacle is a hybrid part (Same Sky UJ32-C-H-G-H2-SMT, D-73): row A
  is SMT at the rear, row B is through-hole in two staggered sub-rows in
  front of it. Row A pairs (TX1, RX2) leave on the top layer; row B pairs
  (RX1, TX2) leave on the bottom layer straight from their holes, through
  the gaps of the rear sub-row, and come up through free-size vias next to
  the switch. In2 is ground under this area (planes.py).
- TX1 and TX2 are wired with + and - swapped at the receptacle (schematic):
  USB 3 receivers must detect and correct lane polarity inversion, and this
  avoids crossings. D+/D- (USB 2.0) are never swapped.
- The header-path 0 ohm links (DNP) share the FX3-side pad of the fitted
  link, turned 90 deg, so the unfitted option leaves no stub.
- D+/D-: A6-B6 joined on top, A7-B7 on the bottom (a via east of A7). The
  pair leaves on the bottom through the B8|B5 gap, runs forward, up beside
  the bracket and along y = 126.5 to the FX3: the only way past both
  bottom-layer lanes without crossing them.
- Intra-pair skew is kept to a few tenths of a mm with bumps on the short
  line (route() returns the SuperSpeed lengths).
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


def seglen(pts):
    return sum(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(pts, pts[1:]))


def bumps(x0, y, n, h, step=1.2, w=0.6, side=-1):
    """n rectangular bumps of height h along a horizontal run at y, from x0 eastwards."""
    pts, x = [], x0
    for _ in range(n):
        pts += [(x, y), (x, y + side * h), (x + w, y + side * h), (x + w, y)]
        x += step
    return pts


def route(cu):
    J = "J3"
    v = cu.via
    pad = cu.pad
    # The hybrid receptacle (D-73): row A (SMT, rear) leaves on the top layer,
    # row B (through-hole, front sub-row) leaves on the bottom layer through the
    # gaps of the rear sub-row. No small vias.
    ax_e = pad(J, "A1")[0] + 0.85                       # east end of the row-A pads
    xb_f = pad(J, "B11")[0]                             # front sub-row
    xb_r = pad(J, "B12")[0]                             # rear sub-row
    xg = xb_r + 0.45                                    # just past the rear sub-row

    # ---- TX1 (top): A2/A3 -> C57/C56 -> U8 16/17 (A2 = TX1-, swapped, D-70)
    a2, a3 = pad(J, "A2"), pad(J, "A3")
    c57, c56 = pad("C57", "2"), pad("C56", "2")
    cu.track("USBC_TX1_N", [a2, (ax_e + 0.15, a2[1]), (ax_e + 0.15 + (a2[1] - c57[1]), c57[1]), c57], W_SS)
    cu.track("USBC_TX1_P", [a3, (ax_e + 0.3, a3[1]), (c56[0] - 0.2, c56[1]), c56], W_SS)
    cu.track("MUX_TX1_N", [("C57", "1"), (67.6, 130.3), (68.5, 131.2), ("U8", "16")], W_NECK)
    cu.track("MUX_TX1_P", [("C56", "1"), (67.6, 131.3), (67.9, 131.6), ("U8", "17")], W_NECK)

    # ---- RX2 (top): A10/A11 -> 45 deg -> U8 18/19, north of the TX2 caps
    a10, a11 = pad(J, "A10"), pad(J, "A11")
    u18, u19 = pad("U8", "18"), pad("U8", "19")
    xn = ax_e + 0.14                                    # N turns here (clear of A9)
    cn = xn + a10[1]                                    # line y = cn - x
    cp = cn + 0.413 * 2 ** 0.5                          # parallel, 90 ohm spacing
    cu.track("USBC_RX2_N", [a10, (xn, a10[1]), (cn - u18[1], u18[1])], W_SS)
    cu.track("USBC_RX2_N", [(cn - u18[1], u18[1]), ("U8", "18")], W_NECK)
    cu.track("USBC_RX2_P", [a11, (cp - a11[1], a11[1]), (cp - u19[1], u19[1])], W_SS)
    cu.track("USBC_RX2_P", [(cp - u19[1], u19[1]), ("U8", "19")], W_NECK)

    # ---- TX2 (bottom): B2 (TX2-, south) / B3 (TX2+) through the B4|B1 gap, east,
    # up through vias under C59/C58 (south line -> west via: no crossing)
    b2, b3 = pad(J, "B2"), pad(J, "B3")
    yc = (pad(J, "B4")[1] + pad(J, "B1")[1]) / 2
    yn, ys = yc - 0.2065, yc + 0.2065
    vn, vp = (67.4, 135.65), (68.4, 135.65)
    # TX2- (west via) is ~1.2 mm shorter: one bump south, clear of the shell slot
    tx_n = [b2, (xb_f + 0.12, ys)] + bumps(xg + 1.5, ys, 1, 0.6, side=1) + \
           [(vn[0] - (vn[1] - ys), ys), vn]
    tx_p_head = [b3, (xb_f + 0.15, b3[1]), (xb_f + 0.40, yn), (xg + 0.6, yn)]
    tx_p_tail = [(vp[0] - (vp[1] - yn) - 0.0, yn), vp]
    # P is longer (east via): bumps on N would cross P, so P's extra is cut by
    # starting N's descent later; the remaining skew is reported
    tx_p = tx_p_head + tx_p_tail
    cu.track("USBC_TX2_N", tx_n, W_SS, "B")
    cu.track("USBC_TX2_P", tx_p, W_SS, "B")
    v("USBC_TX2_N", *vn)
    v("USBC_TX2_P", *vp)
    cu.track("USBC_TX2_N", [vn, ("C59", "2")], W_SS)
    cu.track("USBC_TX2_P", [vp, ("C58", "2")], W_SS)
    c59, c58 = pad("C59", "1"), pad("C58", "1")
    cu.track("MUX_TX2_N", [c59, (c59[0], 133.6), (c59[0] + 0.8, 132.8), ("U8", "20")], W_NECK)
    cu.track("MUX_TX2_P", [c58, (c58[0], 133.2), ("U8", "21")], W_NECK)

    # ---- RX1 (bottom): B11 (RX1+, north) / B10 (RX1-) through the B12|B9 gap,
    # east, up through vias north of U8 (north line -> west via), necks to 15/14
    b11, b10 = pad(J, "B11"), pad(J, "B10")
    yc = (pad(J, "B12")[1] + pad(J, "B9")[1]) / 2
    yn, ys = yc - 0.2065, yc + 0.2065
    u14, u15 = pad("U8", "14"), pad("U8", "15")
    rp, rn = (69.9, 129.5), (70.75, 129.5)
    rx_n = [b10, (xb_f + 0.15, b10[1]), (xb_f + 0.40, ys), (rn[0] - (ys - rn[1]), ys), rn]
    rx_p0 = [b11, (xb_r, yn)]
    rx_p1 = [(rp[0] - (yn - rp[1]), yn), rp]
    base_p = seglen(rx_p0 + rx_p1) + seglen([rp, u15])
    base_n = seglen(rx_n) + seglen([rn, u14])
    n = 0
    h = 0.45
    while base_p + 2 * h * n < base_n - 0.3 and n < 6:
        n += 1
    rx_p = rx_p0 + bumps(xg + 0.4, yn, n, h, side=-1) + rx_p1
    cu.track("USBC_RX1_N", rx_n, W_SS, "B")
    cu.track("USBC_RX1_P", rx_p, W_SS, "B")
    v("USBC_RX1_N", *rn)
    v("USBC_RX1_P", *rp)
    cu.track("USBC_RX1_N", [rn, ("U8", "14")], W_NECK)
    cu.track("USBC_RX1_P", [rp, ("U8", "15")], W_NECK)

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

    # ---- D+/D-: A6-B6 joined on top, A7-B7 on the bottom (via east of A7);
    # the pair leaves on the bottom through the B8|B5 gap, runs forward (west),
    # up beside the bracket and along y 126.45/126.9 to the FX3 (DP north)
    a6, a7, b6, b7 = pad(J, "A6"), pad(J, "A7"), pad(J, "B6"), pad(J, "B7")
    cu.track("USBC_DP", [a6, (a6[0] - 0.85, a6[1]), b6], W_LS)
    vdm = (ax_e + 0.45, a7[1])
    cu.track("USBC_DM", [a7, vdm], W_LS)
    v("USBC_DM", *vdm)
    cu.track("USBC_DM", [vdm, b7], W_LS, "B")
    yg = (pad(J, "B8")[1] + pad(J, "B5")[1]) / 2
    ym, yp = yg - 0.175, yg + 0.175
    xm, xp = xb_f - 0.85, xb_f - 1.3
    # 0.2 mm through the 0.95 mm gap, 90 ohm width once clear of the receptacle
    cu.track("USBC_DM", [b7, (xb_f + 0.25, ym), (xm, ym), (xm, ym - 0.4)], W_LS, "B")
    cu.track("USBC_DP", [b6, (xb_f + 0.25, yp), (xp, yp)], W_LS, "B")
    cu.track("USBC_DM", [(xm, ym - 0.4), (xm, 127.5), (xm + 0.6, 126.9), (78.4, 126.9), (78.4, 123.6)], W_SS, "B")
    # D- is ~2.4 mm longer (A7 -> via -> B7): two bumps on D+ (north side, clear of the routes)
    cu.track("USBC_DP", [(xp, yp), (xp, 127.3), (xp + 0.85, 126.45)] + bumps(66.0, 126.45, 2, 0.6, step=1.6, w=0.8, side=-1)
             + [(77.7, 126.45), (77.7, 124.6)], W_SS, "B")
    v("USBC_DP", 77.7, 124.6)
    v("USBC_DM", 78.4, 123.6)
    cu.track("USBC_DP", [(77.7, 124.6), ("R38", "2")], W_NECK)
    cu.track("USBC_DM", [(78.4, 123.6), ("R40", "2")], W_NECK)
    cu.track("USB_DP", [("R38", "1"), ("U1", "A9")], W_SS)
    cu.track("USB_DM", [("R40", "1"), ("U1", "A10")], W_SS)
    return {"TX2": (seglen(tx_n), seglen(tx_p)), "RX1": (seglen(rx_n) + seglen([rn, u14]),
                                                         seglen(rx_p) + seglen([rp, u15]))}
