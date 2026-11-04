# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Small helpers for scripted copper: tracks, vias and pad lookups."""
import uuid

import pcbnew

MM = pcbnew.FromMM
LAYER = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu, "In1": pcbnew.In1_Cu, "In2": pcbnew.In2_Cu,
         "In3": pcbnew.In3_Cu, "In4": pcbnew.In4_Cu}


def P(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


NS = uuid.UUID("6f0c1a52-6d0e-4b7a-9a43-1d2b0e5f7c11")
_seen = {}


def stable_id(item, *key):
    """Name-based uuid (uuid5 of the item's geometry), so a regenerated board
    is byte-identical; a repeated key gets a running number."""
    k = "|".join(str(x) for x in key)
    n = _seen.get(k, 0)
    _seen[k] = n + 1
    item.SetUuid(pcbnew.KIID(str(uuid.uuid5(NS, f"{k}|{n}"))))


class Copper:
    def __init__(self, board):
        self.board = board
        self.fps = {fp.GetReference(): fp for fp in board.GetFootprints()}

    def net(self, name):
        n = self.board.FindNet(name)
        if n is None:
            raise KeyError(f"net {name}")
        return n

    def pad(self, ref, num):
        """Centre of a pad (the first one with that number)."""
        for p in self.fps[ref].Pads():
            if p.GetNumber() == num:
                q = p.GetPosition()
                return pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
        raise KeyError(f"{ref}.{num}")

    def pad_net(self, ref, num):
        for p in self.fps[ref].Pads():
            if p.GetNumber() == num:
                return p.GetNetname()
        raise KeyError(f"{ref}.{num}")

    def track(self, net, pts, width, layer="F"):
        """Polyline; points may be (x, y) tuples or ("ref", "pad") pad names."""
        pts = [self.pad(*p) if isinstance(p[0], str) else p for p in pts]
        n = self.net(net)
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(P(*a))
            t.SetEnd(P(*b))
            t.SetWidth(MM(width))
            t.SetLayer(LAYER[layer])
            t.SetNet(n)
            stable_id(t, "t", net, layer, a, b, width)
            self.board.Add(t)
        return pts

    def via(self, net, x, y, d=0.45, drill=0.3):
        v = pcbnew.PCB_VIA(self.board)
        v.SetPosition(P(x, y))
        v.SetWidth(MM(d))
        v.SetDrill(MM(drill))
        v.SetNet(self.net(net))
        stable_id(v, "v", net, x, y, d, drill)
        self.board.Add(v)
        return x, y


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


class Space:
    """Copper already on the board, for "is there room for a via / a short
    track here" checks. Pads are taken as their bounding boxes (exact for the
    0/90 degree rectangles and conservative for round pads); a through via
    meets every copper item, a track only those on its layer. Round pads
    are circles."""

    def __init__(self, board):
        T = pcbnew.ToMM
        self.items = []   # (kind, layers or None, geometry, net)
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                q = t.GetPosition()
                self.items.append(("c", None, (T(q.x), T(q.y), T(t.GetWidth(pcbnew.F_Cu)) / 2), t.GetNetname()))
            else:
                s, e = t.GetStart(), t.GetEnd()
                self.items.append(("s", {t.GetLayer()}, (T(s.x), T(s.y), T(e.x), T(e.y), T(t.GetWidth()) / 2),
                                   t.GetNetname()))
        for fp in board.GetFootprints():
            for p in fp.Pads():
                lays = {l for l in LAYER.values() if p.IsOnLayer(l)}
                if not lays:
                    continue
                bb = p.GetBoundingBox()
                if p.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE:
                    q = p.GetPosition()
                    self.items.append(("c", lays, (T(q.x), T(q.y), T(p.GetSize(pcbnew.F_Cu).x) / 2), p.GetNetname()))
                else:
                    self.items.append(("r", lays, (T(bb.GetLeft()), T(bb.GetTop()), T(bb.GetRight()), T(bb.GetBottom())),
                                       p.GetNetname()))
                if p.GetDrillSize().x > 0:     # drilled pads count on every layer
                    self.items[-1] = (self.items[-1][0], None, self.items[-1][2], p.GetNetname())

    @staticmethod
    def _dist_point(kind, g, x, y):
        if kind == "c":
            return ((x - g[0]) ** 2 + (y - g[1]) ** 2) ** 0.5 - g[2]
        if kind == "s":
            return _seg_dist(x, y, *g[:4]) - g[4]
        dx = max(g[0] - x, 0, x - g[2])
        dy = max(g[1] - y, 0, y - g[3])
        return (dx * dx + dy * dy) ** 0.5

    def via_ok(self, x, y, r, clr, net=None, ignore=()):
        """Room for a through via of radius r at (x, y): clr to everything
        except items of the same net listed in ignore (the pad it serves)."""
        for i, (kind, lays, g, n) in enumerate(self.items):
            if i in ignore:
                continue
            gap = clr if n != net else 0.0
            if self._dist_point(kind, g, x, y) < r + gap:
                return False
        return True

    def seg_ok(self, a, b, hw, layer, clr, net, ignore=()):
        """Room for a track a-b of half width hw on one layer (sampled)."""
        n = max(2, int(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 / 0.05) + 1)
        for i, (kind, lays, g, nn) in enumerate(self.items):
            if i in ignore or nn == net:
                continue
            if lays is not None and layer not in lays:
                continue
            for k in range(n):
                t = k / (n - 1)
                x, y = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
                if self._dist_point(kind, g, x, y) < hw + clr:
                    return False
        return True

    def find(self, x, y):
        """Indices of items touching a point (to ignore one's own pad)."""
        return {i for i, (k, l, g, n) in enumerate(self.items) if self._dist_point(k, g, x, y) <= 0}

    def add_via(self, x, y, r, net):
        self.items.append(("c", None, (x, y, r), net))

    def add_seg(self, a, b, hw, layer, net):
        self.items.append(("s", {layer}, (a[0], a[1], b[0], b[1], hw), net))
