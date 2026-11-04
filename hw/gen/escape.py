# SPDX-License-Identifier: CERN-OHL-S-2.0
"""FX3 BGA escape (D-75).

Freerouting cannot find its way through the 0.8 mm ball field even where
the bottom layer is empty (D-74), so every FX3 signal leaves the package
by script first, as is usual for BGAs: a 0.1 mm track from the ball's
fan-out via (bottom layer or the inner signal layer In2, D-75) or, for the
outer ring, from the ball itself (top layer) to just outside BGA_BOX.
With 0.45 mm vias at 0.8 mm pitch one track fits between two vias, so a
single layer lets only about two rings out; the FX3's signal balls go four
rings deep, which is why the 4-layer board could not take them (D-75). Freerouting continues from the end of
the stub.

Each stub is a shortest path on a 0.05 mm grid (8 directions, small turn
penalty). Its cost is its length plus PULL times the straight distance
from its end to the net's nearest pad on another part, so it leaves
towards its destination. The stubs are planned together by negotiated
congestion (PathFinder): each is routed on its own and may come too close
to others at a price; those that do are routed again with a higher price
and a growing history cost on the contested cells, until none conflict.

Clearances (rules.py, D-74): track 0.1 mm, copper 0.1 mm; a track keeps
0.2 mm from a via hole outside the ball field and 0.17 mm inside it (the
BGA rule), which the copper clearance already covers there.
"""
import heapq
import math

import pcbnew

from fanout import U, PLANE_NETS, USB_BALLS, XTAL_BALLS, outer

W = 0.1
VIA_LAYERS = ("B", "In2")          # a fan-out via leaves on the bottom or the inner signal layer
CLR = 0.1
HOLE_CLR = 0.2
GRID = 0.05
BOX = (81.5, 121.5, 92.5, 132.5)     # autoroute.BGA_BOX: stubs end outside it
EXIT = 0.25                          # how far past BOX a stub ends
MARGIN = 1.0                         # search area: BOX plus this
FIELD = 4.5                          # vias within this of U1's centre are in the ball field
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
TURN = {0: 0.0, 1: 0.05, 2: 0.25}    # cost of a 45 / 90 degree turn (mm); sharper is not allowed
EPS = 0.004
ROUNDS = 40
PRES0, PRES_GROW, HIST = 0.5, 1.4, 0.3
PULL = 0.3                           # weight of the end-to-destination distance


