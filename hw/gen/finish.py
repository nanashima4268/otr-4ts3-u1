# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Finishing router for the connections Freerouting leaves open (D-77).

Freerouting stops at a few connections in the crowded strip between the
FX3 and the FPGA (D-74, D-75), and a second Freerouting run on the routed
board does worse (it treats the fixed wiring as obstacles but not as part
of the nets). So, as is common after an autorouter, the leftovers are
finished by a plain maze router that only uses free space and never moves
existing copper:

- for every routed net (autoroute.routed_nets) whose copper falls into
  more than one piece, the smallest piece is joined to the nearest other
  piece, until one piece is left;
- the search is A* on the 0.05 mm grid of occ.Occ, on the three signal
  layers (F.Cu, In2, B.Cu), 8 directions, with through vias (0.45 / 0.3 mm)
  between them where every layer has room;
- the track takes its net class width and falls back to 0.1 mm;
- the receiver channels (layout.RX_BAND), the card edge and the track
  keep-out rule areas are kept clear;
- where free space is not enough, the usual rip-up and reroute: the
  search may cross other routed nets' tracks at a price (RIP_COST per
  grid step), those tracks are taken up, their remains removed, and their
  nets joined again the same way (the joins made here are never taken up,
  so this ends).

The plane nets connect through the poured zones, which are only filled
after the board is saved; planes() then joins, on the filled board, the
plane pins that reach no plane (no room for planes.py's via, or no plane
under them: the card-edge fingers, the USB-C, parts in the RF and USB
areas) with a track to a via inside the plane, and the separate islands
of a plane net with each other. A rip-up made for a plane pin is undone
when a signal it took up cannot be joined again.
"""
import heapq
import math

import pcbnew

import layout as L
import rules
from escape import simplify
from occ import Occ, Sets, Snap, blank, GRID, CLR, HOLE_CLR
from autoroute import PLANE_NETS     # every net with an inner-layer plane
from fanout import U
from route import stable_id

LAYERS = {"F": pcbnew.F_Cu, "In2": pcbnew.In2_Cu, "B": pcbnew.B_Cu}
VIA_D, VIA_DRILL = 0.45, 0.3
VIA_COST = 1.5            # mm of track a layer change is worth
MARGINS = (3.0, 8.0, 20.0)   # search window around the pieces, tried in turn
PLANE_MARGINS = (3.0, 8.0, 20.0)   # a plane pin may sit far from its plane (RF, USB areas)
EDGE_CLR = 0.3            # rules.py
WIDTH = {"POWER": 0.3}    # rules.CLASSES track widths that differ from 0.1 mm
MAX_JOINS = 40
HOLE_GAP = 0.25           # hole to hole (KiCad 0.2 mm, JLC 0.25 mm for vias)
SINK_PITCH = 0.25        # plane vias of planes() sit on this lattice
RIP_COST = 2.0         # mm per grid step over a track that would be taken up
RIPPED = {}            # net -> times taken up in this finish() run: each time
                       # makes it dearer to take up again (as in PathFinder), so
                       # nets that wall each other in do not take turns forever


def T(v):
    return pcbnew.ToMM(v)


TAKEN = None      # while a list: every track and via removed here, for undo()


def remove(board, it):
    if TAKEN is not None:
        # plain numbers: the SWIG point objects die with the item
        if it.GetClass() == "PCB_VIA":
            q = it.GetPosition()
            TAKEN.append(("via", it.GetNetCode(), (int(q.x), int(q.y)), int(it.GetWidth(pcbnew.F_Cu)),
                          int(it.GetDrill()), it.m_Uuid.AsString()))
        else:
            a, b = it.GetStart(), it.GetEnd()
            TAKEN.append(("track", it.GetNetCode(), it.GetLayer(), (int(a.x), int(a.y)), (int(b.x), int(b.y)),
                          int(it.GetWidth()), it.m_Uuid.AsString()))
    board.Delete(it)


def undo(board, before, taken):
    """Back to the copper of before (the uuids of the tracks and vias then):
    remove what was added since, put back what was removed."""
    for t in list(board.GetTracks()):
        if t.m_Uuid.AsString() not in before:
            board.Delete(t)
    for rec in taken:
        if rec[-1] not in before:
            continue
        if rec[0] == "via":
            _, code, pos, d, drill, uid = rec
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(*pos))
            v.SetWidth(d)
            v.SetDrill(drill)
        else:
            _, code, layer, a, b, w, uid = rec
            v = pcbnew.PCB_TRACK(board)
            v.SetStart(pcbnew.VECTOR2I(*a))
            v.SetEnd(pcbnew.VECTOR2I(*b))
            v.SetWidth(w)
            v.SetLayer(layer)
        v.SetNetCode(code)
        v.SetUuid(pcbnew.KIID(uid))
        board.Add(v)


def clearance(board):
    """clr(net): the net class clearance (rules.CLASSES), at least CLR."""
    cache = {}

    def clr(net):
        if net not in cache:
            n = board.FindNet(net) if net else None
            nc = n.GetNetClassName().split(",")[0] if n else ""
            cache[net] = max(CLR, rules.CLASSES[nc][0][1]) if nc in rules.CLASSES else CLR
        return cache[net]
    return clr


def net_class_width(board, net):
    nc = board.FindNet(net).GetNetClassName() if board.FindNet(net) else ""
    return WIDTH.get(nc.split(",")[0], 0.1)


def pieces(board, net):
    """The net's copper (pads, tracks, vias) split into connected pieces."""
    conn = board.GetConnectivity()
    code = board.GetNetcodeFromNetname(net)
    items = [p for p in board.GetPads() if p.GetNetCode() == code]
    items += [t for t in board.GetTracks() if t.GetNetCode() == code]
    seen, out = set(), []
    for it in items:
        k = it.m_Uuid.AsString()
        if k in seen:
            continue
        group = [it] + [c.Cast() for c in conn.GetConnectedItems(it) if c.GetNetCode() == code]
        keep = []
        for g in group:
            gk = g.m_Uuid.AsString()
            if gk not in seen:
                seen.add(gk)
                keep.append(g)
        out.append(keep)
    return out


