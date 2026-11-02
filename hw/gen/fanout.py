# SPDX-License-Identifier: CERN-OHL-S-2.0
"""FX3 (U1, 121-ball 0.8 mm BGA) fan-out (D-71).

Dog-bone escape: a free-size through via (0.45/0.3 mm, D-69/D-72) on the
diagonal between four balls, joined to its ball by a short top-layer
neck. Every diagonal point serves one ball at most; the via points away
from the package centre (quadrant pattern), so the channels between the
via rows stay open on the bottom layer.

- Outer-ring signal balls are not given a via: they leave on the top layer.
- The six USB balls (A3-A6, A9, A10) are routed by usb.py and left alone.
- Supply balls get a via even on the outer ring, so they reach the planes
  (planes.py). +1V2 vias point inwards (they stay inside the +1V2 island
  under the package), +3V3 vias on the outer ring point outwards.
- A supply ball with no free diagonal joins a neighbouring ball of the same
  net on the top layer.
- No-connect balls get nothing.
- The crystal lines (C6, C7) are drawn first (xtal(), D-71).
"""
from route import Space

U = "U1"
PITCH = 0.8
COLS = "ABCDEFGHJKL"
VIA_D, VIA_DRILL = 0.45, 0.3
NECK = 0.15            # ball pad 0.4 mm; the neck passes 0.27 mm from the neighbours
NECK_PWR = 0.2
CLR = 0.09             # JLC BGA fan-out clearance (rules.py)
USB_BALLS = {"A3", "A4", "A5", "A6", "A9", "A10"}
PLANE_NETS = {"GND", "+3V3", "+1V2"}


def ball_index(name):
    return COLS.index(name[0]), int(name[1:])


def outer(name):
    c, r = ball_index(name)
    return c in (0, len(COLS) - 1) or r in (1, 11)


W_XTAL_IN = 0.1        # in a 0.4 mm channel between balls: 0.15 mm each side
W_XTAL = 0.15
XTAL_BALLS = {"C6", "C7"}


def keepouts(fps):
    """Top-side areas the placer must leave free for xtal() (Y1 is fixed):
    the XTALOUT run between Y1 and the ball field and the XTALIN via."""
    import pcbnew
    def pad(ref, num):
        p = next(p for p in fps[ref].Pads() if p.GetNumber() == num)
        return pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
    p3, p1 = pad("Y1", "3"), pad("Y1", "1")
    c11 = pad("U1", "C11")
    return [(p3[0] - 0.5, p3[1], c11[0], c11[1] - 0.4),
            (p1[0] - 0.6, p1[1] - 1.75, p1[0] + 0.6, p1[1] - 0.6)]


def xtal(cu):
    """Crystal Y1 sits north-west of the package: pad 3 (XTALOUT) south-west,
    pad 1 (XTALIN) north-east. Both lines cannot leave column C on the top
    layer without walling in C8 (R_USB2) and C10, so (D-71):
    - C7 XTALOUT: top layer only, channel west of column C, straight to Y1.3;
    - C6 XTALIN: via on its south-east diagonal, bottom layer along the
      column-C ball line (between the via rows), via north of Y1.1."""
    h = PITCH / 2
    ox, oy = cu.pad("U1", "C7")
    top = cu.pad("U1", "C11")[1] - 0.6          # just outside the ball field
    x_out = ox - h
    p3 = cu.pad("Y1", "3")
    cu.track("FX3_XTALOUT", [("U1", "C7"), (x_out, oy - h), (x_out, top),
                             (p3[0] + 0.3, p3[1] + 1.0), p3], W_XTAL_IN)
    ix, iy = cu.pad("U1", "C6")
    v1 = (ix + h, iy + h)
    cu.track("FX3_XTALIN", [("U1", "C6"), v1], W_XTAL_IN)
    cu.via("FX3_XTALIN", *v1, VIA_D, VIA_DRILL)
    p1 = cu.pad("Y1", "1")
    v2 = (p1[0], p1[1] - 1.2)
    cu.track("FX3_XTALIN", [v1, (ix, iy), (ix, top - 0.2), v2], W_XTAL_IN, "B")
    cu.via("FX3_XTALIN", *v2, VIA_D, VIA_DRILL)
    cu.track("FX3_XTALIN", [v2, p1], W_XTAL)
    return {(round(v1[0], 2), round(v1[1], 2))}


