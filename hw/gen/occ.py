# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Occupancy grids on the 0.05 mm routing lattice (D-75, D-77).

A cell of one copper layer is taken for a net when some other net's
copper is closer than the track half width plus the clearance. Occ keeps
the cells in a flat integer array: 0 free, a net id when only that net's
copper is near, MULTI when several are (or a keep-out); that is all the
searches need. Sets keeps, per cell, the set of keys marked there (the
finishing router's tracks that could be taken up).

Shapes (discs, rectangles grown by a radius, capsules) are rasterised a
column at a time: each meets a column in one interval, found from the
geometry and then trimmed with the exact point test, so a cell is marked
exactly when its centre (rounded to 0.1 um) is strictly inside. Every
window starts on the same global lattice, so a shape's cells are worked
out once and reused by every grid it falls into.

Snap reads the board's tracks and pads once into plain numbers, so the
many grids of the finishing router do not each go through pcbnew.
"""
import math
from array import array

import pcbnew

GRID = 0.05
CLR = 0.1
HOLE_CLR = 0.2
EPS = 0.004
FIELD = 4.5                          # vias within this of U1's centre are in the ball field
MULTI = -1
LAYERS = (pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)    # the signal layers


class Snap:
    """The board's tracks, vias and pads as plain numbers.
    tracks: (item, net, layer or None for a via, geometry, half width, drill radius)
    pads: (net, x, y, drill radius or None, layers, circle radius or None, bbox)"""

    def __init__(self, board):
        T = pcbnew.ToMM
        self.tracks = []
        for t in board.GetTracks():
            net = t.GetNetname()
            if t.GetClass() == "PCB_VIA":
                q = t.GetPosition()
                self.tracks.append((t, net, None, (T(q.x), T(q.y)), T(t.GetWidth(pcbnew.F_Cu)) / 2,
                                    T(t.GetDrill()) / 2))
            else:
                s, e = t.GetStart(), t.GetEnd()
                self.tracks.append((t, net, t.GetLayer(), ((T(s.x), T(s.y)), (T(e.x), T(e.y))),
                                    T(t.GetWidth()) / 2, None))
        self.pads = []
        for fp in board.GetFootprints():
            for p in fp.Pads():
                q = p.GetPosition()
                ds = p.GetDrillSize()
                drill = max(T(ds.x), T(ds.y)) / 2 if ds.x > 0 else None
                on = frozenset(l for l in LAYERS if p.IsOnLayer(l))
                circ = T(p.GetSize(pcbnew.F_Cu).x) / 2 if p.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE else None
                bb = p.GetBoundingBox()
                self.pads.append((p.GetNetname(), T(q.x), T(q.y), drill, on, circ,
                                  (T(bb.GetLeft()), T(bb.GetTop()), T(bb.GetRight()), T(bb.GetBottom()))))

    def without(self, drop):
        """The same snapshot less the track records whose id() is in drop."""
        s = Snap.__new__(Snap)
        s.tracks = [rec for rec in self.tracks if id(rec) not in drop]
        s.pads = self.pads
        return s


_SPANS = {}     # shape -> its cells on the global lattice, as column intervals


def _span(px, lo, hi, inside):
    """Rows of one column inside a shape: the candidate interval [lo, hi]
    (a little wider than the shape), trimmed with the exact test."""
    j0 = int(math.floor(lo / GRID))
    j1 = int(math.ceil(hi / GRID))
    while j0 <= j1 and not inside(px, round(j0 * GRID, 4)):
        j0 += 1
    while j1 > j0 and not inside(px, round(j1 * GRID, 4)):
        j1 -= 1
    return j0, j1


def _circle(x, y, R):
    RR = R * R
    Rw = R + 1e-6

    def inside(px, py):
        return (px - x) ** 2 + (py - y) ** 2 < RR
    out = []
    for i in range(int(math.floor((x - Rw) / GRID)), int(math.ceil((x + Rw) / GRID)) + 1):
        px = round(i * GRID, 4)
        d2 = Rw * Rw - (px - x) ** 2
        if d2 < 0:
            continue
        h = math.sqrt(d2)
        j0, j1 = _span(px, y - h, y + h, inside)
        if j0 <= j1:
            out.append((i, j0, j1))
    return out


def _rect(l, t, r, b, R):
    RR = R * R
    Rw = R + 1e-6

    def inside(px, py):
        dx, dy = max(l - px, 0, px - r), max(t - py, 0, py - b)
        return dx * dx + dy * dy < RR
    out = []
    for i in range(int(math.floor((l - Rw) / GRID)), int(math.ceil((r + Rw) / GRID)) + 1):
        px = round(i * GRID, 4)
        dx = max(l - px, 0.0, px - r)
        if dx > Rw:
            continue
        h = math.sqrt(Rw * Rw - dx * dx)
        j0, j1 = _span(px, t - h, b + h, inside)
        if j0 <= j1:
            out.append((i, j0, j1))
    return out


def _seg(a, b, R):
    """Capsule of radius R around a-b: per column, the union of the two end
    discs and the band beside the segment (one interval)."""
    RR = R * R
    Rw = R + 1e-6
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    L = math.sqrt(L2)

    def inside(px, py):
        u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        return (px - ax - u * dx) ** 2 + (py - ay - u * dy) ** 2 < RR
    out = []
    for i in range(int(math.floor((min(ax, bx) - Rw) / GRID)), int(math.ceil((max(ax, bx) + Rw) / GRID)) + 1):
        px = round(i * GRID, 4)
        lo, hi = math.inf, -math.inf
        for cx, cy in (a, b):
            d2 = Rw * Rw - (px - cx) ** 2
            if d2 >= 0:
                h = math.sqrt(d2)
                lo, hi = min(lo, cy - h), max(hi, cy + h)
        if L2 > 0:
            if dx == 0:
                if abs(px - ax) <= Rw:
                    lo, hi = min(lo, ay, by), max(hi, ay, by)
            else:
                c = (px - ax) * dy
                p, q = sorted(((c - Rw * L) / dx, (c + Rw * L) / dx))
                if dy != 0:
                    u0, u1 = sorted(((0 - (px - ax) * dx) / dy, (L2 - (px - ax) * dx) / dy))
                    p, q = max(p, u0), min(q, u1)
                elif not (0 <= (px - ax) * dx <= L2):
                    p, q = 1.0, 0.0
                if p <= q:
                    lo, hi = min(lo, ay + p), max(hi, ay + q)
        if lo <= hi:
            j0, j1 = _span(px, lo, hi, inside)
            if j0 <= j1:
                out.append((i, j0, j1))
    return out


def spans(kind, *args):
    """The cells of a shape on the global lattice (cell (i, j) centred on
    (i * GRID, j * GRID)), as (i, j0, j1) column intervals with the bounding
    range of i and j; cached, as the same tracks go into many grids."""
    key = (kind,) + args
    s = _SPANS.get(key)
    if s is None:
        cols = {"c": _circle, "r": _rect, "s": _seg}[kind](*args)
        if cols:
            s = (cols, cols[0][0], cols[-1][0], min(c[1] for c in cols), max(c[2] for c in cols))
        else:
            s = ((), 0, -1, 0, -1)
        _SPANS[key] = s
    return s


class Raster:
    """A window of the global lattice (it must start on a lattice point, as
    every window here does) and the shape rasterisers; a cell is marked
    when its centre is strictly inside the shape grown by EPS. Subclasses
    keep the marks (_mark)."""

    def _window(self, window):
        x0, y0, x1, y1 = window
        self.x0, self.y0 = x0, y0
        self.nx = int(round((x1 - x0) / GRID)) + 1
        self.ny = int(round((y1 - y0) / GRID)) + 1
        self._origin()

    def _origin(self):
        self.oi, self.oj = int(round(self.x0 / GRID)), int(round(self.y0 / GRID))
        assert abs(self.oi * GRID - self.x0) < 1e-6 and abs(self.oj * GRID - self.y0) < 1e-6, (self.x0, self.y0)

    def xy(self, i, j):
        return round(self.x0 + i * GRID, 4), round(self.y0 + j * GRID, 4)

    def ij(self, x, y):
        return int(round((x - self.x0) / GRID)), int(round((y - self.y0) / GRID))

    def _put(self, s, key):
        cols, gi0, gi1, gj0, gj1 = s
        oi, oj, nx, ny = self.oi, self.oj, self.nx, self.ny
        if gi1 < oi or gi0 >= oi + nx or gj1 < oj or gj0 >= oj + ny:
            return
        for gi, j0, j1 in cols:
            i = gi - oi
            if 0 <= i < nx:
                j0, j1 = max(j0 - oj, 0), min(j1 - oj, ny - 1)
                if j0 <= j1:
                    self._mark(i, j0, j1, key)

    def circle(self, x, y, reach, key):
        self._put(spans("c", x, y, reach + EPS), key)

    def rect(self, l, t, r, b, reach, key):
        self._put(spans("r", l, t, r, b, reach + EPS), key)

    def seg(self, a, b, reach, key):
        self._put(spans("s", a, b, reach + EPS), key)


class Occ(Raster):
    """Cells of one copper layer that a track of width w cannot use. board
    is a pcbnew board or a Snap; tracks for which skip(track) is true are
    left out; clr(net) gives the clearance to another net's copper
    (default CLR). Vias outside FIELD of (cx, cy) also keep HOLE_CLR from
    their hole (inside, the BGA rule's copper clearance covers it)."""

    def __init__(self, board, layer, cx, cy, window, w, skip=None, clr=None):
        snap = board if isinstance(board, Snap) else Snap(board)
        self.layer = layer
        self.w = w
        self._window(window)
        self.a = array("i", bytes(4 * self.nx * self.ny))
        self.cx, self.cy = cx, cy
        self.clr = clr or (lambda net: CLR)
        self.ids = {}
        hw = w / 2
        for rec in snap.tracks:
            if skip is not None and skip(rec[0]):
                continue
            self.add(rec)
        for net, x, y, drill, on, circ, bb in snap.pads:
            if drill is not None:
                self.circle(x, y, drill + hw + HOLE_CLR, net)
            if layer not in on:
                continue
            if circ is not None:
                self.circle(x, y, circ + hw + self.clr(net), net)
            else:
                self.rect(bb[0], bb[1], bb[2], bb[3], hw + self.clr(net), net)

    def add(self, rec):
        """Mark a Snap track record (a track on this layer, or a via)."""
        _, net, layer, geo, r, drill_r = rec
        if layer is None:
            self.via(geo[0], geo[1], r, drill_r, net)
        elif layer == self.layer:
            self.track(geo[0], geo[1], r, net)

    def add_item(self, t):
        T = pcbnew.ToMM
        if t.GetClass() == "PCB_VIA":
            q = t.GetPosition()
            self.via(T(q.x), T(q.y), T(t.GetWidth(pcbnew.F_Cu)) / 2, T(t.GetDrill()) / 2, t.GetNetname())
        elif t.GetLayer() == self.layer:
            s, e = t.GetStart(), t.GetEnd()
            self.track((T(s.x), T(s.y)), (T(e.x), T(e.y)), T(t.GetWidth()) / 2, t.GetNetname())

    def via_reach(self, x, y, r, drill_r, net=None):
        reach = r + self.w / 2 + self.clr(net)
        if max(abs(x - self.cx), abs(y - self.cy)) > FIELD:
            reach = max(reach, drill_r + self.w / 2 + HOLE_CLR)
        return reach

    def via(self, x, y, r, drill_r, net):
        self.circle(x, y, self.via_reach(x, y, r, drill_r, net), net)

    def track(self, a, b, hw, net):
        self.seg(a, b, hw + self.w / 2 + self.clr(net), net)

    def nid(self, net):
        if not net:
            return MULTI
        n = self.ids.get(net)
        if n is None:
            n = self.ids[net] = len(self.ids) + 1
        return n

    def free(self, i, j, net):
        if not (0 <= i < self.nx and 0 <= j < self.ny):
            return False
        v = self.a[i * self.ny + j]
        return v == 0 or (v != MULTI and v == self.ids.get(net, -2))

    def _mark(self, i, j0, j1, net):
        n = self.nid(net)
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


class Sets(Raster):
    """cells: (i, j) -> set of the keys marked there."""

    def __init__(self, like):
        self.layer, self.w = like.layer, like.w
        self.x0, self.y0, self.nx, self.ny = like.x0, like.y0, like.nx, like.ny
        self._origin()
        self.cells = {}

    def _mark(self, i, j0, j1, key):
        cells = self.cells
        for j in range(j0, j1 + 1):
            s = cells.get((i, j))
            if s is None:
                cells[(i, j)] = {key}
            else:
                s.add(key)


def blank(like):
    """An empty Occ over the same window as like."""
    o = Occ.__new__(Occ)
    o.__dict__.update(layer=like.layer, w=like.w, x0=like.x0, y0=like.y0, nx=like.nx, ny=like.ny,
                      cx=like.cx, cy=like.cy, clr=like.clr, ids={}, oi=like.oi, oj=like.oj,
                      a=array("i", bytes(4 * like.nx * like.ny)))
    return o