def bbox(piece):
    xs, ys = [], []
    for it in piece:
        bb = it.GetBoundingBox()
        xs += [T(bb.GetLeft()), T(bb.GetRight())]
        ys += [T(bb.GetTop()), T(bb.GetBottom())]
    return min(xs), min(ys), max(xs), max(ys)


def on_copper(grid, piece, lname):
    """Grid cells of one layer whose centre lies on the piece's copper: a
    track may start or end there."""
    layer = LAYERS[lname]
    out = set()

    def add_if(x0, y0, x1, y1, inside):
        i0, j0 = grid.ij(x0, y0)
        i1, j1 = grid.ij(x1, y1)
        for i in range(max(i0 - 1, 0), min(i1 + 2, grid.nx)):
            for j in range(max(j0 - 1, 0), min(j1 + 2, grid.ny)):
                if inside(*grid.xy(i, j)):
                    out.add((i, j))

    wx0, wy0 = grid.x0, grid.y0
    wx1, wy1 = grid.x0 + grid.nx * GRID, grid.y0 + grid.ny * GRID
    for it in piece:
        bb = it.GetBoundingBox()
        if T(bb.GetRight()) < wx0 or T(bb.GetLeft()) > wx1 or T(bb.GetBottom()) < wy0 or T(bb.GetTop()) > wy1:
            continue
        if it.GetClass() == "PCB_VIA":
            q = it.GetPosition()
            x, y, r = T(q.x), T(q.y), T(it.GetWidth(pcbnew.F_Cu)) / 2 - 0.02
            add_if(x - r, y - r, x + r, y + r, lambda px, py: (px - x) ** 2 + (py - y) ** 2 <= r * r)
        elif it.GetClass() == "PCB_TRACK":
            if it.GetLayer() != layer:
                continue
            s, e = it.GetStart(), it.GetEnd()
            a, b = (T(s.x), T(s.y)), (T(e.x), T(e.y))
            hw = T(it.GetWidth()) / 2 - 0.005

            def inside(px, py, a=a, b=b, hw=hw):
                dx, dy = b[0] - a[0], b[1] - a[1]
                L2 = dx * dx + dy * dy
                u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
                return (px - a[0] - u * dx) ** 2 + (py - a[1] - u * dy) ** 2 <= hw * hw
            add_if(min(a[0], b[0]) - hw, min(a[1], b[1]) - hw, max(a[0], b[0]) + hw, max(a[1], b[1]) + hw, inside)
        elif it.GetClass() == "PAD":
            if not it.IsOnLayer(layer):
                continue
            bb = it.GetBoundingBox()
            add_if(T(bb.GetLeft()), T(bb.GetTop()), T(bb.GetRight()), T(bb.GetBottom()),
                   lambda px, py, p=it: p.HitTest(pcbnew.VECTOR2I(pcbnew.FromMM(px), pcbnew.FromMM(py)), 0))
    return out


_EDGES = [None, None]     # (board, shapes) of the last board seen


