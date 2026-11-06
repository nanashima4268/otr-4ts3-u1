# SPDX-License-Identifier: CERN-OHL-S-2.0
"""RF front end: hand placement in line with the signal and the 75 ohm routes (D-78).

Each antenna input is one straight chain on the top layer over the In1
ground, from the F jack towards the receiver band (layout.RX_BAND):

  jack - ESD (shunt, pad on the line) - DC block - switch A
       = bypass cap (upper branch) / DC block - LNA - DC block (lower branch) =
  switch B - DC block - 45.3 ohm - star - 4 x 45.3 ohm arms

The SOT-363 switches face each other (A turned 180 deg, its common pin J1
towards the jack; B at 0 deg, J1 towards the star). Their throws then sit
J2 over J3 on A and J3 over J2 on B, so the LNA runs A.J3 -> B.J2 and the
bypass A.J2 -> B.J3 without crossing (design.rf_path). The LNA (DFN-8,
RF in and out on the same side) lies below the line with its pins up; its
input and output DC blocks stand upright between the switch throws and
the pins. The bias choke meets the LNA output line between the LNA and
its DC block, with a short stub. The star is a short bar: two arms up,
two down, so the arms are no more than 0.6 mm off the node.

Ground: the ESD diode and the switch GND pins get a via of their own next
to the pad; the LNA's ground pins are tied straight onto its exposed pad, which has
two vias in the pad (JLC's 6-layer boards come with filled and capped vias,
D-75).

The satellite chain (S) runs straight at the ANT-S jack's height. The
terrestrial chain (T) rises from the ANT-T jack to the same column as S,
5 mm higher than the jack, so that its star sits at the corner of the
receiver band and not among the FX3's parts.

RF_<band><ch> (the arm outputs) are left for the receiver sheet.
"""
import pcbnew

from route import P

W = 0.145            # 75 ohm microstrip over In1 (D-69)
W_GND = 0.3
VIA_D, VIA_DRILL = 0.45, 0.3
X_ESD = 65.95        # ESD pad column: 0.6 mm clear of the jack's courtyard
CHAINS = {           # band: (jack, line height at the switches)
    "S": ("J6", 102.0),
    "T": ("J5", 113.0),
}
PATHS = []           # (net, points, width) filled by place(), drawn by route()
VIAS = []            # (net, x, y)
KEEP = []            # boxes the automatic placement must leave free


def _nets(fp):
    return {p.GetNumber(): p.GetNetname() for p in fp.Pads()}


def _pad(fp, num):
    for p in fp.Pads():
        if p.GetNumber() == num:
            q = p.GetPosition()
            return pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
    raise KeyError(f"{fp.GetReference()}.{num}")


def _find(fps, prefix, want):
    """The one part with that ref prefix whose pads carry the nets in want
    ({pad number or None: net}); None matches any pad."""
    hits = []
    for ref, fp in fps.items():
        if not ref.startswith(prefix) or ref[len(prefix):][:1].isalpha():
            continue
        nets = _nets(fp)
        if all((nets.get(k) == n) if k else (n in nets.values()) for k, n in want):
            hits.append(ref)
    if len(hits) != 1:
        raise KeyError(f"{prefix} {want}: {hits}")
    return hits[0]


def _put(fp, a, b, d, at):
    """Turn a two-ended part so that pad b lies in direction d from pad a,
    and move it so that pad a is at the point `at`."""
    for rot in (0, 90, 180, 270):
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(P(0, 0))
        pa, pb = _pad(fp, a), _pad(fp, b)
        dx, dy = pb[0] - pa[0], pb[1] - pa[1]
        n = (dx * dx + dy * dy) ** 0.5
        if abs(dx / n - d[0]) < 1e-3 and abs(dy / n - d[1]) < 1e-3:
            fp.SetPosition(P(at[0] - pa[0], at[1] - pa[1]))
            return
    raise ValueError(f"{fp.GetReference()}: no rotation puts {b} {d} of {a}")


def _centre(fp, x, y):
    """Move a footprint so that its courtyard centre is at (x, y)."""
    cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    cx, cy_ = pcbnew.ToMM(cy.Centre().x), pcbnew.ToMM(cy.Centre().y)
    q = fp.GetPosition()
    fp.SetPosition(P(pcbnew.ToMM(q.x) + x - cx, pcbnew.ToMM(q.y) + y - cy_))


def _half(fp):
    """Half width and half height of the courtyard as placed."""
    b = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    return pcbnew.ToMM(b.GetWidth()) / 2, pcbnew.ToMM(b.GetHeight()) / 2


