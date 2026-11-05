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

from occ import Occ, Snap, GRID, CLR, HOLE_CLR, EPS, FIELD
from fanout import U, PLANE_NETS, USB_BALLS, XTAL_BALLS, outer

W = 0.1
VIA_LAYERS = ("B", "In2")          # a fan-out via leaves on the bottom or the inner signal layer
BOX = (81.5, 121.5, 92.5, 132.5)     # autoroute.BGA_BOX: stubs end outside it
EXIT = 0.25                          # how far past BOX a stub ends
MARGIN = 1.0                         # search area: BOX plus this
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
TURN = {0: 0.0, 1: 0.05, 2: 0.25}    # cost of a 45 / 90 degree turn (mm); sharper is not allowed
ROUNDS = 40
PRES0, PRES_GROW, HIST = 0.5, 1.4, 0.3
PULL = 0.3                           # weight of the end-to-destination distance


class Grid(Occ):
    """Cells of one copper layer that a stub (width W) cannot use, over BOX
    plus MARGIN (occ.Occ: a cell is free for a net when no other net's
    copper is within W / 2 plus the clearance)."""

    def __init__(self, board, layer, cx, cy, window=None, w=W):
        super().__init__(board, layer, cx, cy,
                         window or (BOX[0] - MARGIN, BOX[1] - MARGIN, BOX[2] + MARGIN, BOX[3] + MARGIN), w)

    def out(self, i, j):
        x, y = self.xy(i, j)
        return x < BOX[0] - EXIT or x > BOX[2] + EXIT or y < BOX[1] - EXIT or y > BOX[3] + EXIT

    def footprint(self, cells):
        """Cells closer than w + CLR to a stub through the given cells."""
        r = self.w + CLR + EPS
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
        nx, ny, arr = self.nx, self.ny, self.a
        nid = self.ids.get(net, -2)
        x0, y0 = self.x0, self.y0
        bx0, by0, bx1, by1 = BOX[0] - EXIT, BOX[1] - EXIT, BOX[2] + EXIT, BOX[3] + EXIT
        dxd, dyd = dest
        hcache, outc = {}, {}

        def free(i, j):
            if 0 <= i < nx and 0 <= j < ny:
                v = arr[i * ny + j]
                return v == 0 or v == nid
            return False

        def h(i, j):
            # admissible: the stub from here plus the straight run from its
            # end to dest is never shorter than the straight run from here
            k = i * ny + j
            r = hcache.get(k)
            if r is None:
                x, y = round(x0 + i * GRID, 4), round(y0 + j * GRID, 4)
                r = hcache[k] = PULL * math.hypot(x - dxd, y - dyd)
            return r
        moves = []
        for d in range(8):
            row = []
            for nd in (d - 2, d - 1, d, d + 1, d + 2):
                nd %= 8
                turn = min((nd - d) % 8, (d - nd) % 8)
                dx, dy = DIRS[nd]
                row.append((nd, dx, dy, GRID * (1.4142 if dx and dy else 1.0), TURN[turn]))
            moves.append(row)
        heap = []
        for d in range(8):
            heapq.heappush(heap, (h(si, sj), 0.0, si, sj, d, None))
        prev = {}
        best = {}
        heappush, heappop = heapq.heappush, heapq.heappop
        while heap:
            f, g, i, j, d, par = heappop(heap)
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
            x, y = round(x0 + i * GRID, 4), round(y0 + j * GRID, 4)
            if x < bx0 or x > bx1 or y < by0 or y > by1:
                gg = g + PULL * math.hypot(x - dxd, y - dyd)
                heappush(heap, (gg, gg, i, j, -1, key))
                continue
            started = par is not None
            for nd, dx, dy, step, tc in moves[d]:
                ni, nj = i + dx, j + dy
                if not free(ni, nj):
                    continue
                if dx and dy and not (free(i + dx, j) or free(i, j + dy)):
                    continue
                nk = (ni, nj, nd)
                if nk in prev:
                    continue
                ng = g + step * (1 + hist.get((ni, nj), 0.0)) + tc * started
                occ = soft.get((ni, nj))
                if occ:
                    ng += pres * sum(1 for n in occ if n != net)
                if best.get(nk, 1e9) <= ng:
                    continue
                best[nk] = ng
                heappush(heap, (ng + h(ni, nj), ng, ni, nj, nd, key))
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
    snap = Snap(board)
    grids = {k: Grid(snap, v, cx, cy) for k, v in LAY.items()}
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
