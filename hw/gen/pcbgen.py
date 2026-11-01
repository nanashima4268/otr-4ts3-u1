# SPDX-License-Identifier: CERN-OHL-S-2.0
"""PCB generator for OTR-4TS3-U1 (D-51): outline, footprints with nets and
schematic links, provisional placement from layout.py.

Run with KiCad's Python (it needs the pcbnew module):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 hw/gen/pcbgen.py

The footprints carry the schematic's symbol paths (schgen.stable_uuid), so
KiCad's "Update PCB from Schematic" and the DRC parity check work. This
first version writes a fresh board (placement only, no copper yet).
"""
import os
import sys

import pcbnew

import design
import layout as L
from schgen import KICAD_SHARE
from sexp import parse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "kicad", design.PROJECT + ".kicad_pcb")
MM = pcbnew.FromMM


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
    if not part.ref.startswith(("J", "H")):    # dense board: references on the fab layer
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


# ---------------------------------------------------------------- board
def setup(board):
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(MM(1.6))
    # JLCPCB 4-layer capabilities (refined at the routing stage)
    ds.m_TrackMinWidth = MM(0.1)
    ds.m_MinClearance = MM(0.1)
    ds.m_ViasMinSize = MM(0.45)
    ds.m_MinThroughDrill = MM(0.3)
    ds.m_CopperEdgeClearance = MM(0.3)
    ds.m_HoleClearance = MM(0.2)


def build():
    for f in (design.fx3_sheet, design.fpga_sheet, design.power_sheet, design.usb_sheet,
              design.control_sheet, design.rf_sheet):
        f()
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
    # fixed parts
    blocked = []
    for ref, (x, y, rot, side) in L.FIXED.items():
        place(fps[ref], x, y, rot, side)
        if ref != "J1":
            blocked.append(bbox(fps[ref]))
    for (hx, hy) in L.HOLES:
        r = L.SCREW_HEAD_R
        blocked.append((hx - r, hy - r, hx + r, hy + r))
        screw_head(board, hx, hy, r)
    # everything else, packed per group
    zone_of = {"fx3": "fx3", "fpga": "fpga", "power": "power", "usb": "usb", "control": "control",
               "rf_S": "rf_S", "rf_T": "rf_T"}
    failed = []
    for g, zone in zone_of.items():
        members = [fp for ref, fp in fps.items() if groups[ref] == g and ref not in L.FIXED]
        failed += pack(members, L.ZONES[zone], blocked)
    reservations(board)
    board.Save(OUT)
    return board, failed


if __name__ == "__main__":
    board, failed = build()
    print("wrote", os.path.relpath(OUT))
    print("footprints:", len(board.GetFootprints()))
    if failed:
        print("did not fit:", " ".join(failed))
        sys.exit(1)