def _chain(fps, band, jack, y0):
    p = f"RF{band}_"
    ant = f"ANT_{band}"
    r = {
        "D": _find(fps, "D", [("1", ant)]),
        "CA": _find(fps, "C", [(None, ant), (None, p + "SWA_J1")]),
        "UA": _find(fps, "U", [("5", p + "SWA_J1")]),
        "UB": _find(fps, "U", [("5", p + "SWB_J1")]),
        "CBY": _find(fps, "C", [(None, p + "SWA_J2"), (None, p + "SWB_J3")]),
        "CIN": _find(fps, "C", [(None, p + "SWA_J3"), (None, p + "LNA_IN")]),
        "COUT": _find(fps, "C", [(None, p + "LNA_OUT"), (None, p + "SWB_J2")]),
        "LNA": _find(fps, "U", [("4", p + "LNA_IN")]),
        "L": _find(fps, "L", [(None, p + "LNA_OUT")]),
        "CS": _find(fps, "C", [(None, p + "SWB_J1"), (None, p + "SPLIT_IN")]),
        "RIN": _find(fps, "R", [(None, p + "SPLIT_IN"), (None, p + "STAR")]),
    }
    arms = []
    for ch in range(4):
        arms.append(_find(fps, "R", [(None, p + "STAR"), (None, f"RF_{band}{ch}")]))
    f = {k: fps[v] for k, v in r.items()}
    def pin(fp, net):
        return next(q.GetNumber() for q in fp.Pads() if q.GetNetname() == net)

    xj, yj = _pad(fps[jack], "1")
    xd = X_ESD
    cxa = xd + 4.25                       # switch A centre
    xin, xout = cxa + 2.1, cxa + 3.6      # LNA in / out columns
    cxb = cxa + 5.7                       # switch B centre
    yl = y0 + 4.0                         # LNA pin row
    paths = []

    # ESD diode upright, its line pad on the jack's line, ground below
    _put(f["D"], "1", "2", (0, 1), (xd, yj))
    # switches: A with J1 (pin 5) towards the jack, B with J1 away from it
    f["UA"].SetOrientationDegrees(180)
    f["UA"].SetPosition(P(cxa, y0))
    f["UB"].SetOrientationDegrees(0)
    f["UB"].SetPosition(P(cxb, y0))
    a5, b5 = _pad(f["UA"], "5"), _pad(f["UB"], "5")
    a1, a3 = _pad(f["UA"], "1"), _pad(f["UA"], "3")     # J3 below, J2 above
    b1, b3 = _pad(f["UB"], "1"), _pad(f["UB"], "3")     # J3 above, J2 below
    assert a3[1] < y0 < a1[1] and b1[1] < y0 < b3[1]
    ca_in = pin(f["CA"], ant)
    ca_out = pin(f["CA"], p + "SWA_J1")
    if abs(yj - y0) < 1e-6:
        # straight: jack - ESD - DC block - switch A
        _put(f["CA"], ca_in, ca_out, (1, 0), (xd + 1.22, y0))
        paths.append((ant, [_pad(fps[jack], "1"), (xd, y0), _pad(f["CA"], ca_in)]))
        paths.append((p + "SWA_J1", [_pad(f["CA"], ca_out), a5]))
    else:
        # rise from the jack's height to the switches' line: 45 deg out of the
        # ESD pad, upright DC block on the climb, 45 deg into a straight run
        # of 0.85 mm to switch A's J1, between its control pins
        xv = xd + 1.3
        xa = a5[0] - 0.85
        yt = y0 + (xa - xv)
        _put(f["CA"], ca_in, ca_out, (0, -1), (xv, (yj - 0.9 + yt) / 2 + 0.48))
        paths.append((ant, [_pad(fps[jack], "1"), (xd, yj), (xd + 0.4, yj), (xv, yj - 0.9),
                            _pad(f["CA"], ca_in)]))
        paths.append((p + "SWA_J1", [_pad(f["CA"], ca_out), (xv, yt), (xa, y0), a5]))
    # bypass: straight across the top throws
    cby_a = pin(f["CBY"], p + "SWA_J2")
    cby_b = pin(f["CBY"], p + "SWB_J3")
    _put(f["CBY"], cby_a, cby_b, (1, 0), ((cxa + cxb) / 2 - 0.48, a3[1]))
    paths.append((p + "SWA_J2", [a3, _pad(f["CBY"], cby_a)]))
    paths.append((p + "SWB_J3", [_pad(f["CBY"], cby_b), b1]))
    # LNA branch: down 45 deg from the lower throws through upright DC blocks
    cin_a, cin_l = pin(f["CIN"], p + "SWA_J3"), pin(f["CIN"], p + "LNA_IN")
    cout_l, cout_b = pin(f["COUT"], p + "LNA_OUT"), pin(f["COUT"], p + "SWB_J2")
    _put(f["CIN"], cin_a, cin_l, (0, 1), (xin, y0 + 1.52))
    _put(f["COUT"], cout_b, cout_l, (0, 1), (xout, y0 + 1.52))
    # LNA with its pins up: in (4) left, out (1) right
    lna = f["LNA"]
    for rot in (0, 90, 180, 270):
        lna.SetOrientationDegrees(rot)
        lna.SetPosition(P(0, 0))
        p1, p4 = _pad(lna, "1"), _pad(lna, "4")
        if abs(p1[1] - p4[1]) < 1e-3 and p1[0] > p4[0] and p1[1] < 0:
            break
    p4 = _pad(lna, "4")
    lna.SetPosition(P(xin - p4[0], yl - p4[1]))
    assert abs(_pad(lna, "1")[0] - xout) < 1e-3
    paths.append((p + "SWA_J3", [a1, (xin - 0.65, a1[1]), (xin, a1[1] + 0.65), _pad(f["CIN"], cin_a)]))
    paths.append((p + "LNA_IN", [_pad(f["CIN"], cin_l), _pad(lna, "4")]))
    paths.append((p + "LNA_OUT", [_pad(lna, "1"), _pad(f["COUT"], cout_l)]))
    paths.append((p + "SWB_J2", [_pad(f["COUT"], cout_b), (xout, b3[1] + 0.65), (xout + 0.65, b3[1]), b3]))
    # bias choke: right of the LNA's courtyard, a short stub to the out line
    lc = f["L"]
    l_out, l_ch = pin(lc, p + "LNA_OUT"), pin(lc, p + "CHOKE")
    _put(lc, l_out, l_ch, (1, 0), (0, 0))
    hw, _ = _half(lc)
    ly = y0 + 3.2
    _centre(lc, cxa + 4.2 + hw + 0.05, ly)
    lo = _pad(lc, l_out)
    paths.append((p + "LNA_OUT", [(xout, ly), (lo[0], ly)]))
    # after switch B: DC block, 45.3 ohm, star bar, arms
    cs_b, cs_s = pin(f["CS"], p + "SWB_J1"), pin(f["CS"], p + "SPLIT_IN")
    _put(f["CS"], cs_b, cs_s, (1, 0), (0, 0))
    _centre(f["CS"], cxb + 2.5, y0)
    ri_a, ri_s = pin(f["RIN"], p + "SPLIT_IN"), pin(f["RIN"], p + "STAR")
    _put(f["RIN"], ri_a, ri_s, (1, 0), (0, 0))
    _centre(f["RIN"], cxb + 4.48, y0)
    paths.append((p + "SWB_J1", [b5, _pad(f["CS"], cs_b)]))
    paths.append((p + "SPLIT_IN", [_pad(f["CS"], cs_s), _pad(f["RIN"], ri_a)]))
    xs = cxb + 6.05
    bar = [_pad(f["RIN"], ri_s), (xs, y0), (xs + 1.15, y0)]
    paths.append((p + "STAR", bar))
    for i, ref in enumerate(arms):
        fp = fps[ref]
        s_pad = pin(fp, p + "STAR")
        o_pad = pin(fp, f"RF_{band}{i}")
        x = xs + 1.15 * (i % 2)
        up = i < 2
        sy = y0 - 0.55 if up else y0 + 0.55
        _put(fp, s_pad, o_pad, (0, -1) if up else (0, 1), (x, sy))
        paths.append((p + "STAR", [(x, y0), (x, sy)]))
    # ground vias
    vias = []
    dg = _pad(f["D"], "2")
    vias.append(("GND", dg, (dg[0], dg[1] + 0.8)))
    ga, gb = _pad(f["UA"], "2"), _pad(f["UB"], "2")
    vias.append(("GND", ga, (cxa + 1.7, y0)))
    vias.append(("GND", gb, (cxb - 1.7, y0)))
    ep = _pad(lna, "9")
    q = lna.GetOrientationDegrees() % 180
    for s in (-0.4, 0.4):
        v = (ep[0] + s, ep[1]) if q == 90 else (ep[0], ep[1] + s)
        vias.append(("GND", None, v))
    gnd_pins = [n for n, net in _nets(lna).items() if net == "GND" and n != "9"]
    refs = list(r.values()) + arms
    return refs, paths, vias, [(lna, n) for n in gnd_pins]