def edge_shapes(board):
    """The card edge (its own outline and the footprints' notches) and the
    track keep-out rule areas, as ("seg", (a, b), None), ("rect", box, None)
    and ("area", box, layer names); read once per board."""
    if _EDGES[0] is board:
        return _EDGES[1]
    out = []
    edges = list(board.GetDrawings())
    for fp in board.GetFootprints():          # the card-edge connector draws its own notch
        edges += list(fp.GraphicalItems())
    for d in edges:
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        if d.GetShape() == pcbnew.SHAPE_T_SEGMENT:
            segs = [(d.GetStart(), d.GetEnd())]
        else:
            poly = d.GetPolyPoints() if d.GetShape() == pcbnew.SHAPE_T_POLY else None
            if poly is not None and len(poly):
                pts = list(poly)
                segs = list(zip(pts, pts[1:] + pts[:1]))
            elif d.GetShape() == pcbnew.SHAPE_T_RECT:
                c = d.GetCorners()
                segs = list(zip(c, c[1:] + c[:1]))
            else:     # arcs and circles: their bounding box
                bb = d.GetBoundingBox()
                out.append(("rect", (T(bb.GetLeft()), T(bb.GetTop()), T(bb.GetRight()), T(bb.GetBottom())), None))
                continue
        for a, b in segs:
            out.append(("seg", ((T(a.x), T(a.y)), (T(b.x), T(b.y))), None))
    for z in board.Zones():
        if not (z.GetIsRuleArea() and z.GetDoNotAllowTracks()):
            continue
        bb = z.GetBoundingBox()
        out.append(("area", (T(bb.GetLeft()), T(bb.GetTop()), T(bb.GetRight()), T(bb.GetBottom())),
                    [n for n, l in LAYERS.items() if z.IsOnLayer(l)]))
    _EDGES[0], _EDGES[1] = board, out
    return out


def keepouts(board, grids, window):
    """Mark the receiver channels, the card edge and track keep-outs as
    taken by every net (net name "")."""
    for g in grids.values():
        x0, y0, x1, y1 = L.RX_BAND
        g.rect(x0, y0, x1, y1, g.w / 2 + CLR, "")
    for kind, geo, names in edge_shapes(board):
        if kind == "seg":
            for g in grids.values():
                g.seg(geo[0], geo[1], g.w / 2 + EDGE_CLR, "")
        elif kind == "rect":
            for g in grids.values():
                g.rect(*geo, g.w / 2 + EDGE_CLR, "")
        else:
            for n in names:
                g = grids[n]
                g.rect(*geo, g.w / 2 + CLR, "")


def via_room(grids, board, w, pads=None, soft=None):
    """via_ok(i, j, net): a through via fits at the cell. The grids mark
    copper w / 2 + CLR wide around every item; a via needs VIA_D / 2 + CLR
    from copper and VIA_DRILL / 2 + HOLE_CLR from tracks, so it needs every
    cell within the larger difference free on all three layers (and, in
    rip-up mode, clear of the tracks that could be taken up). Plane-only
    layers need nothing: their pours keep clear of the via."""
    # the marks are whole cells: a track edge may lie up to half a cell
    # diagonal (GRID / sqrt 2) inside a free cell, hence the margin
    need = max(VIA_D / 2 + CLR, VIA_DRILL / 2 + HOLE_CLR) - (w / 2 + CLR) + GRID * 0.75
    k = int(need / GRID) + 1
    disk = [(a, b) for a in range(-k, k + 1) for b in range(-k, k + 1)
            if (a * GRID) ** 2 + (b * GRID) ** 2 <= need * need]
    g0 = next(iter(grids.values()))
    nx, ny = g0.nx, g0.ny
    offs = [a * ny + b for a, b in disk]
    arrays = [g.a for g in grids.values()]
    sets = [s.cells for s in soft.values()] if soft else None
    pa = pads.a if pads is not None else None
    caches = {}

    def ok(i, j, net):
        per = caches.get(net)
        if per is None:
            per = caches[net] = ({}, [(arr, g.ids.get(net, -2)) for g, arr in zip(grids.values(), arrays)])
        cache, layers = per
        base = i * ny + j
        r = cache.get(base)
        if r is None:
            r = k <= i < nx - k and k <= j < ny - k
            if r and pa is not None and pa[base]:
                r = False
            if r:
                for arr, nid in layers:
                    for o in offs:
                        v = arr[base + o]
                        if v and v != nid:
                            r = False
                            break
                    if not r:
                        break
            if r and sets:
                r = not any((i + a, j + b) in s for s in sets for a, b in disk)
            cache[base] = r
        return r
    return ok


def pad_grid(snap, g):
    """Cells where a via would touch a pad of any net, its own included: no
    via in pads (JLC fills those at extra cost, and solder would wick); nor
    closer than HOLE_GAP hole to hole to any via or drilled pad, own net
    included. snap: occ.Snap of the board."""
    out = blank(g)
    for _, x, y, drill, _, _, bb in snap.pads:
        out.rect(bb[0], bb[1], bb[2], bb[3], VIA_D / 2, "")
        if drill is not None:
            out.circle(x, y, drill + VIA_DRILL / 2 + HOLE_GAP, "")
    for _, _, layer, geo, _, drill_r in snap.tracks:
        if layer is None:
            out.circle(geo[0], geo[1], drill_r + VIA_DRILL / 2 + HOLE_GAP, "")
    return out


