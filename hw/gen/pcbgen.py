# SPDX-License-Identifier: CERN-OHL-S-2.0
"""PCB generator for OTR-4TS3-U1 (D-51): outline, footprints with nets and
schematic links, provisional placement from layout.py.

Run with KiCad's Python (it needs the pcbnew module):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 hw/gen/pcbgen.py

The footprints carry the schematic's symbol paths (schgen.stable_uuid), so
KiCad's "Update PCB from Schematic" and the DRC parity check work. This
first version writes a fresh board (placement only, no copper yet).
"""
import math
import os
import re
import sys

import pcbnew

import design
import layout as L
import rules
import usb
import fanout
import escape
import finish
import planes
import autoroute
from route import Copper, stable_id
from schgen import KICAD_SHARE
from sexp import parse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "kicad", design.PROJECT + ".kicad_pcb")
MM = pcbnew.FromMM


MODEL_OVERRIDE = {
}


def P(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


def fp_lib_path(nick):
    if nick == "otr":
        return os.path.join(HERE, "..", "lib", "otr.pretty")
    return os.path.join(KICAD_SHARE, "footprints", nick + ".pretty")


# ---------------------------------------------------------------- drawing
def line(board, a, b, layer=pcbnew.Edge_Cuts, w=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(*a))
    s.SetEnd(P(*b))
    s.SetLayer(layer)
    s.SetWidth(MM(w))
    board.Add(s)


def rect(board, x0, y0, x1, y1, layer, w=0.1):
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        line(board, a, b, layer, w)


def text(board, s, x, y, layer, size=1.0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(P(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(size * 0.15))
    if layer in (pcbnew.B_Fab, pcbnew.B_SilkS):
        t.SetMirrored(True)
    board.Add(t)


def outline(board):
    """Card outline; the PCIe footprint draws the finger part itself."""
    pts = [(L.FINGER_R, L.FINGER_TOP_Y), (L.FINGER_R, L.SHOULDER_Y), (L.FAR_X, L.SHOULDER_Y),
           (L.FAR_X, L.TOP_Y), (L.BRACKET_X, L.TOP_Y), (L.BRACKET_X, L.TAB_Y), (L.TAB_X, L.TAB_Y),
           (L.TAB_X, L.SHOULDER_Y), (L.FINGER_L, L.SHOULDER_Y), (L.FINGER_L, L.FINGER_TOP_Y)]
    for a, b in zip(pts, pts[1:]):
        line(board, a, b)


def screw_head(board, x, y, r):
    """Screw head outline on the component side (packing keeps parts out)."""
    c = pcbnew.PCB_SHAPE(board)
    c.SetShape(pcbnew.SHAPE_T_CIRCLE)
    c.SetCenter(P(x, y))
    c.SetEnd(P(x + r, y))
    c.SetLayer(pcbnew.Dwgs_User)
    c.SetWidth(MM(0.1))
    board.Add(c)


def reservations(board):
    x0, y0, x1, y1 = L.RX_BAND
    w = (x1 - x0) / L.RX_COUNT
    for i in range(L.RX_COUNT):
        rect(board, x0 + i * w + 0.3, y0, x0 + (i + 1) * w - 0.3, y1, pcbnew.Dwgs_User, 0.15)
        text(board, f"RX{i}", x0 + (i + 0.5) * w, y0 + 4, pcbnew.Dwgs_User, 1.5)
        text(board, "CXD2858ER + CXD2856ER", x0 + (i + 0.5) * w, y0 + 7, pcbnew.Dwgs_User, 0.8)
        text(board, "(after measurement)", x0 + (i + 0.5) * w, y0 + 9, pcbnew.Dwgs_User, 0.8)
    cw, ch = L.BCAS_CARD
    bx1 = L.FAR_X + 2.0                       # the card may stick out at the far end
    by0 = L.TOP_Y + (L.SHOULDER_Y - L.TOP_Y - ch) / 2
    rect(board, bx1 - cw, by0, bx1, by0 + ch, pcbnew.B_Fab, 0.15)
    text(board, "B-CAS full-size card (DNP slot, solder side)", bx1 - cw / 2, by0 + ch / 2, pcbnew.B_Fab, 1.2)
    for (zx0, zy0, zx1, zy1) in L.ZONES.values():
        rect(board, zx0, zy0, zx1, zy1, pcbnew.Cmts_User, 0.05)


# ---------------------------------------------------------------- footprints
def kicad_pad_nets():
    """(ref, pad) -> net name, from the netlist KiCad exported for the
    schematic (written and checked by design.py). Taking the names from KiCad
    includes its "unconnected-(...)" nets for no-connect pins."""
    path = os.path.join(HERE, "..", "kicad", design.PROJECT + ".net")
    tree = parse(open(path).read())[0]
    nets_sec = next(e for e in tree if isinstance(e, list) and e and e[0] == "nets")
    out = {}
    for net in nets_sec[1:]:
        name = next(e[1] for e in net if isinstance(e, list) and e[0] == "name")
        for node in net:
            if isinstance(node, list) and node[0] == "node":
                f = {e[0]: e[1] for e in node[1:] if isinstance(e, list)}
                out[(str(f["ref"]), str(f["pin"]))] = str(name)
    return out


def owner_groups():
    """Group each part for packing: its sheet, with the RF sheet split into
    the satellite and terrestrial chains by connectivity."""
    groups = {}
    for s in design.d.sheets:
        for p in s.parts:
            groups[p.ref] = s.name
    rf = [p for s in design.d.sheets if s.name == "rf" for p in s.parts]
    by_net = {}
    for p in rf:
        for net in p.nets.values():
            by_net.setdefault(net, []).append(p.ref)
    big = {n for n, refs in by_net.items()
           if len(refs) > 6 or n in ("GND", "NC") or n.startswith(("+", "LNA_BYPASS"))}
    adj = {p.ref: set() for p in rf}
    for n, refs in by_net.items():
        if n in big:
            continue
        for r in refs:
            adj[r].update(refs)
    # multi-source BFS: each part joins the chain of the nearer F jack
    frontier = [("J6", "rf_S"), ("J5", "rf_T")]
    seen = {"J6", "J5"}
    while frontier:
        nxt = []
        for r, band in frontier:
            groups[r] = band
            for n in sorted(adj[r] - seen):
                seen.add(n)
                nxt.append((n, band))
        frontier = nxt
    # internal-header-only parts (AC caps, VBUS link) sit next to J4, not at the bracket
    for s_ in design.d.sheets:
        if s_.name == "usb":
            for p in s_.parts:
                ns = {n for n in p.nets.values() if n not in ("GND", "NC")}
                if ns and p.ref != "J4" and all(n.startswith("HDR_") or n == "VBUS" for n in ns) \
                        and any(n.startswith("HDR_") for n in ns):
                    groups[p.ref] = "usb_hdr"
    # point-of-load LDOs (AN70707: short supply paths) sit with their load, with
    # their input and output caps (the parts either side of them on the sheet)
    for s_ in design.d.sheets:
        if s_.name == "power":
            for i, p in enumerate(s_.parts):
                load = LDO_LOAD.get(p.nets.get("5")) if p.value.startswith("TLV755") else None
                if load:
                    cin, cout = s_.parts[i - 1], s_.parts[i + 1]
                    for q in (cin, p, cout):
                        groups[q.ref] = load
                    LDO_CAPS[cin.ref] = (p.ref, "+3V3")
                    LDO_CAPS[cout.ref] = (p.ref, p.nets["5"])
    for p in rf:                              # anything unreached (e.g. shared bias) -> T side
        if groups[p.ref] == "rf":
            groups[p.ref] = "rf_T"
    return groups


def make_footprint(board, nets, pad_nets, sheet, part):
    nick, name = part.footprint.split(":")
    fp = pcbnew.FootprintLoad(fp_lib_path(nick), name)
    if fp is None:
        raise RuntimeError(f"{part.ref}: footprint {part.footprint} not found")
    fp.SetParent(board)
    if part.ref in MODEL_OVERRIDE:                 # no usable model in the KiCad library
        models = fp.Models()
        models.clear()
        m = pcbnew.FP_3DMODEL()
        m.m_Filename = MODEL_OVERRIDE[part.ref]
        models.append(m)
    fp.SetReference(part.ref)
    fp.SetValue(part.value)
    fp.SetFPIDAsString(part.footprint) if hasattr(fp, "SetFPIDAsString") else None
    fp.SetPath(pcbnew.KIID_PATH(design.d.footprint_path(sheet, part.ref)))
    if part.dnp:
        fp.SetDNP(True)
        fp.SetExcludedFromBOM(True)
        fp.SetExcludedFromPosFiles(True)
    if part.lcsc:
        f = pcbnew.PCB_FIELD(fp, pcbnew.FIELD_T_USER, "LCSC") if hasattr(pcbnew, "FIELD_T_USER") else None
        if f is not None:
            f.SetText(part.lcsc)
            f.SetVisible(False)
            fp.Add(f)
    if not re.match(r"^(J|H)\d", part.ref) or part.ref in ("J3", "J5", "J6"):   # dense board: references on the fab layer
        fp.Reference().SetLayer(pcbnew.F_Fab)
    fp.SetExcludedFromBOM(part.dnp)           # same as the symbol (schgen: in_bom = not dnp)
    for pad in fp.Pads():
        num = pad.GetNumber()
        net = pad_nets.get((part.ref, num))
        if net is not None:
            if net not in nets:
                nets[net] = pcbnew.NETINFO_ITEM(board, net)
                board.Add(nets[net])
            pad.SetNet(nets[net])
        elif num and pad.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH and part.nets.get(num) != "NC":
            print(f"  warning: {part.ref} pad {num} is not in the netlist")
    board.Add(fp)
    return fp


def bbox(fp):
    """Courtyard extent (falls back to the footprint body)."""
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    if cy.OutlineCount() > 0:
        b = cy.BBox()
        return (pcbnew.ToMM(b.GetLeft()), pcbnew.ToMM(b.GetTop()),
                pcbnew.ToMM(b.GetRight()), pcbnew.ToMM(b.GetBottom()))
    b = fp.GetBoundingBox(False)
    return (pcbnew.ToMM(b.GetLeft()), pcbnew.ToMM(b.GetTop()),
            pcbnew.ToMM(b.GetRight()), pcbnew.ToMM(b.GetBottom()))


def place(fp, x, y, rot, side="F"):
    if side == "B" and not fp.IsFlipped():
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(P(x, y))


def overlaps(a, b, gap=0.2):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def pack(fps, zone, blocked, gap=0.25):
    """Shelf packing inside zone, avoiding blocked rectangles; largest first.
    Each part is tried at 0 and 90 degrees at every position."""
    x0, y0, x1, y1 = zone
    def size(fp):
        b = bbox(fp)
        return b[2] - b[0], b[3] - b[1]
    order = sorted(fps, key=lambda f: (-(size(f)[0] * size(f)[1]), f.GetReference()))

    def scan(w, h):
        y = y0
        while y + h <= y1 + 1e-6:
            x = x0
            while x + w <= x1 + 1e-6:
                cand = (x, y, x + w, y + h)
                hit = next((b for b in blocked if overlaps(cand, b, gap)), None)
                if hit is None:
                    return x, y
                x = max(x + 0.1, hit[2] + gap)
            y += 0.1
        return None

    failed = []
    for fp in order:
        best = None
        for rot in (0, 90):
            fp.SetOrientationDegrees(rot)
            w, h = size(fp)
            pos = scan(w, h)
            if pos and (best is None or (pos[1], pos[0]) < (best[1][1], best[1][0])):
                best = (rot, pos)
        if best is None:
            fp.SetOrientationDegrees(0)
            failed.append(fp.GetReference())
            continue
        rot, (x, y) = best
        fp.SetOrientationDegrees(rot)
        b = bbox(fp)
        p = fp.GetPosition()
        fp.SetPosition(P(x + pcbnew.ToMM(p.x) - b[0], y + pcbnew.ToMM(p.y) - b[1]))
        blocked.append(bbox(fp))
    return failed


# ---------------------------------------------------------------- affinity placement
OWNER_IC = {"fx3": "U1", "fpga": "U3"}
LDO_CAPS = {}     # cap ref -> (LDO ref, net): the cap sits at that LDO pin
LDO_LOAD = {"+1V2": "fx3", "+1V2_FPGA": "fpga"}   # D-71
RAIL_MIN = 9               # nets with this many pads or more count as rails


def pad_xy(pad):
    p = pad.GetPosition()
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


class Affinity:
    """Places each part next to the pads it connects to (decoupling caps
    spread over the IC's supply pins, signal parts at their pin), searching
    outwards from the target for the nearest free spot inside the zone."""

    def __init__(self, fps, groups, blocked, gap=0.1):
        self.fps, self.groups, self.blocked, self.gap = fps, groups, blocked, gap
        self.placed = set()
        self.members = {}
        for ref, fp in fps.items():
            for pad in fp.Pads():
                n = pad.GetNetname()
                if n and not n.startswith("unconnected"):
                    self.members.setdefault(n, []).append((ref, pad))
        self.used_pads = {}          # (ref, pad number) -> count of caps aimed at it

    def is_rail(self, net):
        return net == "GND" or net.startswith("+") or len(self.members.get(net, [])) >= RAIL_MIN

    def nets(self, ref):
        # sorted: a set's order follows the per-run string hash seed
        return sorted({p.GetNetname() for p in self.fps[ref].Pads()
                       if p.GetNetname() and p.GetNetname() != "GND" and not p.GetNetname().startswith("unconnected")})

    def target(self, ref):
        """(x, y, net) the part should sit next to, or None if nothing placed yet."""
        if ref in LDO_CAPS:
            ldo, net = LDO_CAPS[ref]
            if ldo not in self.placed:
                return None
            pad = next(p for p in self.fps[ldo].Pads() if p.GetNetname() == net)
            x, y = pad_xy(pad)
            return x, y, net
        sig = [n for n in self.nets(ref) if not self.is_rail(n)]
        pts = [(pad_xy(pad), n) for n in sig for (r, pad) in self.members[n]
               if r != ref and r in self.placed]
        if pts:
            x = sum(p[0][0] for p in pts) / len(pts)
            y = sum(p[0][1] for p in pts) / len(pts)
            return x, y, pts[0][1]
        rails = [n for n in self.nets(ref) if self.is_rail(n)]
        owner = OWNER_IC.get(self.groups[ref])
        for n in rails:
            cands = [pad for (r, pad) in self.members[n] if r == owner] if owner else []
            if not cands:          # nearest placed IC of the same group on this rail
                cands = [pad for (r, pad) in self.members[n]
                         if r in self.placed and r.startswith("U") and self.groups.get(r) == self.groups[ref]]
            if cands:
                # the supply pin with the fewest caps so far, farthest from the ones already used
                used = [pad_xy(p) for (r, p) in self.members[n] if self.used_pads.get((r, p.GetNumber()))]
                def score(pad):
                    x, y = pad_xy(pad)
                    d = min(((x - u[0]) ** 2 + (y - u[1]) ** 2 for u in used), default=1e9)
                    return (self.used_pads.get((owner, pad.GetNumber()), 0), -d)
                pad = min(cands, key=score)
                key = (pad.GetParentFootprint().GetReference(), pad.GetNumber())
                self.used_pads[key] = self.used_pads.get(key, 0) + 1
                x, y = pad_xy(pad)
                return x, y, n
        return None

    def put(self, ref, tx, ty, net, zone, rots=(0, 90, 180, 270)):
        fp = self.fps[ref]
        shapes = []
        for rot in rots:
            fp.SetOrientationDegrees(rot)
            fp.SetPosition(P(0, 0))
            b = bbox(fp)
            near = [pad_xy(p) for p in fp.Pads() if p.GetNetname() == net] or [(0.0, 0.0)]
            shapes.append((rot, b, near[0]))
        x0, y0, x1, y1 = zone
        # every candidate box of a ring lies in this reach around the target
        lo_x = min(b[0] - px for _, b, (px, py) in shapes)
        lo_y = min(b[1] - py for _, b, (px, py) in shapes)
        hi_x = max(b[2] - px for _, b, (px, py) in shapes)
        hi_y = max(b[3] - py for _, b, (px, py) in shapes)
        step, r = 0.2, 0.0
        while r < 150:
            n = max(1, int(2 * math.pi * r / step))
            best = None
            rr = r + 1e-6
            ring = (tx - rr + lo_x, ty - rr + lo_y, tx + rr + hi_x, ty + rr + hi_y)
            near = [o for o in self.blocked if overlaps(ring, o, self.gap)]
            for i in range(n):
                a = 2 * math.pi * i / n
                cx, cy = tx + r * math.cos(a), ty + r * math.sin(a)
                for rot, b, (px, py) in shapes:
                    # put the connecting pad on the candidate point
                    ox, oy = cx - px, cy - py
                    box = (b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy)
                    if box[0] < x0 or box[1] < y0 or box[2] > x1 or box[3] > y1:
                        continue
                    if any(overlaps(box, o, self.gap) for o in near):
                        continue
                    best = (rot, ox, oy, box)
                    break
                if best:
                    break
            if best:
                rot, ox, oy, box = best
                fp.SetOrientationDegrees(rot)
                fp.SetPosition(P(ox, oy))
                self.blocked.append(box)
                self.placed.add(ref)
                return True
            r += step if r < 10 else 1.0
        fp.SetOrientationDegrees(0)
        return False


def priority(ref, fp):
    """ICs first, then 100 nF caps, then the other passives, then LEDs and test pads."""
    v = fp.GetValue()
    if ref.startswith("U"):
        return 0
    if ref.startswith("Y"):
        return 1
    if ref.startswith("C") and v in ("100nF", "100n"):
        return 2
    if ref.startswith(("C", "R", "FB", "L", "X")):
        return 3
    return 4


KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"


def fill(path):
    """Fill the zones with KiCad's own filler under the project rules
    (pcbnew's Python filler does not see the .kicad_dru written after save)."""
    import subprocess
    import tempfile
    cli = os.environ.get("KICAD_CLI", KICAD_CLI)
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([cli, "pcb", "drc", "--refill-zones", "--save-board", "-o", os.path.join(d, "drc.rpt"), path],
                       check=True, capture_output=True)


def stabilize(board):
    """Name-based uuids for everything pcbnew created with random ones
    (footprints and their children, drawings), so the file is byte-stable."""
    T = pcbnew.ToMM
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        stable_id(fp, "fp", ref)
        for p in fp.Pads():
            stable_id(p, "pad", ref, p.GetNumber())
        for f in fp.GetFields():
            stable_id(f, "field", ref, f.GetName())
        for g in fp.GraphicalItems():
            bb = g.GetBoundingBox()
            stable_id(g, "fpg", ref, g.GetClass(), g.GetLayer(), bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())
        for z in fp.Zones():
            stable_id(z, "fpz", ref, z.GetLayerSet().FmtHex())
    for d in board.GetDrawings():
        bb = d.GetBoundingBox()
        extra = d.GetText() if hasattr(d, "GetText") else ""
        stable_id(d, "drw", d.GetClass(), d.GetLayer(), bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom(), extra)
    for z in board.Zones():
        stable_id(z, "zone", z.GetNetname(), z.GetLayerSet().FmtHex(), z.GetAssignedPriority(),
                  z.GetBoundingBox().GetLeft(), z.GetBoundingBox().GetTop())


def pads_outside(board):
    """Every copper pad must lie on the card (KiCad's DRC does not flag a pad
    that is entirely outside the outline)."""
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    bad = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            if not outline.Contains(p.GetPosition()):
                bad.append(f"{fp.GetReference()}.{p.GetNumber()}(outside the card)")
    return bad


# ---------------------------------------------------------------- board
def setup(board):
    board.SetCopperLayerCount(6)       # JLC06161H-7628 (D-75)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(MM(1.6))
    # JLCPCB 6-layer capabilities (refined at the routing stage)
    ds.m_TrackMinWidth = MM(0.1)
    ds.m_MinClearance = MM(0.1)
    ds.m_ViasMinSize = MM(0.45)
    ds.m_MinThroughDrill = MM(0.3)
    ds.m_CopperEdgeClearance = MM(0.3)
    ds.m_HoleClearance = MM(0.2)


def build():
    design.build_sheets()
    board = pcbnew.NewBoard(OUT)
    setup(board)
    nets = {}
    pad_nets = kicad_pad_nets()
    outline(board)
    groups = owner_groups()
    fps = {}
    for s in design.d.sheets:
        for p in s.parts:
            if p.ref.startswith("#") or not p.footprint:
                continue
            fps[p.ref] = make_footprint(board, nets, pad_nets, s.name, p)
    # fixed parts (the USB chain is placed by usb.py)
    blocked = []
    usb_refs = usb.place(fps)
    for ref in usb_refs:
        blocked.append(bbox(fps[ref]))
    blocked += usb.KEEP
    for ref, (x, y, rot, side) in L.FIXED.items():
        place(fps[ref], x, y, rot, side)
        if ref != "J1":
            blocked.append(bbox(fps[ref]))
    blocked += fanout.keepouts(fps)
    for (hx, hy) in L.HOLES:
        r = L.SCREW_HEAD_R
        blocked.append((hx - r, hy - r, hx + r, hy + r))
        screw_head(board, hx, hy, r)
    # placed parts of other groups are anchors too
    aff = Affinity(fps, groups, blocked)
    aff.placed.update(L.FIXED)
    aff.placed.update(usb_refs)
    zone_of = {g: g for g in L.ZONES}
    failed = []
    # big parts that are not fixed: packed in their zone, in sheet order
    for g in zone_of:
        majors = [fp for ref, fp in fps.items() if groups[ref] == g and ref not in L.FIXED and ref not in usb_refs
                  and ref in L.PACKED_MAJORS]
        failed += pack(majors, L.ZONES[g], blocked)
        aff.placed.update(fp.GetReference() for fp in majors)
    # the rest by affinity; parts whose neighbours are not placed yet wait a round
    todo = sorted((ref for ref in fps if ref not in aff.placed),
                  key=lambda r: (priority(r, fps[r]), r))
    for ref, where in L.TARGET_OVERRIDE(fps):
        if ref in todo:
            todo.remove(ref)
            x, y, net = where()
            if aff.put(ref, x, y, net, L.ZONES[groups[ref]]):
                aff.placed.add(ref)
            else:
                failed.append(ref)
    while todo:
        progress = False
        for ref in list(todo):
            t = aff.target(ref)
            if t is None:
                continue
            todo.remove(ref)
            progress = True
            if not aff.put(ref, t[0], t[1], t[2], L.ZONES[groups[ref]]):
                spill = L.SPILL.get(groups[ref])
                if not (spill and ref.startswith("TP") and aff.put(ref, t[0], t[1], t[2], L.ZONES[spill])):
                    failed.append(ref)
        if not progress:           # nothing to aim at: start from the zone centre
            ref = todo.pop(0)
            z = L.ZONES[groups[ref]]
            if not aff.put(ref, (z[0] + z[2]) / 2, (z[1] + z[3]) / 2, None, z):
                failed.append(ref)
    lens = usb.route(Copper(board))
    print("usb pair lengths (N, P):", {k: (round(a, 2), round(b, 2)) for k, (a, b) in lens.items()})
    made, fo_failed, fo_top = fanout.fanout(Copper(board))
    print(f"fan-out: {len(made)} balls, no room {fo_failed}, outer supply left to top routing {fo_top}")
    failed += [f"U1.{b}" for b in fo_failed]
    stubs, esc_failed = escape.escape(Copper(board), made)
    print(f"BGA escape: {len(stubs)} stubs, no way out {esc_failed}")
    pv, pv_missed = planes.build(Copper(board))
    print(f"plane vias: {pv}, no room: {pv_missed}")
    # general routing: the Freerouting session kept beside the board (autoroute.py, D-74)
    base = os.path.splitext(OUT)[0]
    routed = set()
    if os.path.exists(base + ".ses") and os.path.exists(base + ".routed"):
        routed = set(open(base + ".routed").read().split())
        nt, nv = autoroute.apply_ses(board, base + ".ses", routed)
        print(f"autoroute session: {nt} tracks, {nv} vias")
        # what the router left open (D-77)
        joined, ripped, left = finish.finish(Copper(board), routed)
        print(f"finishing: joined {joined}, taken up and joined again {ripped}, still open {left}")
    reservations(board)
    failed += pads_outside(board)
    stabilize(board)
    board.Save(OUT)
    base = os.path.splitext(OUT)[0]
    rules.apply(base + ".kicad_pro", base + ".kicad_dru")
    fill(OUT)
    if routed:
        # plane pins that reach no plane yet: joined on the filled board, then
        # filled again (D-77)
        board = pcbnew.LoadBoard(OUT)
        joined, left = finish.planes(Copper(board), routed)
        print(f"plane finishing: joined {len(joined)}, still open {left}")
        board.Save(OUT)
        # Save() writes the project file back from the loaded settings
        rules.apply(base + ".kicad_pro", base + ".kicad_dru")
        fill(OUT)
    return board, failed


if __name__ == "__main__":
    board, failed = build()
    print("wrote", os.path.relpath(OUT))
    print("footprints:", len(board.GetFootprints()))
    if failed:
        print("did not fit:", " ".join(failed))
        sys.exit(1)
