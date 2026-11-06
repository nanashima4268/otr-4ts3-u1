# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Reference and supply planes (D-71).

Stack (D-75, JLC06161H-7628): F.Cu signals / In1 GND / In2 signals /
In3 supplies / In4 GND / B.Cu signals.

- In1 and In4: solid GND planes under the whole card body, the references
  of the outer layers. In1 is cut out only under the SuperSpeed
  AC-coupling caps (AN70707 sec. 12.1, TI SLLSES1E: the pad capacitance is
  tuned out by removing the plane right below); no In2 track runs there
  either, so those caps see In3, which is GND there.
- In2: inner signal layer (BGA escape, general routing), no pour.
- In3: GND by default. Supply areas (higher priority) cut into it:
    +3V3        FX3/FPGA/control area, kept east of the USB bottom-layer
                lanes so they keep a solid GND reference (D-70)
    +1V2        island under the FX3 ball field (its +1V2 vias point inwards)
    +1V2_FPGA   island under the FPGA body
  The RF, USB, power (switching) areas and the receiver band stay GND.
- Zones are filled by kicad-cli after the rules are written (pcbgen.fill),
  so the fill follows the custom rules (RF keep-away, edge clearance).
- SuperSpeed vias get a GND return via about 1 mm away.
- Exposed pads (GND) get vias inside them; ground pins next to an exposed
  pad that have no room for their own via join it on the top layer.
- Every SMD pad on a plane net gets a via next to it when that via lands
  where its net's plane is; the rest is left to the general routing.
