# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Internal USB3 header option (J4, DNP, D-09/D-56): the three 90 ohm pairs
from the header-side 0 ohm links next to the FX3 to the header (D-79).

The links sit at the USB-C chain (usb.py), the header at the far end of the
card, so the pairs cross the whole board. They run on the bottom layer over
the In4 ground, in a band along the card's lower edge under the FX3 and the
FPGA, where the bottom layer is free:

  top    HDR_DP / HDR_DM      (USB 2.0)
         HDR_SSTX_P / _N      (FX3 RX <- host TX)
  bottom HDR_TX_P / _N        (FX3 TX -> coupling caps -> HDR_SSRX -> host RX)

The order follows from both ends. At the links each pair goes down to the
band at its own column, TX leftmost, then SSTX, then DP/DM (a pair turning
from down to right passes under the ones to its right). At the header the
pins are DP/DM (row 131), SSTX (133/135), SSRX (137) from the top. Short of
the I2C header J7 the pairs rise at 45 degrees to the gaps between the
header's pin rows: DP/DM and SSTX stay on the bottom layer to the
through-hole pins, TX comes up to the top layer for its coupling caps
(C61 N, C60 P, turned so that the FX3 side is on the left) and goes on to
pins 17/18 there.

DP/DM must pass the USB-C SSRX pair (bottom layer, y 128-128.6) and the FX3
SSTX pair (top layer) near the links: they drop to In2 at the link pads and
come to the bottom layer under the FX3 (about 9 mm of In2, where the line
is narrower than 90 ohm would need; USB 2.0 tolerates it). Lane polarity:
the header pins take P and N as the standard has them; no swap is needed.

Intra-pair skew: at the links the N line (D- for DP/DM) starts 3-4 mm
further away, so the short line gets rectangular bumps (as usb.py), sized
from the planned lengths so that the pair matches to a few hundredths of a
mm: DP and SSTX_P in the gap between their pairs in the band (staggered),
TX+SSRX_P (matched through the coupling caps) on the top-layer run towards
J7, where the bottom-layer band is too close to the card edge.
"""
import math

import pcbnew

from route import P

W = 0.263            # 90 ohm pair (D-69), as usb.W_SS
H = (0.263 + 0.15) / 2   # half pitch of the pair
VIA_D, VIA_DRILL = 0.45, 0.3

PATHS = []           # (net, points, width, layer)
VIAS = []            # (net, x, y)
KEEP = []            # top-layer copper and vias: boxes the placement leaves free

# band centres (y) and the columns the pairs come down at (x)
BAND = {"DP": 137.05, "SSTX": 138.4, "TX": 139.75}
DOWN = {"DP": 81.15, "SSTX": 78.4, "TX": 76.8065}
RISE = {"DP": 141.0, "SSTX": 141.5, "TX": 142.0}         # where each pair leaves the band
# centre at the header: the line to the far pin column runs exactly in the
# middle of the 0.65 mm gap between two near-column pins (y 130, 134, 136),
# the other line turns into its near-column pin before
ROW = {"DP": 130.0 + H, "SSTX": 134.0 + H, "TX": 136.0 + H}
X_END = 168.6        # pairs split here into the header pins
CHAMFER = 1.0
# TX coupling caps: via column, cap centre column, caps' rows
X_TXV, X_CAP = 146.8, 148.18
CAP_ROWS = {"C61": 136.0 + H - 0.5, "C60": 136.0 + H + 0.5}


def pair(c, h=H):
    """The two lines of a pair along centreline c: (A, B), A on the side of
    the normal (-dy, dx) (below when running right, left when running
    down), mitred at the bends."""
    def norm(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy)
        return -dy / n, dx / n
    ns = [norm(a, b) for a, b in zip(c, c[1:])]
    A, B = [], []
    for i, p in enumerate(c):
        if i == 0:
            m = ns[0]
        elif i == len(c) - 1:
            m = ns[-1]
        else:
            n1, n2 = ns[i - 1], ns[i]
            k = 1 + n1[0] * n2[0] + n1[1] * n2[1]
            m = ((n1[0] + n2[0]) / k, (n1[1] + n2[1]) / k)
        A.append((p[0] + m[0] * h, p[1] + m[1] * h))
        B.append((p[0] - m[0] * h, p[1] - m[1] * h))
    return A, B


def _pad(fp, num):
    for p in fp.Pads():
        if p.GetNumber() == num:
            q = p.GetPosition()
            return pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
    raise KeyError((fp.GetReference(), num))


def _band(key, start, end=X_END):
    """Centreline from start (on the pair's down column) to x = end on the
    header row: down, a chamfered turn into the band, along it, a 45 degree
    rise."""
    x, y = DOWN[key], BAND[key]
    xr, yr = RISE[key], ROW[key]
    return [start, (x, y - CHAMFER), (x + CHAMFER, y), (xr, y), (xr + (y - yr), yr), (end, yr)]


def _into(e, pin):
    """From the end e of a line down (or up) at 45 degrees onto a pin's row,
    then along it into the pin."""
    return [e, (e[0] + abs(pin[1] - e[1]), pin[1]), pin]


def _over(e, pin):
    """Along the line's row to 45 degrees short of the pin, then into it."""
    return [e, (pin[0] - abs(pin[1] - e[1]), e[1]), pin]


def _add(net, pts, layer, w=W):
    PATHS.append((net, [(round(x, 4), round(y, 4)) for x, y in pts], w, layer))


def _length(nets):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1])
               for net, pts, w, layer in PATHS if net in nets for a, b in zip(pts, pts[1:]))