def plane_sink(board, net):
    """sink(x, y): a through via there lands well inside one of the net's
    filled planes (the refill then joins it)."""
    polys = []
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != net:
            continue
        for l in (pcbnew.In1_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu):
            if z.IsOnLayer(l):
                polys.append(z.GetFilledPolysList(l))
    for f in polys:
        f.BuildBBoxCaches()
    # the via's pad, 0.3 mm to the card edge (rules.py) and the plane's edge
    r = VIA_D / 2 + 0.3
    offs = [(0, 0), (r, 0), (-r, 0), (0, r), (0, -r)]
    cache = {}

    def inside(f, x, y):
        return f.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)), -1, 0, True)

    def sink(x, y):
        # only on a SINK_PITCH lattice: the polygon tests are the slow part
        k = (round(x / SINK_PITCH, 6), round(y / SINK_PITCH, 6))
        if k[0] != int(k[0]) or k[1] != int(k[1]):
            return False
        if k not in cache:
            cache[k] = any(all(inside(f, x + a, y + b) for a, b in offs) for f in polys)
        return cache[k]
    return sink


def search(grids, via_ok, net, starts, goals, goal_boxes, soft=None, sink=None):
    """A* from any start cell to any goal cell over (i, j, layer). soft
    (rip-up mode) maps each layer to a grid of the tracks that may be
    taken up: stepping into one of their cells costs RIP_COST more. With
    sink(x, y), a node where a via fits and sink is true is a goal too (the
    path then ends in a via, marked by an empty layer name)."""
    g0 = next(iter(grids.values()))
    nx, ny, x0, y0 = g0.nx, g0.ny, g0.x0, g0.y0
    occ = {l: (g.a, g.ids.get(net, -2)) for l, g in grids.items()}
    hc = {}

    def h(i, j):
        k = i * ny + j
        r = hc.get(k)
        if r is None:
            if not goal_boxes:
                r = 0.0
            else:
                x, y = round(x0 + i * GRID, 4), round(y0 + j * GRID, 4)
                r = min(math.hypot(max(bx0 - x, 0, x - bx1), max(by0 - y, 0, y - by1))
                        for bx0, by0, bx1, by1 in goal_boxes)
            hc[k] = r
        return r

    heap, best, prev = [], {}, {}
    for (i, j, l) in starts:
        arr, nid = occ[l]
        if 0 <= i < nx and 0 <= j < ny and arr[i * ny + j] in (0, nid):
            best[(i, j, l)] = 0.0
            heapq.heappush(heap, (h(i, j), 0.0, (i, j, l), None))
    names = list(grids)
    D = GRID * 1.4142
    DIRS = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
    heappush, heappop = heapq.heappush, heapq.heappop
    while heap:
        f, g, node, par = heappop(heap)
        if node in prev:
            continue
        prev[node] = par
        if node[2] == "" or node in goals:
            path = []
            k = node
            while k is not None:
                path.append(k)
                k = prev[k]
            return list(reversed(path))
        i, j, l = node
        arr, nid = occ[l]
        sc = soft[l].price if soft else None
        for dx, dy in DIRS:
            ni, nj = i + dx, j + dy
            if not (0 <= ni < nx and 0 <= nj < ny):
                continue
            v = arr[ni * ny + nj]
            if v and v != nid:
                continue
            if dx and dy:
                v = arr[ni * ny + j]
                if v and v != nid:
                    continue
                v = arr[i * ny + nj]
                if v and v != nid:
                    continue
                c = D
            else:
                c = GRID
            if sc is not None and (ni, nj) in sc:
                c += sc[(ni, nj)]
            nn = (ni, nj, l)
            ng = g + c
            if nn in prev or best.get(nn, 1e9) <= ng:
                continue
            best[nn] = ng
            heappush(heap, (ng + h(ni, nj), ng, nn, node))
        if via_ok(i, j, net):
            ng = g + VIA_COST
            nodes = [(i, j, m) for m in names if m != l]
            if sink is not None and sink(*g0.xy(i, j)):
                nodes.append((i, j, ""))
            for nn in nodes:
                if nn in prev or best.get(nn, 1e9) <= ng:
                    continue
                best[nn] = ng
                heappush(heap, (ng + h(i, j), ng, nn, node))
    return None