def place(fps):
    """Places both chains; returns the placed refs."""
    PATHS.clear()
    VIAS.clear()
    KEEP.clear()
    refs = []
    for band, (jack, y0) in CHAINS.items():
        rr, paths, vias, ties = _chain(fps, band, jack, y0)
        refs += rr
        PATHS.extend((net, pts, W) for net, pts in paths)
        for net, pad, v in vias:
            if pad is not None:
                PATHS.append((net, [pad, v], W_GND))
            VIAS.append((net,) + v)
        for fp, n in ties:          # straight across the gap onto the exposed pad
            px, py = _pad(fp, n)
            ex, ey = _pad(fp, "9")
            PATHS.append(("GND", [(px, py), (px, ey)], 0.25))
        for net, pts in paths:
            for a, b in zip(pts, pts[1:]):
                KEEP.append((min(a[0], b[0]) - 0.35, min(a[1], b[1]) - 0.35,
                             max(a[0], b[0]) + 0.35, max(a[1], b[1]) + 0.35))
    return refs


def route(cu):
    for net, pts, w in PATHS:
        cu.track(net, [(round(x, 4), round(y, 4)) for x, y in pts], w)
    for net, x, y in VIAS:
        cu.via(net, round(x, 4), round(y, 4), VIA_D, VIA_DRILL)
