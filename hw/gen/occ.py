# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Occupancy grid of one copper layer for the finishing router (D-77).

The same cells as escape.Grid (0.05 mm, a cell is taken for a net when
some other net's copper is closer than the track half width plus the
clearance), kept in a flat integer array: 0 free, a net id when only that
net's copper is near, MULTI when several are (or a keep-out). That is all
free() needs, and it lets the finishing router build one grid per layer
for the whole board and add each new track to it, instead of building a
dict grid per connection (escape.Grid). Shapes are rasterised a column at
a time: each one meets a grid column in a single interval (they are all
convex), so no cell is tested on its own.
"""
import math
from array import array

import pcbnew

from escape import GRID, CLR, HOLE_CLR, EPS, FIELD

MULTI = -1


class Occ:
    def __init__(self, board, layer, cx, cy, window, w, skip=None, clr=None):
        self.layer = layer
        self.w = w
        x0, y0, x1, y1 = window
        self.x0, self.y0 = x0, y0
        self.nx = int(round((x1 - x0) / GRID)) + 1
        self.ny = int(round((y1 - y0) / GRID)) + 1
        self.a = array("i", bytes(4 * self.nx * self.ny))
        self.cx, self.cy = cx, cy
        self.clr = clr or (lambda net: CLR)
        self.ids = {}
        T = pcbnew.ToMM
        hw = w / 2
        for t in board.GetTracks():
            if skip is not None and skip(t):
                continue
            self.add_item(t)
        for fp in board.GetFootprints():
            for p in fp.Pads():
                drilled = p.GetDrillSize().x > 0
                if not (drilled or p.IsOnLayer(layer)):
                    continue
                q = p.GetPosition()
                x, y = T(q.x), T(q.y)
                net = p.GetNetname()
                if drilled:
                    self.circle(x, y, max(T(p.GetDrillSize().x), T(p.GetDrillSize().y)) / 2 + hw + HOLE_CLR, net)
                if not p.IsOnLayer(layer):
                    continue
                if p.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE:
                    self.circle(x, y, T(p.GetSize(pcbnew.F_Cu).x) / 2 + hw + self.clr(net), net)
                else:
                    bb = p.GetBoundingBox()
                    self.rect(T(bb.GetLeft()), T(bb.GetTop()), T(bb.GetRight()), T(bb.GetBottom()),
                              hw + self.clr(net), net)

    def add_item(self, t):
        """Mark a track (on this layer) or a via."""
        T = pcbnew.ToMM
        net = t.GetNetname()
        if t.GetClass() == "PCB_VIA":
            q = t.GetPosition()
            self.via(T(q.x), T(q.y), T(t.GetWidth(pcbnew.F_Cu)) / 2, T(t.GetDrill()) / 2, net)
        elif t.GetLayer() == self.layer:
            s, e = t.GetStart(), t.GetEnd()
            self.track((T(s.x), T(s.y)), (T(e.x), T(e.y)), T(t.GetWidth()) / 2, net)

    def via(self, x, y, r, drill_r, net):
        reach = r + self.w / 2 + self.clr(net)
        if max(abs(x - self.cx), abs(y - self.cy)) > FIELD:
            reach = max(reach, drill_r + self.w / 2 + HOLE_CLR)
        self.circle(x, y, reach, net)

    def track(self, a, b, hw, net):
        self.seg(a, b, hw + self.w / 2 + self.clr(net), net)

    # ------------------------------------------------------------ cells
    def nid(self, net):
        if not net:
            return MULTI
        n = self.ids.get(net)
        if n is None:
            n = self.ids[net] = len(self.ids) + 1
        return n

    def xy(self, i, j):
        return round(self.x0 + i * GRID, 4), round(self.y0 + j * GRID, 4)

    def ij(self, x, y):
        return int(round((x - self.x0) / GRID)), int(round((y - self.y0) / GRID))

    def free(self, i, j, net):
        if not (0 <= i < self.nx and 0 <= j < self.ny):
            return False
        v = self.a[i * self.ny + j]
        return v == 0 or (v != MULTI and v == self.ids.get(net, -2))

    def _columns(self, xlo, xhi):
        i0 = max(int(math.ceil((xlo - self.x0) / GRID - 1e-9)), 0)
        i1 = min(int(math.floor((xhi - self.x0) / GRID + 1e-9)), self.nx - 1)
        return range(i0, i1 + 1)

    def _fill(self, i, ylo, yhi, n):
        j0 = max(int(math.ceil((ylo - self.y0) / GRID - 1e-9)), 0)
        j1 = min(int(math.floor((yhi - self.y0) / GRID + 1e-9)), self.ny - 1)
        if j1 < j0:
            return
        a, base = self.a, i * self.ny
        if n == MULTI:
            a[base + j0:base + j1 + 1] = array("i", [MULTI]) * (j1 - j0 + 1)
            return
        for k in range(base + j0, base + j1 + 1):
            v = a[k]
            if v == 0:
                a[k] = n
            elif v != n:
                a[k] = MULTI

    def circle(self, x, y, reach, net):
        R = reach + EPS
        n = self.nid(net)
        for i in self._columns(x - R, x + R):
            dx = self.x0 + i * GRID - x
            d2 = R * R - dx * dx
            if d2 < 0:
                continue
            h = math.sqrt(d2)
            self._fill(i, y - h, y + h, n)

    def rect(self, l, t, r, b, reach, net):
        R = reach + EPS
        n = self.nid(net)
        for i in self._columns(l - R, r + R):
            px = self.x0 + i * GRID
            dx = max(l - px, 0.0, px - r)
            if dx > R:
                continue
            h = math.sqrt(R * R - dx * dx)
            self._fill(i, t - h, b + h, n)

    def seg(self, a, b, reach, net):
        """Capsule of radius reach around a-b: per column, the union of the
        two end discs and the band beside the segment (one interval)."""
        R = reach + EPS
        n = self.nid(net)
        (ax, ay), (bx, by) = a, b
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        L = math.sqrt(L2)
        for i in self._columns(min(ax, bx) - R, max(ax, bx) + R):
            px = self.x0 + i * GRID
            lo, hi = math.inf, -math.inf
            for cx, cy in (a, b):
                d2 = R * R - (px - cx) ** 2
                if d2 >= 0:
                    h = math.sqrt(d2)
                    lo, hi = min(lo, cy - h), max(hi, cy + h)
            if L2 > 0:
                if dx == 0:
                    if abs(px - ax) <= R:
                        lo, hi = min(lo, ay, by), max(hi, ay, by)
                else:
                    c = (px - ax) * dy
                    p, q = sorted(((c - R * L) / dx, (c + R * L) / dx))
                    if dy != 0:
                        u0, u1 = sorted(((0 - (px - ax) * dx) / dy, (L2 - (px - ax) * dx) / dy))
                        p, q = max(p, u0), min(q, u1)
                    elif not (0 <= (px - ax) * dx <= L2):
                        p, q = 1.0, 0.0
                    if p <= q:
                        lo, hi = min(lo, ay + p), max(hi, ay + q)
            if lo <= hi:
                self._fill(i, lo, hi, n)


def blank(like):
    """An empty Occ over the same window as like."""
    o = Occ.__new__(Occ)
    o.__dict__.update(layer=like.layer, w=like.w, x0=like.x0, y0=like.y0, nx=like.nx, ny=like.ny,
                      cx=like.cx, cy=like.cy, clr=like.clr, ids={},
                      a=array("i", bytes(4 * like.nx * like.ny)))
    return o