"""
import pcbnew

import layout as L
from route import Space, stable_id

MM = pcbnew.FromMM
VIA_D, VIA_DRILL = 0.45, 0.3
HOLE = (VIA_DRILL / 2, 0.25)    # hole to hole, own net included (JLC 0.25 mm for vias)
CLR = 0.2                 # POWER net class clearance (rules.py)
ZONE_CLR = 0.2
USB_WEST = 82.6           # USB bottom lanes end at x 82.1 (usb.py)
AC_CAPS = ("C56", "C57", "C58", "C59")
NO_VIA_REFS = {"J1", "J3", "U1"}      # edge fingers, USB-C (rows), BGA (fanout.py)


def body():
    """Card body above the shoulder (the planes stay out of the fingers)."""
    return [(L.BRACKET_X, L.TOP_Y), (L.FAR_X, L.TOP_Y), (L.FAR_X, L.SHOULDER_Y),
            (L.TAB_X, L.SHOULDER_Y), (L.TAB_X, L.TAB_Y), (L.BRACKET_X, L.TAB_Y)]


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def regions(fps):
    """In3 supply areas: net -> list of polygons (later ones win)."""
    def centre(ref):
        p = fps[ref].GetPosition()
        return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
    fx, fy = centre("U1")
    gx, gy = centre("U3")
    zf, zg, zc = L.ZONES["fx3"], L.ZONES["fpga"], L.ZONES["control"]
    sh = L.SHOULDER_Y - 0.3
    north = zf[1] - 0.5
    usb_top = 122.6            # USB D+/D- bottom-layer run starts at y 123.6
    return [
        ("+3V3", 1, [(zf[0], north), (zg[2] + 0.25, north), (zg[2] + 0.25, sh), (USB_WEST, sh),
                     (USB_WEST, usb_top), (zf[0], usb_top)]),
        ("+3V3", 1, rect(zc[0] - 0.3, north, L.FAR_X, sh)),
        ("+1V2", 2, rect(fx - 4.1, fy - 4.1, fx + 4.1, fy + 4.1)),   # inner vias at 3.6, outer +3V3 vias at 4.4
        ("+1V2_FPGA", 2, rect(gx - 9.6, gy - 9.6, gx + 9.6, gy + 9.6)),
    ]


def in_body(x, y, r=0.0):
    """(x, y) and the points r around it are on the card body: a via of
    radius VIA_D / 2 with r = VIA_D / 2 + 0.3 keeps the 0.3 mm to the edge."""
    poly = body()
    return all(inside(poly, x + a, y + b) for a, b in ((0, 0), (r, 0), (-r, 0), (0, r), (0, -r)))


def inside(poly, x, y):
    c = False
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            c = not c
    return c


def in2_net(regs, x, y):
    best, pr = "GND", 0
    for net, prio, poly in regs:
        if prio >= pr and inside(poly, x, y):
            best, pr = net, prio
    return best


def zone(board, net, layer, pts, prio=0, rule_area=False, no_tracks=False):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    if rule_area:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowZoneFills(True)
        z.SetDoNotAllowTracks(no_tracks)
        z.SetDoNotAllowVias(False)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
    else:
        z.SetNetCode(board.FindNet(net).GetNetCode())
        z.SetAssignedPriority(prio)
        z.SetLocalClearance(MM(ZONE_CLR))
        z.SetMinThickness(MM(0.1 if net == "+1V2" else 0.2))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(MM(0.3))
        z.SetThermalReliefSpokeWidth(MM(0.3))
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(MM(x), MM(y))
    stable_id(z, "zone", net, layer, prio, rule_area, pts[0])
    board.Add(z)
    return z


def _box(pad):
    bb = pad.GetBoundingBox()
    return tuple(round(pcbnew.ToMM(v), 4) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))


def plane_vias(cu, regs):
    """A via beside each SMD pad of a plane net, where that net's plane is."""
    board = cu.board
    space = Space(board)
    ends = set()
    for t in board.GetTracks():
        for p in (t.GetStart(), t.GetEnd()) if t.GetClass() == "PCB_TRACK" else (t.GetPosition(),):
            ends.add((round(pcbnew.ToMM(p.x), 2), round(pcbnew.ToMM(p.y), 2)))
    made, missed = 0, []
    eps = {}                                   # ref -> exposed pad box (GND)
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        if ref in ("J1", "J3", "U1"):
            continue
        for pad in fp.Pads():
            box = _box(pad)
            if pad.GetNetname() != "GND" or pad.GetDrillSize().x > 0 or not pad.IsOnLayer(pcbnew.F_Cu):
                continue
            w, h = box[2] - box[0], box[3] - box[1]
            fc = (pcbnew.ToMM(fp.GetPosition().x), pcbnew.ToMM(fp.GetPosition().y))
            if w * h < 0.8 or abs((box[0] + box[2]) / 2 - fc[0]) > 0.3 or abs((box[1] + box[3]) / 2 - fc[1]) > 0.3:
                continue
            # exposed pad: vias inside it on a >= 1 mm pitch along its long side
            eps[ref] = box
            long_x = w >= h
            n = max(1, int((max(w, h) - 0.2) / 1.0) + 1)
            own = space.find((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            for i in range(n):
                t = (i + 0.5) / n
                vx = box[0] + t * w if long_x else (box[0] + box[2]) / 2
                vy = (box[1] + box[3]) / 2 if long_x else box[1] + t * h
                vx, vy = round(vx, 3), round(vy, 3)
                if space.via_ok(vx, vy, VIA_D / 2, CLR, "GND", own, HOLE):
                    cu.via("GND", vx, vy, VIA_D, VIA_DRILL)
                    space.add_via(vx, vy, VIA_D / 2, "GND", VIA_DRILL / 2)
                    made += 1
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        if ref in NO_VIA_REFS:
            continue
        fc = (pcbnew.ToMM(fp.GetPosition().x), pcbnew.ToMM(fp.GetPosition().y))
        for pad in fp.Pads():
            net = pad.GetNetname()
            if pad.GetDrillSize().x > 0 or not net:
                continue
            if ref in eps and _box(pad) == eps[ref]:
                continue
            if net != "GND" and net not in {n for n, _, _ in regs}:
                continue
            bb = pad.GetBoundingBox()
            x0, y0, x1, y1 = (pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if any(x0 <= ex <= x1 and y0 <= ey <= y1 for ex, ey in ends):
                continue                       # already routed (USB chain)
            island = net.startswith("+1V2")
            ax, ay = cx - fc[0], cy - fc[1]
            dirs = sorted([(1, 0), (-1, 0), (0, 1), (0, -1)],
                          key=lambda d: (d[0] * ax + d[1] * ay) * (1 if island else -1))
            own = space.find(cx, cy)
            w = min(0.3, 0.8 * min(x1 - x0, y1 - y0))   # narrower than a fine-pitch pad
            done = False
            for extra in (0.0, 0.3, 0.6, 0.9):
                for dx, dy in dirs:
                    half = (x1 - x0) / 2 if dx else (y1 - y0) / 2
                    r = half + VIA_D / 2 + 0.1 + extra
                    vx, vy = round(cx + dx * r, 3), round(cy + dy * r, 3)
                    if net != "GND" and in2_net(regs, vx, vy) != net:
                        continue
                    if not in_body(vx, vy, VIA_D / 2 + 0.3):
                        continue
                    if not space.via_ok(vx, vy, VIA_D / 2, CLR, net, own, HOLE):
                        continue
                    if not space.seg_ok((cx, cy), (vx, vy), w / 2, pcbnew.F_Cu, CLR, net, own):
                        continue
                    cu.track(net, [(cx, cy), (vx, vy)], w, "F")
                    cu.via(net, vx, vy, VIA_D, VIA_DRILL)
                    space.add_via(vx, vy, VIA_D / 2, net, VIA_DRILL / 2)
                    space.add_seg((cx, cy), (vx, vy), w / 2, pcbnew.F_Cu, net)
                    made += 1
                    done = True
                    break
                if done:
                    break
            if not done and net == "GND" and ref in eps:
                # a ground pin next to the exposed pad joins it on the top layer
                e = eps[ref]
                tx, ty = min(max(cx, e[0] + w / 2), e[2] - w / 2), min(max(cy, e[1] + w / 2), e[3] - w / 2)
                if space.seg_ok((cx, cy), (tx, ty), w / 2, pcbnew.F_Cu, CLR, net, own | space.find(tx, ty)):
                    cu.track(net, [(cx, cy), (tx, ty)], w, "F")
                    space.add_seg((cx, cy), (tx, ty), w / 2, pcbnew.F_Cu, net)
                    done = True
            if not done and (net == "GND" or in2_net(regs, cx, cy) == net):
                missed.append(f"{ref}.{pad.GetNumber()}")
    return made, missed


SS_PREFIX = ("FX3_SSTX_", "USB_SSRX_", "MUX_TX", "MUX_RX", "USBC_TX", "USBC_RX", "HDR_SS", "HDR_TX")


def return_vias(cu):
    """A GND via beside each SuperSpeed layer change, so the return current
    changes reference plane next to the signal (AN70707 sec. 12.1: about
    1 mm away). The small vias between the USB-C rows have no room."""
    import math
    board = cu.board
    space = Space(board)
    sig = [(pcbnew.ToMM(v.GetPosition().x), pcbnew.ToMM(v.GetPosition().y), v.GetNetname())
           for v in board.GetTracks() if v.GetClass() == "PCB_VIA" and v.GetNetname().startswith(SS_PREFIX)
           and pcbnew.ToMM(v.GetDrill()) >= 0.2]
    made, missed = 0, []
    for x, y, net in sorted(sig):
        if any(math.hypot(x - gx, y - gy) < 1.4 for gx, gy, gn in
               [(i[2][0], i[2][1], i[3]) for i in space.items if i[0] == "c" and i[3] == "GND"]):
            continue                       # a ground via already near (shared by the pair)
        for r in (1.0, 1.2, 1.4, 1.7, 2.0):     # as near as there is room
            ok = False
            for k in range(16):
                a = 2 * math.pi * k / 16
                gx, gy = round(x + r * math.cos(a), 3), round(y + r * math.sin(a), 3)
                if in_body(gx, gy, VIA_D / 2 + 0.3) and space.via_ok(gx, gy, VIA_D / 2, CLR, "GND", hole=HOLE):
                    cu.via("GND", gx, gy, VIA_D, VIA_DRILL)
                    space.add_via(gx, gy, VIA_D / 2, "GND", VIA_DRILL / 2)
                    made += 1
                    ok = True
                    break
            if ok:
                break
        else:
            missed.append(net)
    return made, missed


def plane_at(fps):
    """plane_at(net, x, y): the net's plane is at (x, y) once poured (GND:
    In1 / In4 over the whole card body; the supplies: their In3 areas)."""
    regs = regions(fps)
    outline = body()

    def at(net, x, y):
        if not inside(outline, x, y):
            return False
        return net == "GND" or in2_net(regs, x, y) == net
    return at


def build(cu):
    board, fps = cu.board, cu.fps
    regs = regions(fps)
    zone(board, "GND", pcbnew.In1_Cu, body())
    zone(board, "GND", pcbnew.In3_Cu, body())
    zone(board, "GND", pcbnew.In4_Cu, body())
    for net, prio, poly in regs:
        zone(board, net, pcbnew.In3_Cu, poly, prio)
    for ref in AC_CAPS:
        fp = fps[ref]
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            x0, y0, x1, y1 = (pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))
            zone(board, None, pcbnew.In1_Cu, rect(x0 - 0.1, y0 - 0.1, x1 + 0.1, y1 + 0.1), rule_area=True)
            zone(board, None, pcbnew.In2_Cu, rect(x0 - 0.1, y0 - 0.1, x1 + 0.1, y1 + 0.1), rule_area=True,
                 no_tracks=True)
    rv, rv_missed = return_vias(cu)
    made, missed = plane_vias(cu, regs)
    return made + rv, missed + [f"return via {n}" for n in rv_missed]