def join(board, cu, net, src, others, widths, rippable=None, sink=None, margins=MARGINS):
    """Route one track (with vias) from piece src to the nearest of others.
    With rippable(track) given, such tracks may be crossed and are then
    taken up. With sink (plane nets), the way may also end in a via that
    lands in the plane, and the window is taken around src alone.
    Each track width (widths, widest first) is tried in each window
    (margins, smallest first) before the next width. Returns None when no way was
    found, else the set of nets whose tracks were taken up."""
    fp = cu.fps[U]
    cx, cy = T(fp.GetPosition().x), T(fp.GetPosition().y)
    boxes = [] if sink else [bbox(p) for p in others]
    sb = bbox(src)
    windows = []
    for margin in margins:
        # the window starts on the SINK_PITCH lattice so grid cells hit it
        x0 = math.floor((min([sb[0]] + [b[0] for b in boxes]) - margin) / SINK_PITCH) * SINK_PITCH
        y0 = math.floor((min([sb[1]] + [b[1] for b in boxes]) - margin) / SINK_PITCH) * SINK_PITCH
        x1 = max([sb[2]] + [b[2] for b in boxes]) + margin
        y1 = max([sb[3]] + [b[3] for b in boxes]) + margin
        windows.append((x0, y0, x1, y1))
    snap = Snap(board)
    solid, rip = snap, []
    if rippable:
        # (uuid, record) of the tracks that may be taken up; the rest is solid
        rip = [(rec[0].m_Uuid.AsString(), rec) for rec in snap.tracks
               if rec[2] is not None and rippable(rec[0])]
        solid = snap.without({id(rec) for _, rec in rip})
    owner = {k: rec[0] for k, rec in rip}
    for w in widths:
        for window in windows:
            clr = clearance(board)
            grids = {n: Occ(solid, l, cx, cy, window, w, clr=clr) for n, l in LAYERS.items()}
            keepouts(board, grids, window)
            soft = None
            if rippable:
                soft = {n: Sets(g) for n, g in grids.items()}
                knet = {}
                for k, (_, net_k, layer, geo, r, _) in rip:
                    knet[k] = net_k
                    for n, l in LAYERS.items():
                        if layer == l:
                            soft[n].seg(geo[0], geo[1], r + w / 2 + clr(net_k), k)
                for sn in soft.values():
                    sn.price = {c: RIP_COST * (1 + max(RIPPED.get(knet[k], 0) for k in ks))
                                for c, ks in sn.cells.items()}
            starts = {(i, j, n) for n, g in grids.items() for i, j in on_copper(g, src, n)}
            goals = set()
            for p in others:
                goals |= {(i, j, n) for n, g in grids.items() for i, j in on_copper(g, p, n)}
            if not starts or not (goals or sink):
                continue
            # vias only where nothing would have to be taken up
            path = search(grids, via_room(grids, board, w, pad_grid(snap, grids["F"]), soft), net, starts, goals,
                          boxes, soft, sink)
            if path is None:
                continue
            ripped = set()
            if soft:
                for i, j, n in path:
                    if n in soft:            # not the sink's end point
                        ripped |= soft[n].cells.get((i, j), set())
            nets = {owner[k].GetNetname() for k in ripped}
            for n in nets:
                RIPPED[n] = RIPPED.get(n, 0) + 1
            for k in sorted(ripped):
                remove(board, owner[k])
            g0 = grids["F"]
            run = [path[0]]
            end_via = path[-1][2] == ""
            if end_via:
                path = path[:-1]
            for node in path[1:] + [None]:
                if node is not None and node[2] == run[-1][2]:
                    run.append(node)
                    continue
                if len(run) > 1:
                    pts = simplify([g0.xy(i, j) for i, j, _ in run])
                    cu.track(net, pts, w, run[0][2])
                if node is not None:
                    x, y = g0.xy(node[0], node[1])
                    cu.via(net, x, y, VIA_D, VIA_DRILL)
                    run = [node]
            if end_via:
                cu.via(net, *g0.xy(path[-1][0], path[-1][1]), VIA_D, VIA_DRILL)
            return nets
    return None


HARD_TRIES = 3