class Grid:
    def __init__(self, board, layer, cx, cy):
        self.layer = layer
        self.x0, self.y0 = BOX[0] - MARGIN, BOX[1] - MARGIN
        self.nx = int(round((BOX[2] - BOX[0] + 2 * MARGIN) / GRID)) + 1
        self.ny = int(round((BOX[3] - BOX[1] + 2 * MARGIN) / GRID)) + 1
        self.cells = {}           # (i, j) -> set of nets whose copper is too close
        self.cx, self.cy = cx, cy
        T = pcbnew.ToMM
        hw = W / 2
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                q = t.GetPosition()
                x, y = T(q.x), T(q.y)
                self.circle(x, y, self.via_reach(x, y, T(t.GetWidth(pcbnew.F_Cu)) / 2, T(t.GetDrill()) / 2),
                            t.GetNetname())
            elif t.GetLayer() == layer:
                s, e = t.GetStart(), t.GetEnd()
                self.seg((T(s.x), T(s.y)), (T(e.x), T(e.y)), T(t.GetWidth()) / 2 + hw + CLR, t.GetNetname())
        for fp in board.GetFootprints():
            for p in fp.Pads():
                drilled = p.GetDrillSize().x > 0
                if not (drilled or p.IsOnLayer(layer)):
                    continue
                q = p.GetPosition()
                x, y = T(q.x), T(q.y)
                if drilled:
                    self.circle(x, y, max(T(p.GetDrillSize().x), T(p.GetDrillSize().y)) / 2 + hw + HOLE_CLR,
                                p.GetNetname())
                if not p.IsOnLayer(layer):
                    continue
                if p.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE:
                    self.circle(x, y, T(p.GetSize(pcbnew.F_Cu).x) / 2 + hw + CLR, p.GetNetname())
                else:
                    bb = p.GetBoundingBox()
                    self.rect(T(bb.GetLeft()), T(bb.GetTop()), T(bb.GetRight()), T(bb.GetBottom()),
                              hw + CLR, p.GetNetname())

    def via_reach(self, x, y, r, drill_r):
        reach = r + W / 2 + CLR
        if max(abs(x - self.cx), abs(y - self.cy)) > FIELD:
            reach = max(reach, drill_r + W / 2 + HOLE_CLR)
        return reach

    def xy(self, i, j):
        return round(self.x0 + i * GRID, 4), round(self.y0 + j * GRID, 4)

    def ij(self, x, y):
        return int(round((x - self.x0) / GRID)), int(round((y - self.y0) / GRID))

    def _mark(self, x0, y0, x1, y1, net, inside):
        i0, j0 = self.ij(x0, y0)
        i1, j1 = self.ij(x1, y1)
        for i in range(max(i0 - 1, 0), min(i1 + 2, self.nx)):
            for j in range(max(j0 - 1, 0), min(j1 + 2, self.ny)):
                if inside(*self.xy(i, j)):
                    self.cells.setdefault((i, j), set()).add(net)

    def circle(self, x, y, reach, net):
        reach += EPS
        self._mark(x - reach, y - reach, x + reach, y + reach, net,
                   lambda px, py: (px - x) ** 2 + (py - y) ** 2 < reach * reach)

    def rect(self, l, t, r, b, reach, net):
        reach += EPS
        def inside(px, py):
            dx, dy = max(l - px, 0, px - r), max(t - py, 0, py - b)
            return dx * dx + dy * dy < reach * reach
        self._mark(l - reach, t - reach, r + reach, b + reach, net, inside)

    def seg(self, a, b, reach, net):
        reach += EPS
        def inside(px, py):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
            return (px - a[0] - u * dx) ** 2 + (py - a[1] - u * dy) ** 2 < reach * reach
        self._mark(min(a[0], b[0]) - reach, min(a[1], b[1]) - reach,
                   max(a[0], b[0]) + reach, max(a[1], b[1]) + reach, net, inside)

    def free(self, i, j, net):
        if not (0 <= i < self.nx and 0 <= j < self.ny):
            return False
        s = self.cells.get((i, j))
        return not s or s <= {net}

    def out(self, i, j):
        x, y = self.xy(i, j)
        return x < BOX[0] - EXIT or x > BOX[2] + EXIT or y < BOX[1] - EXIT or y > BOX[3] + EXIT

    def footprint(self, cells):
        """Cells closer than W + CLR to a stub through the given cells."""
        r = W + CLR + EPS
        k = int(r / GRID) + 1
        disk = [(a, b) for a in range(-k, k + 1) for b in range(-k, k + 1) if (a * GRID) ** 2 + (b * GRID) ** 2 < r * r]
        out = set()
        for i, j in cells:
            for a, b in disk:
                out.add((i + a, j + b))
        return out

    def route(self, net, start, dest, soft=None, hist=None, pres=0.0):
        """Cheapest stub from start (x, y) to outside BOX, as grid cells;
        cost = length + turns + PULL * straight distance from the end to
        dest, plus the congestion terms of negotiated routing: a cell next
        to another stub costs pres per stub, and hist[cell] scales the
        length of a step into a cell that was fought over before."""
        soft = soft or {}
        hist = hist or {}
        si, sj = self.ij(*start)
        if not self.free(si, sj, net):
            return None, None
        best = {}
        heap = []
        def h(i, j):
            # admissible: the stub from here plus the straight run from its
            # end to dest is never shorter than the straight run from here
            x, y = self.xy(i, j)
            return PULL * math.hypot(x - dest[0], y - dest[1])
        for d in range(8):
            heapq.heappush(heap, (h(si, sj), 0.0, si, sj, d, None))
        prev = {}
        while heap:
            f, g, i, j, d, par = heapq.heappop(heap)
            key = (i, j, d)
            if key in prev:
                continue
            prev[key] = par
            if d == -1:     # goal node
                path = []
                k = par
                while k is not None:
                    path.append((k[0], k[1]))
                    k = prev[k]
                return g, list(reversed(path))
            if self.out(i, j):
                x, y = self.xy(i, j)
                gg = g + PULL * math.hypot(x - dest[0], y - dest[1])
                heapq.heappush(heap, (gg, gg, i, j, -1, key))
                continue
            for nd in (d - 2, d - 1, d, d + 1, d + 2):
                nd %= 8
                turn = min((nd - d) % 8, (d - nd) % 8)
                dx, dy = DIRS[nd]
                ni, nj = i + dx, j + dy
                if not self.free(ni, nj, net):
                    continue
                if dx and dy and not (self.free(i + dx, j, net) or self.free(i, j + dy, net)):
                    continue
                if (ni, nj, nd) in prev:
                    continue
                ng = g + GRID * (1.4142 if dx and dy else 1.0) * (1 + hist.get((ni, nj), 0.0)) \
                    + TURN[turn] * (par is not None)
                occ = soft.get((ni, nj))
                if occ:
                    ng += pres * sum(1 for n in occ if n != net)
                if best.get((ni, nj, nd), 1e9) <= ng:
                    continue
                best[(ni, nj, nd)] = ng
                heapq.heappush(heap, (ng + h(ni, nj), ng, ni, nj, nd, key))
        return None, None