def _bump(net, layer, x0, skew, h, side, step=1.2, w=0.6):
    """Lengthen net by skew with rectangular bumps of height h (the last one
    lower, for the rest) on its horizontal run through x0 on the layer,
    eastwards from x0, on side (+1 down, -1 up)."""
    n = int(skew / (2 * h))
    hs = [h] * n
    rest = skew - 2 * h * n
    if rest / 2 >= 0.02:
        hs.append(rest / 2)
    if not hs:
        return
    for k, (nt, pts, wd, ly) in enumerate(PATHS):
        if nt != net or ly != layer:
            continue
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            if a[1] == b[1] and a[0] <= x0 and x0 + step * len(hs) <= b[0]:
                y, x, ins = a[1], x0, []
                for hh in hs:
                    yy = round(y + side * hh, 4)
                    ins += [(x, y), (x, yy), (round(x + w, 4), yy), (round(x + w, 4), y)]
                    x = round(x + step, 4)
                PATHS[k] = (nt, pts[:i + 1] + ins + pts[i + 1:], wd, ly)
                return
    raise ValueError(f"{net}: no straight run on {layer} from x = {x0}")


def place(fps):
    """Places the TX coupling caps and plans the routes. Returns the refs placed."""
    PATHS.clear()
    VIAS.clear()
    KEEP.clear()
    for ref, y in CAP_ROWS.items():
        fp = fps[ref]
        fp.SetOrientationDegrees(0)            # pad 1 (HDR_TX) on the left
        fp.SetPosition(P(X_CAP, y))
    pad = lambda ref, n: _pad(fps[ref], n)
    J4 = fps["J4"]

    # --- DP/DM: link pads -> In2 -> bottom layer under the FX3 -> band
    dm, dp = pad("R41", "2"), pad("R39", "2")
    # In2 columns: DM clear of the USB-C SSRX_N via at (82.1, 129.4)
    dm_v1, dp_v1 = (81.5, dm[1]), (80.7, 126.3)
    dm_v2, dp_v2 = (81.5, 131.2), (80.75, 130.9)
    x2 = dm_v1[0] - 2 * H                       # DP's In2 column
    _add("HDR_DM", [dm, dm_v1], "F")
    _add("HDR_DP", [dp, (dp[0], dp_v1[1] - (dp_v1[0] - dp[0])), dp_v1], "F")
    xdp, xdm = DOWN["DP"] - H, DOWN["DP"] + H
    _add("HDR_DM", [dm_v1, dm_v2], "In2")
    _add("HDR_DP", [dp_v1, (x2, dp_v1[1] + (x2 - dp_v1[0])),
                    (x2, dp_v2[1] - (x2 - dp_v2[0])), dp_v2], "In2")
    c = _band("DP", (DOWN["DP"], 131.6))       # ends at X_END on the header row
    a, b = pair(c)                              # A = DP (left, then lower)
    _add("HDR_DP", [dp_v2, (xdp, dp_v2[1] + (xdp - dp_v2[0]))] + a, "B")
    _add("HDR_DM", [dm_v2, (xdm, dm_v2[1] + (dm_v2[0] - xdm))] + b, "B")
    # header: DP into pin 11 (169.5, 131), DM over it into pin 12 (171.5, 131)
    p11, p12 = _pad(J4, "11"), _pad(J4, "12")
    _add("HDR_DP", _into(a[-1], p11), "B")
    _add("HDR_DM", _over(b[-1], p12), "B")

    # --- SSTX: link pads -> bottom layer, right to its column, down to the band
    n, p_ = pad("R37", "2"), pad("R35", "2")
    nv, pv = (71.75, n[1]), (76.1, p_[1])
    _add("HDR_SSTX_N", [n, nv], "F")
    _add("HDR_SSTX_P", [p_, pv], "F")
    sstx_v = (nv, pv)
    yh = 129.86                                  # the run from the links to the column
    x = DOWN["SSTX"]
    c = [(76.4, yh), (x - CHAMFER, yh), (x, yh + CHAMFER)] + _band("SSTX", (x, yh + CHAMFER))[1:]
    # running right first: A (below) = N; turning down it is the left line, then the lower one
    a, b = pair(c)
    _add("HDR_SSTX_N", [nv, (nv[0] + (yh + H - nv[1]), yh + H)] + a, "B")
    _add("HDR_SSTX_P", [pv, (pv[0] + (yh - H - pv[1]), yh - H)] + b, "B")
    p14, p15 = _pad(J4, "14"), _pad(J4, "15")
    _add("HDR_SSTX_N", _into(a[-1], p15), "B")
    _add("HDR_SSTX_P", _over(b[-1], p14), "B")

    # --- TX: link pads -> bottom layer at its column -> band -> rise -> caps on top
    n, p_ = pad("R33", "2"), pad("R31", "2")
    nv, pv = (76.45, 130.9), (76.45, p_[1])
    _add("HDR_TX_N", [n, (n[0] + (n[1] - nv[1]), nv[1]), nv], "F")
    _add("HDR_TX_P", [p_, pv], "F")
    x = DOWN["TX"]
    c = _band("TX", (x, 134.6), X_TXV - 0.6)
    a, b = pair(c)                               # A = P (left, then lower), B = N
    _add("HDR_TX_N", [nv, (x + H, nv[1] + (x + H - nv[0]))] + b, "B")
    _add("HDR_TX_P", [pv, (x - H, pv[1] + (x - H - pv[0]))] + a, "B")
    # fan out to the cap rows, through vias up to the top layer
    for net, line, row in (("HDR_TX_N", b, CAP_ROWS["C61"]), ("HDR_TX_P", a, CAP_ROWS["C60"])):
        e = line[-1]
        d = abs(row - e[1])
        _add(net, [e, (e[0] + d, row), (X_TXV, row)], "B")
        VIAS.append((net, X_TXV, row))
        _add(net, [(X_TXV, row), pad("C61" if net.endswith("N") else "C60", "1")], "F")
    # caps -> header pins 17 (P) and 18 (N) on the top layer
    p17, p18 = _pad(J4, "17"), _pad(J4, "18")
    yn, yp = ROW["TX"] - H, ROW["TX"] + H
    s_n, s_p = pad("C61", "2"), pad("C60", "2")
    _add("HDR_SSRX_N", [s_n, (s_n[0] + 0.34, s_n[1]), (s_n[0] + 0.34 + (yn - s_n[1]), yn)]
         + _over((X_END, yn), p18), "F")
    _add("HDR_SSRX_P", [s_p, (s_p[0] + 0.34, s_p[1]), (s_p[0] + 0.34 + (s_p[1] - yp), yp)]
         + _into((X_END, yp), p17), "F")

    VIAS.extend([("HDR_DM",) + dm_v1, ("HDR_DP",) + dp_v1, ("HDR_DM",) + dm_v2, ("HDR_DP",) + dp_v2,
                 ("HDR_SSTX_N",) + sstx_v[0], ("HDR_SSTX_P",) + sstx_v[1],
                 ("HDR_TX_N",) + nv, ("HDR_TX_P",) + pv])
    # intra-pair skew: bumps on the short line where it has room (D-79)
    for short, long_, layer, x0, side, h, nets in (
            ("HDR_DP", "HDR_DM", "B", 86.0, 1, 0.4, None),          # down, into the gap to SSTX
            ("HDR_SSTX_P", "HDR_SSTX_N", "B", 100.0, -1, 0.4, None),  # up, into the same gap, further on
            ("HDR_SSRX_P", "HDR_SSRX_N", "F", 151.0, 1, 0.6,         # down towards J7, for TX + SSRX
             (("HDR_TX_P", "HDR_SSRX_P"), ("HDR_TX_N", "HDR_SSRX_N")))):
        a_nets, b_nets = nets or ((short,), (long_,))
        skew = _length(b_nets) - _length(a_nets)
        _bump(short, layer, x0, skew, h, side)
    for net, pts, w, layer in PATHS:
        if layer != "F":
            continue
        for a_, b_ in zip(pts, pts[1:]):
            KEEP.append((min(a_[0], b_[0]) - 0.35, min(a_[1], b_[1]) - 0.35,
                         max(a_[0], b_[0]) + 0.35, max(a_[1], b_[1]) + 0.35))
    for net, x, y in VIAS:
        KEEP.append((x - 0.5, y - 0.5, x + 0.5, y + 0.5))
    return list(CAP_ROWS)


def route(cu):
    """Draws the planned routes. Returns {net: length} for the pairs."""
    lens = {}
    for net, pts, w, layer in PATHS:
        cu.track(net, pts, w, layer)
        lens[net] = lens.get(net, 0.0) + sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    for net, x, y in VIAS:
        cu.via(net, round(x, 4), round(y, 4), VIA_D, VIA_DRILL)
    return lens