def finish(cu, routed, only=None):
    """Join the open pieces of the routed nets. Returns (joined, ripped, open):
    the nets joined, the nets whose tracks were taken up on the way (and
    joined again), the nets left open."""
    board = cu.board
    original = {t.m_Uuid.AsString() for t in board.GetTracks()}
    nets = sorted(n for n in (only or routed) if n not in PLANE_NETS)
    todo = list(nets)
    joined, ripped_nets, left = [], set(), []
    hard = {}                     # net -> times it took up this run's joins
    RIPPED.clear()
    budget = MAX_JOINS * 4        # join attempts (nets already whole cost nothing)
    while todo and budget:
        net = todo.pop(0)
        for _ in range(MAX_JOINS):
            board.BuildConnectivity()
            # pieces without a pad are left-over router copper: nothing to join
            ps = [p for p in pieces(board, net) if any(it.GetClass() == "PAD" for it in p)]
            if len(ps) < 2:
                break
            if not budget:
                todo.insert(0, net)
                break
            budget -= 1
            ps.sort(key=lambda p: (len(p), bbox(p)))
            src, others = ps[0], ps[1:]
            got = None
            got = join(board, cu, net, src, others, sorted({net_class_width(board, net), 0.1}, reverse=True))
            if got is None:
                # rip-up: tracks of other routed nets that were on the board
                # before this run may give way (they are joined again after),
                # never the joins made here, nor this net's own copper
                def rippable(t, net=net):
                    n = t.GetNetname()
                    return (t.GetClass() != "PCB_VIA" and n != net and n in routed and n not in PLANE_NETS
                            and t.m_Uuid.AsString() in original)
                got = join(board, cu, net, src, others, (0.1,), rippable)
                if got is None and hard.get(net, 0) < HARD_TRIES:
                    # last resort, a few times per net: joins made earlier
                    # in this run may give way too (an earlier net's join
                    # can wall this one in; two nets may take turns)
                    hard[net] = hard.get(net, 0) + 1
                    def rippable(t, net=net):
                        n = t.GetNetname()
                        return t.GetClass() != "PCB_VIA" and n != net and n in routed and n not in PLANE_NETS
                    got = join(board, cu, net, src, others, (0.1,), rippable)
                if got:
                    ripped_nets |= got
                    todo += sorted(n for n in got if n not in todo)
            if got is None:
                left.append(net)
                break
            joined.append(net)
    left += todo                  # out of budget: not looked at
    # what is left of a taken-up track no longer reaches a pad: remove it
    board.BuildConnectivity()
    for net in sorted(ripped_nets | set(only or ())):
        for p in pieces(board, net):
            if not any(it.GetClass() == "PAD" for it in p):
                for it in p:
                    remove(board, it)
    return joined, sorted(ripped_nets), left


RULES = {"clearance", "hole_clearance", "hole_to_hole", "copper_edge_clearance", "shorting_items",
         "tracks_crossing"}


def violators(board, report, nets):
    """Remove the tracks and vias of the given signal nets that a DRC report
    (kicad-cli JSON) names in a clearance-type violation. Returns their nets."""
    uu = {it["uuid"] for v in report["violations"] if v["type"] in RULES for it in v["items"]}
    out = set()
    for t in list(board.GetTracks()):
        net = t.GetNetname()
        if net in nets and net not in PLANE_NETS and t.m_Uuid.AsString() in uu:
            out.add(net)
            board.Delete(t)
    return out


