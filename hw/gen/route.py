# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Small helpers for scripted copper: tracks, vias and pad lookups."""
import pcbnew

MM = pcbnew.FromMM
LAYER = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu, "In1": pcbnew.In1_Cu, "In2": pcbnew.In2_Cu}


def P(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


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
            self.board.Add(t)
        return pts

    def via(self, net, x, y, d=0.45, drill=0.25):
        v = pcbnew.PCB_VIA(self.board)
        v.SetPosition(P(x, y))
        v.SetWidth(MM(d))
        v.SetDrill(MM(drill))
        v.SetNet(self.net(net))
        self.board.Add(v)
        return x, y