def simplify(path):
    """Merge collinear grid steps into straight segments."""
    out = [path[0]]
    for k in range(1, len(path) - 1):
        a, b, c = out[-1], path[k], path[k + 1]
        d1 = (round((b[0] - a[0]) / GRID), round((b[1] - a[1]) / GRID))
        d2 = (round((c[0] - b[0]) / GRID), round((c[1] - b[1]) / GRID))
        g1, g2 = math.gcd(*d1) or 1, math.gcd(*d2) or 1
        if (d1[0] // g1, d1[1] // g1) != (d2[0] // g2, d2[1] // g2):
            out.append(b)
    out.append(path[-1])
    return out


def destination(board, net, x, y):
    best = None
    for fp in board.GetFootprints():
        if fp.GetReference() == U:
            continue
        for p in fp.Pads():
            if p.GetNetname() == net:
                q = p.GetPosition()
                d = (pcbnew.ToMM(q.x), pcbnew.ToMM(q.y))
                if best is None or math.hypot(d[0] - x, d[1] - y) < math.hypot(best[0] - x, best[1] - y):
                    best = d
    return best


def escape(cu, made):
    """made: fanout()'s {ball: (net, via x, via y)}. Returns (stubs, failed)."""
    board = cu.board
    fp = cu.fps[U]
    cx, cy = pcbnew.ToMM(fp.GetPosition().x), pcbnew.ToMM(fp.GetPosition().y)
    jobs = []
    for p in fp.Pads():
        name, net = p.GetNumber(), p.GetNetname()
        if not net or net.startswith("unconnected-") or net in PLANE_NETS or name in USB_BALLS \
                or name in XTAL_BALLS:
            continue
        q = p.GetPosition()
        bx, by = pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
        if outer(name):
            start, layer = (bx, by), ("F",)
        elif name in made and made[name][1] is not None:
            start, layer = (made[name][1], made[name][2]), VIA_LAYERS
        else:
            continue
        dest = destination(board, net, bx, by)
        if dest is None:
            continue
        jobs.append((max(abs(bx - cx), abs(by - cy)), name, net, start, layer, dest))
    jobs.sort(key=lambda j: (-j[0], j[1]))
    order = [j[1] for j in jobs]
    by_name = {j[1]: j for j in jobs}
    LAY = {"F": pcbnew.F_Cu, "In2": pcbnew.In2_Cu, "B": pcbnew.B_Cu}
    grids = {k: Grid(board, v, cx, cy) for k, v in LAY.items()}
    # negotiated congestion (PathFinder): every stub is routed on its own,
    # stubs may overlap at a price; the nets that overlap are routed again
    # with a higher price and a growing history cost on the fought-over
    # cells, until no two stubs come too close
    soft = {k: {} for k in LAY}
    hist = {k: {} for k in LAY}
    cells, foot, chosen, failed = {}, {}, {}, []
    pres = PRES0
    todo = order
    for _ in range(ROUNDS):
        for name in todo:
            _, _, net, start, layers, dest = by_name[name]
            if name in chosen:
                sl = soft[chosen[name]]
                for c in foot.pop(name):
                    sl[c][net] -= 1
                    if not sl[c][net]:
                        del sl[c][net]
            best = None
            for layer in layers:      # a via may leave on any of its layers
                cost, path = grids[layer].route(net, start, dest, soft[layer], hist[layer], pres)
                if path is not None and (best is None or cost < best[0]):
                    best = (cost, layer, path)
            if best is None:
                failed.append(name)
                cells.pop(name, None)
                chosen.pop(name, None)
                continue
            _, layer, path = best
            g, sl = grids[layer], soft[layer]
            chosen[name] = layer
            cells[name] = path
            foot[name] = g.footprint(path)
            for c in foot[name]:
                sl.setdefault(c, {}).setdefault(net, 0)
                sl[c][net] += 1
        todo = []
        for name in order:
            if name not in cells:
                continue
            net, layer = by_name[name][2], chosen[name]
            bad = [c for c in cells[name] if any(n != net for n in soft[layer].get(c, ()))]
            if bad:
                todo.append(name)
                for c in bad:
                    hist[layer][c] = hist[layer].get(c, 0.0) + HIST
        if not todo:
            break
        pres *= PRES_GROW
    failed += todo
    paths = {}
    for name, path in cells.items():
        if name in todo:
            continue
        pts = simplify([grids[chosen[name]].xy(*c) for c in path])
        pts[0] = by_name[name][3]
        paths[name] = (chosen[name], pts)
    for name in sorted(paths):
        layer, pts = paths[name]
        cu.track(by_name[name][2], pts, W, layer)
    return paths, failed