def cut(t, conn, d=None):
    """What of t can go, t being a track or via with a loose end (for a
    track, d: that end, from KiCad's test): "all", ("start" | "end",
    point) to shorten a track to point, or None. A via goes when it touches
    at most one item. A track is cut back from d to the contact farthest
    from its other end, so a piece that other tracks end on stays. The
    connectivity gives t's whole cluster; contact is tested here."""
    near = [c.Cast() for c in conn.GetConnectedItems(t)]
    if t.GetClass() == "PCB_VIA":
        r = int(t.GetWidth(pcbnew.F_Cu) / 2)
        near = [c for c in near if c.GetClass() != "ZONE" and c.HitTest(t.GetPosition(), r)
                or c.GetClass() == "PCB_TRACK" and (t.HitTest(c.GetStart(), 0) or t.HitTest(c.GetEnd(), 0))]
        near = [c for c in near if c.m_Uuid != t.m_Uuid]
        if len(near) <= 1:
            return "all"
        # tracks of one layer only, all ending at its centre: they meet
        # there without it
        pos = t.GetPosition()
        if all(c.GetClass() == "PCB_TRACK" and c.GetLayer() == near[0].GetLayer()
               and pos in (c.GetStart(), c.GetEnd()) for c in near):
            return "all"
        # tracks of one layer only, some ending off its centre (within its
        # pad): bridged to the centre on that layer, then the via goes
        if all(c.GetClass() == "PCB_TRACK" and c.GetLayer() == near[0].GetLayer() for c in near):
            ends = []
            for c in near:
                e = min((c.GetStart(), c.GetEnd()), key=lambda q: (q - pos).EuclideanNorm())
                if (e - pos).EuclideanNorm() > r + c.GetWidth() / 2:
                    return None      # touches the via's side, not its pad
                if e != pos:
                    ends.append((e, c.GetWidth(), c.GetLayer()))
            return ("bridge", ends)
        return None
    layer = t.GetLayer()
    a, b = t.GetStart(), t.GetEnd()
    if d is None:
        return None
    if a == b:
        return "all"     # a zero-length track with a loose end carries nothing
    # cut from the loose end d (KiCad's) towards the other end k
    at_b = (d - b).EuclideanNorm() < (d - a).EuclideanNorm()
    k = a if at_b else b
    reach = t.GetWidth() / 2
    hits = []        # contacts: points on t where the net's copper touches it
    for c in near:
        if not c.IsOnLayer(layer) or (c.GetClass() == "PCB_TRACK" and c.m_Uuid == t.m_Uuid):
            continue
        if c.GetClass() == "ZONE":
            hits += [p for p in (a, b) if c.HitTestFilledArea(layer, p)]
            continue
        hits += [p for p in (a, b) if c.HitTest(p, 0)]
        if c.GetClass() == "PCB_TRACK":
            hits += [e for e in (c.GetStart(), c.GetEnd()) if t.HitTest(e, int(c.GetWidth() / 2))]
        elif c.GetClass() == "PCB_VIA" and t.HitTest(c.GetPosition(), int(c.GetWidth(pcbnew.F_Cu) / 2)):
            hits.append(c.GetPosition())
    # the loose end has no contact (KiCad): what lies within reach of it is
    # only near, not joined
    hits = [p for p in hits if (p - d).EuclideanNorm() > reach]
    if not hits:
        return "all"
    far = max(hits, key=lambda p: (p - k).EuclideanNorm())
    if (far - k).EuclideanNorm() <= reach:
        return "all"
    # the new end stays on t's own line (the contact may lie beside it, and
    # moving the end there would turn the track towards other copper)
    ux, uy = b.x - a.x, b.y - a.y
    n2 = ux * ux + uy * uy
    s = min(1.0, max(0.0, ((far.x - a.x) * ux + (far.y - a.y) * uy) / float(n2))) if n2 else 0.0
    end = pcbnew.VECTOR2I(int(round(a.x + s * ux)), int(round(a.y + s * uy)))
    if end == (b if at_b else a):
        return None      # nothing to take off (prune() would repeat it forever)
    return ("end" if at_b else "start", end)


def prune(board, nets):
    """Remove the copper of the given nets that leads nowhere, on the filled
    board: escape stubs and fan-out vias the general routing did not
    continue from (it reached the ball another way), and what that leaves
    (cut()). Returns the number of items removed or shortened."""
    removed = 0
    while True:
        board.BuildConnectivity()
        conn = board.GetConnectivity()
        work = []
        for t in board.GetTracks():
            d = pcbnew.VECTOR2I(0, 0)
            if t.GetNetname() in nets and conn.TestTrackEndpointDangling(t, False, d):
                work.append((t, cut(t, conn, d)))
        work = [(t, w) for t, w in work if w is not None]
        if not work:
            return removed
        for t, w in work:
            if w == "all":
                board.Delete(t)
            elif w[0] == "bridge":
                for e, width, layer in w[1]:
                    b = pcbnew.PCB_TRACK(board)
                    b.SetStart(t.GetPosition())
                    b.SetEnd(e)
                    b.SetWidth(width)
                    b.SetLayer(layer)
                    b.SetNetCode(t.GetNetCode())
                    q = t.GetPosition()
                    stable_id(b, "bridge", t.GetNetname(), layer, (q.x, q.y), (e.x, e.y), width)
                    board.Add(b)
                board.Delete(t)
            elif w[0] == "end":
                t.SetEnd(w[1])
            else:
                t.SetStart(w[1])
        removed += len(work)


def region_sink(test):
    """sink(x, y) for a plane not poured yet: a via on the SINK_PITCH
    lattice whose pad and surroundings all pass test(x, y)."""
    # the via's pad, 0.3 mm to the card edge (rules.py) and the plane's edge
    r = VIA_D / 2 + 0.3
    offs = [(0, 0), (r, 0), (-r, 0), (0, r), (0, -r)]
    cache = {}

    def sink(x, y):
        k = (round(x / SINK_PITCH, 6), round(y / SINK_PITCH, 6))
        if k[0] != int(k[0]) or k[1] != int(k[1]):
            return False
        if k not in cache:
            cache[k] = all(test(x + a, y + b) for a, b in offs)
        return cache[k]
    return sink