def fanout(cu):
    xtal_vias = xtal(cu)
    board = cu.board
    fp = cu.fps[U]
    import pcbnew
    cx, cy = pcbnew.ToMM(fp.GetPosition().x), pcbnew.ToMM(fp.GetPosition().y)
    balls = []
    for p in fp.Pads():
        net = p.GetNetname()
        name = p.GetNumber()
        if not net or net.startswith("unconnected-") or name in USB_BALLS or name in XTAL_BALLS:
            continue
        if outer(name) and net not in PLANE_NETS:
            continue
        q = p.GetPosition()
        balls.append((name, net, pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)))
    # +1V2 first (their inward diagonals must stay inside the island), then
    # inner balls before outer ones: they have the fewest choices. Balls left
    # without a via are moved to the front and the plan is made again.
    balls.sort(key=lambda b: (b[1] != "+1V2", max(abs(b[2] - cx), abs(b[3] - cy)), b[0]))
    h = PITCH / 2

    def plan(order_balls):
        space = Space(board)
        used, failed, plan_ = set(xtal_vias), [], {}
        for name, net, bx, by in order_balls:
            sx = 1 if bx > cx + 1e-6 else -1 if bx < cx - 1e-6 else 0
            sy = 1 if by > cy + 1e-6 else -1 if by < cy - 1e-6 else 0
            if net == "+1V2":
                sx, sy = -sx, -sy
            order = [(dx, dy) for dx in ((sx,) if sx else (1, -1)) + ((-sx,) if sx else ())
                     for dy in ((sy,) if sy else (1, -1)) + ((-sy,) if sy else ())]
            own = space.find(bx, by)
            neck = NECK_PWR if net in PLANE_NETS else NECK
            for dx, dy in order:
                vx, vy = round(bx + dx * h, 4), round(by + dy * h, 4)
                key = (round(vx, 2), round(vy, 2))
                if key in used or not space.via_ok(vx, vy, VIA_D / 2, CLR, net, own) \
                        or not space.seg_ok((bx, by), (vx, vy), neck / 2, pcbnew.F_Cu, CLR, net, own):
                    continue
                used.add(key)
                space.add_via(vx, vy, VIA_D / 2, net)
                space.add_seg((bx, by), (vx, vy), neck / 2, pcbnew.F_Cu, net)
                plan_[name] = (net, bx, by, vx, vy, neck)
                break
            else:
                failed.append(name)
        return plan_, failed

    order_balls = list(balls)
    for _ in range(4):
        planned, failed = plan(order_balls)
        signals = [n for n in failed if next(b for b in balls if b[0] == n)[1] not in PLANE_NETS]
        if not signals:
            break
        first = [b for b in order_balls if b[0] in signals]
        order_balls = first + [b for b in order_balls if b[0] not in signals]
    made = {}
    for name, (net, bx, by, vx, vy, neck) in planned.items():
        cu.track(net, [(bx, by), (vx, vy)], neck, "F")
        cu.via(net, vx, vy, VIA_D, VIA_DRILL)
        made[name] = (net, vx, vy)
    space = Space(board)
    # a supply ball without room for a via shares a neighbour's via (same net)
    for name in list(failed):
        net, bx, by = next((n, x, y) for (b, n, x, y) in balls if b == name)
        if net not in PLANE_NETS:
            continue
        c, r = ball_index(name)
        for dc, dr in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            if not (0 <= c + dc < len(COLS)):
                continue
            nb = f"{COLS[c + dc]}{r + dr}"
            if made.get(nb, (None,))[0] != net:
                continue
            nx, ny = cu.pad(U, nb)
            if space.seg_ok((bx, by), (nx, ny), NECK_PWR / 2, pcbnew.F_Cu, CLR, net):
                cu.track(net, [(bx, by), (nx, ny)], NECK_PWR, "F")
                space.add_seg((bx, by), (nx, ny), NECK_PWR / 2, pcbnew.F_Cu, net)
                made[name] = (net, None, None)
                failed.remove(name)
                break
    # an outer-ring supply ball still without a via leaves on the top layer
    # like the outer signals (general routing)
    top = [n for n in failed if outer(n)]
    return made, [n for n in failed if n not in top], top