def early(cu, pins, plane_at):
    """Before the general routing: join the plane pins that have no via into
    their plane (planes.py found no room beside the pad; FX3 supply balls
    whose fan-out via had to go where that plane is not) with a track to a
    via where the net's plane will be (plane_at(net, x, y)) or to the net's
    other pads, so that Freerouting routes around them instead of boxing
    them in. pins: "REF.PAD" names. Returns (joined, open)."""
    board = cu.board
    joined, left = [], []
    for name in pins:
        ref, num = name.split(".", 1)
        pad = next(p for p in cu.fps[ref].Pads() if p.GetNumber() == num)
        net = pad.GetNetname()
        sink = region_sink(lambda x, y, net=net: plane_at(net, x, y))
        # or to the net's other pads and their copper (each has its via)
        board.BuildConnectivity()
        uid = pad.m_Uuid.AsString()
        others = [p for p in pieces(board, net)
                  if any(it.GetClass() == "PAD" for it in p) and all(it.m_Uuid.AsString() != uid for it in p)]
        got = join(board, cu, net, [pad], others, (0.3, 0.1), sink=sink, margins=PLANE_MARGINS)
        (left if got is None else joined).append(name)
    return joined, left


def planes(cu, routed=()):
    """Join the plane-net pads that reach no plane (no room for a via beside
    them, planes.py, or no plane under them: the card-edge fingers, the
    USB-C) with a track to a via in the plane or to connected copper. Run
    on the filled board; refill afterwards. Returns (joined, open)."""
    board = cu.board
    joined, left = [], []
    for net in PLANE_NETS:
        sink = plane_sink(board, net)
        failed = set()
        for _ in range(MAX_JOINS * 4):
            board.BuildConnectivity()
            ps = [p for p in pieces(board, net) if any(it.GetClass() == "PAD" for it in p)]
            has_zone = [any(it.GetClass() == "ZONE" for it in p) for p in ps]
            planed = [p for p, z in zip(ps, has_zone) if z]
            loose = [p for p, z in zip(ps, has_zone)
                     if not z and min(it.m_Uuid.AsString() for it in p) not in failed]
            if not loose:
                break
            loose.sort(key=bbox)
            src = loose[0]
            name = " ".join(sorted(f"{it.GetParentFootprint().GetReference()}.{it.GetNumber()}"
                                   for it in src if it.GetClass() == "PAD"))
            got = None
            got = join(board, cu, net, src, planed, (0.3, 0.1), sink=sink, margins=PLANE_MARGINS)
            keep = set()
            for _ in range(3 if routed else 0):
                if got is not None:
                    break
                # rip-up as in finish(): signal tracks may give way and are
                # joined again below; plane-net copper never does
                def rippable(t, keep=keep):
                    n = t.GetNetname()
                    return (t.GetClass() != "PCB_VIA" and n in routed and n not in PLANE_NETS
                            and n not in keep)
                # the taken-up nets are joined again at once; if one of them
                # stays open, the whole attempt is undone and tried again with
                # that net kept in place (the pin may find another way)
                global TAKEN
                before = {t.m_Uuid.AsString() for t in board.GetTracks()}
                TAKEN = []
                got = join(board, cu, net, src, planed, (0.1,), rippable, sink=sink, margins=PLANE_MARGINS)
                if got is None:
                    TAKEN = None
                    break                      # no way even with rip-up
                l = []
                if got:
                    j, _, l = finish(cu, routed, got)
                    if l:
                        undo(board, before, TAKEN)
                        keep |= set(l)
                        got = None
                    else:
                        joined += j
                TAKEN = None
            if got is None:
                failed.add(min(it.m_Uuid.AsString() for it in src))
                left.append(f"{net}:{name}")
            else:
                joined.append(f"{net}:{name}")
        # separate islands of the same plane net (the +3V3 areas either side
        # of the switching supply, D-71): join the nearest pads of each
        # smaller island to the largest, with a supply track
        for _ in range(MAX_JOINS):
            board.BuildConnectivity()
            ps = [p for p in pieces(board, net) if any(it.GetClass() == "ZONE" for it in p)]
            if len(ps) < 2:
                break
            ps.sort(key=lambda p: -len(p))
            pads = [[it for it in p if it.GetClass() == "PAD"] for p in ps]
            small = pads[-1]
            rest = [q for qs in pads[:-1] for q in qs]
            sp = [(T(a.GetPosition().x), T(a.GetPosition().y)) for a in small]
            rp = [(T(b.GetPosition().x), T(b.GetPosition().y)) for b in rest]
            pairs = sorted((math.hypot(a[0] - b[0], a[1] - b[1]), k, m)
                           for k, a in enumerate(sp) for m, b in enumerate(rp))
            got = None
            for _, k, m in pairs[:5]:
                got = join(board, cu, net, [small[k]], [[rest[m]]], (0.3, 0.1))
                if got is not None:
                    break
            a = small[0]
            name = f"{a.GetParentFootprint().GetReference()}.{a.GetNumber()}"
            if got is None:
                left.append(f"{net}:island {name}")
                break
            joined.append(f"{net}:island {name}")
    return joined, left
