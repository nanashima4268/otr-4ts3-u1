# SPDX-License-Identifier: CERN-OHL-S-2.0
"""General routing with Freerouting (D-51, D-74).

Run with KiCad's bundled python3 after pcbgen.py:
    autoroute.py [--passes N]

1. The board from pcbgen.py (scripted USB, fan-out and plane vias) is
   exported as a Specctra DSN with every existing track and via fixed.
2. The DSN is adjusted for Freerouting (dsn_patch):
   - signals only on the outer layers; In1/In2 stay planes;
   - the planes are taken out and their nets (PLANES) are not routed: every
     plane pin already has its via (planes.py);
   - RF (75 ohm, hand-routed later) and USB (90 ohm pairs, usb.py) are not
     routed;
   - signal tracks 0.1 mm with 0.1 mm clearance: the gaps between the
     0.8 mm-pitch BGA fan-out vias are 0.35 mm (0.8 - 0.45), and 0.15 mm
     tracks with 0.1 mm clearance need exactly that, so nothing could leave
     the FX3;
   - supply tracks 0.3 mm;
   - the receiver channels (layout.RX_BAND) are kept out;
   - the In1 cut-outs under the USB AC caps (pour-only rule areas) are
     dropped: the DSN would make them via keep-outs.
3. Freerouting (headless, analytics off) writes a Specctra session (SES).
   The session is kept in the repository (hw/kicad/<name>.ses): pcbgen.py
   applies it (apply_ses), so the board is rebuilt without running the
   router again.

apply_ses() adds only the session's wiring that is not already on the board,
and only for nets the router was asked to route, so the scripted copper is
never replaced (KiCad's own SES import deletes every track first).
"""
import math
import os
import re
import subprocess
import sys
import tempfile

import pcbnew

import layout as L
from route import Copper

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD_DIR = os.path.join(HERE, "..", "kicad")
JAR = os.environ.get("FREEROUTING_JAR", os.path.expanduser("~/otr-data/work/tools/freerouting-2.5.0.jar"))

PLANE_NETS = ["GND", "+3V3", "+1V2", "+1V2_FPGA"]
NOT_ROUTED = ["RF_75", "USB_90", "PLANES"]
SIGNAL_W, SIGNAL_CLR = 0.1, 0.1
POWER_W = 0.3
MIN_W = 0.09                   # JLC minimum track (rules.py)
NPTH_CLR = 0.2                 # USB-C locating holes (rules.py)
EDGE_CLR = 0.3                 # copper to card edge (rules.py)
WIDE_VIA, WIDE_VIA_D = "Via_route_550:300_um", 0.55
BGA_BOX = (81.5, 121.5, 92.5, 132.5)   # FX3 courtyard: fan-out vias keep their real size


def um(v):
    return int(round(v * 1000))


def keepout(layer, x0, y0, x1, y1):
    # DSN coordinates: micrometres, y up
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    return f'    (keepout "" (polygon {layer} 0 ' + " ".join(f"{um(x)} {-um(y)}" for x, y in pts) + "))\n"


def strip(layer, a, b, half):
    """Keep-out band of half-width `half` along the segment a-b."""
    (x0, y0), (x1, y1) = a, b
    d = math.hypot(x1 - x0, y1 - y0)
    if d == 0:
        return ""
    nx, ny = -(y1 - y0) / d * half, (x1 - x0) / d * half
    pts = [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny), (x0 + nx, y0 + ny)]
    return f'    (keepout "" (polygon {layer} 0 ' + " ".join(f"{um(x)} {-um(y)}" for x, y in pts) + "))\n"


def dsn_patch(s):
    # planes out
    s = re.sub(r"\n\s*\(plane [^\n]*(\n\s+[-\d. ]+)*\)\)", "", s)
    # pour-only rule areas on the inner layers would be via keep-outs
    s = re.sub(r'\n\s*\(keepout "" \(polygon In[12]\.Cu[^\n]*(\n\s+[-\d. ]+)*\)\)', "", s)
    # USB-C locating holes: 0.2 mm to copper (rules.py) instead of the class clearance
    s = re.sub(r'\(keepout "" \(circle ([^ ]+) (\d+) ', lambda m: f'(keepout "" (circle {m.group(1)} '
               f'{int(m.group(2)) + 2 * (um(NPTH_CLR) - um(SIGNAL_CLR))} ', s)
    # the USB-C's oval locating hole (+3.725 mm) is not exported as a keep-out
    s = re.sub(r'(\n(\s*)\(keepout "" \(circle B\.Cu (\d+) -3725 0\)\))',
               lambda m: m.group(1) + "".join(f'\n{m.group(2)}(keepout "" (circle {l} {int(m.group(3)) + 300} 3725 0))'
                                             for l in ("F.Cu", "B.Cu")), s)
    # vias: copper 0.45 mm on the board, drawn 0.55 mm for the router so that
    # 0.1 mm copper clearance keeps 0.2 mm from the hole (JLC, rules.py);
    # the fan-out vias under the FX3 keep their size (BGA rule)
    s = s.replace('    (padstack "Via[0-3]_450:300_um"',
                  f'    (padstack "{WIDE_VIA}"\n' + "".join(f"      (shape (circle {l} {um(WIDE_VIA_D)}))\n"
                  for l in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")) + "      (attach off)\n    )\n"
                  '    (padstack "Via[0-3]_450:300_um"', 1)
    s = s.replace('(via "Via[0-3]_450:300_um")', f'(via "{WIDE_VIA}" "Via[0-3]_450:300_um")', 1)
    s = s.replace('(use_via "Via[0-3]_450:300_um")', f'(use_via "{WIDE_VIA}")')

    def fixed_via(m):
        x, y = int(m.group(1)) / 1000, -int(m.group(2)) / 1000
        bx0, by0, bx1, by1 = BGA_BOX
        if bx0 <= x <= bx1 and by0 <= y <= by1:
            return m.group(0)
        return m.group(0).replace("Via[0-3]_450:300_um", WIDE_VIA)
    s = re.sub(r'\(via "Via\[0-3\]_450:300_um"\s+(-?\d+)\s+(-?\d+)', fixed_via, s)
    # class rules: routed signal classes 0.1/0.1, POWER 0.3/0.1; USB and RF unchanged
    def cls(blk):
        name = blk.split()[1]
        if name in ("RF_75", "USB_90"):
            return blk
        w = um(POWER_W) if name == "POWER" else um(SIGNAL_W)
        return re.sub(r"\(width \d+\)\n(\s*)\(clearance \d+\)",
                      lambda m: f"(width {w})\n{m.group(1)}(clearance {um(SIGNAL_CLR)})", blk)
    out = []
    for blk in re.split(r"(?=\n    \(class )", s):
        if blk.startswith("\n    (class "):
            head, rest = blk.split("(circuit", 1)
            toks = [t for t in head.split() if t not in PLANE_NETS]
            blk = cls("\n    " + " ".join(toks) + "\n      (circuit" + rest)
        out.append(blk)
    s = "".join(out)
    # structure default rule (nets without a class) as the signal classes
    s = re.sub(r"(\(structure.*?\(rule\s*\(width )\d+(\)\s*\(clearance )\d+", lambda m: f"{m.group(1)}{um(SIGNAL_W)}{m.group(2)}{um(SIGNAL_CLR)}", s, count=1, flags=re.S)
    i = s.index("\n    (class ")
    s = s[:i] + ("\n    (class PLANES " + " ".join(PLANE_NETS) +
                 f'\n      (circuit\n        (use_via "{WIDE_VIA}")\n      )'
                 f"\n      (rule\n        (width {um(POWER_W)})\n        (clearance {um(SIGNAL_CLR)})\n      )\n    )") + s[i:]
    # receiver channels kept free; 0.3 mm from the card edge (rules.py)
    x0, y0, x1, y1 = L.RX_BAND
    ko = "".join(keepout(l, x0, y0, x1, y1) for l in ("F.Cu", "B.Cu"))
    m = re.search(r"\(boundary\s*\(path pcb 0((?:\s+-?[\d.]+)+)", s)
    nums = [float(v) / 1000 for v in m.group(1).split()]
    pts = [(nums[k], -nums[k + 1]) for k in range(0, len(nums), 2)]
    half = EDGE_CLR - SIGNAL_CLR
    ko += "".join(strip(l, a, b, half) for a, b in zip(pts, pts[1:] + pts[:1]) for l in ("F.Cu", "B.Cu"))
    j = s.index("    (via ", s.index("(structure"))
    s = s[:j] + ko + s[j:]
    return s


def export(board_path, dsn):
    board = pcbnew.LoadBoard(board_path)
    for t in board.GetTracks():
        t.SetLocked(True)
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        sys.exit("DSN export failed")
    text = dsn_patch(open(dsn).read())
    open(dsn, "w").write(text)


def run(dsn, ses, passes, log):
    cmd = ["java", "-jar", JAR, "-de", dsn, "-do", ses, "-da", "--gui.enabled=false",
           "--router.autorouter.ignore_net_classes=" + ",".join(NOT_ROUTED),
           f"--router.autorouter.max_passes={passes}",
           "--router.layers.routable=true,false,false,true",
           "--router.automatic_neckdown=false", f"--router.neck_width_um={um(SIGNAL_W)}",
           f"--router.copper_to_edge_clearance_um={um(EDGE_CLR)}",
           "--user_data_path=" + os.path.dirname(log)]
    with open(log, "w") as f:
        subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=True)


# ---------------------------------------------------------------- session
def sexp_tokens(s):
    return re.findall(r'\(|\)|"[^"]*"|[^\s()]+', s)


def parse_ses(path):
    """[(net, 'wire', layer, width_mm, [(x, y)...]) | (net, 'via', x, y)]"""
    toks = sexp_tokens(open(path).read())
    res = 1.0
    out = []
    stack, i = [], 0

    def read(i):
        assert toks[i] == "("
        lst, i = [], i + 1
        while toks[i] != ")":
            if toks[i] == "(":
                sub, i = read(i)
                lst.append(sub)
            else:
                lst.append(toks[i].strip('"'))
                i += 1
        return lst, i + 1

    tree, _ = read(0)

    def find(node, name):
        for c in node:
            if isinstance(c, list) and c and c[0] == name:
                yield c

    routes = next(find(tree, "routes"))
    r = next(find(routes, "resolution"))
    scale = {"um": 1e-3, "mm": 1.0, "mil": 0.0254}[r[1]] / float(r[2])
    for net in find(next(find(routes, "network_out")), "net"):
        name = net[1]
        for w in find(net, "wire"):
            p = next(find(w, "path"))
            nums = [float(v) for v in p[3:]]
            pts = [(nums[k] * scale, -nums[k + 1] * scale) for k in range(0, len(nums), 2)]
            out.append((name, "wire", p[1], float(p[2]) * scale, pts))
        for v in find(net, "via"):
            out.append((name, "via", float(v[2]) * scale, -float(v[3]) * scale))
    return out


def apply_ses(board, ses, routed_nets):
    """Add the session's new wiring for routed_nets. Returns (tracks, vias)."""
    T = pcbnew.ToMM
    have_seg, have_via = set(), set()
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            have_via.add((t.GetNetname(), round(T(t.GetPosition().x), 3), round(T(t.GetPosition().y), 3)))
        else:
            a, b = t.GetStart(), t.GetEnd()
            k = tuple(sorted([(round(T(a.x), 3), round(T(a.y), 3)), (round(T(b.x), 3), round(T(b.y), 3))]))
            have_seg.add((t.GetNetname(), t.GetLayerName(), k))
    cu = Copper(board)
    nt = nv = 0
    for item in parse_ses(ses):
        net = item[0]
        if net not in routed_nets:
            continue
        if item[1] == "via":
            x, y = round(item[2], 3), round(item[3], 3)
            if (net, x, y) not in have_via:
                cu.via(net, x, y)
                have_via.add((net, x, y))
                nv += 1
            continue
        _, _, layer, w, pts = item
        pts = [(round(x, 3), round(y, 3)) for x, y in pts]
        for a, b in zip(pts, pts[1:]):
            k = (net, layer, tuple(sorted([a, b])))
            if a == b or k in have_seg:
                continue
            # the router still necks down at a few small pads; JLC's minimum is 0.09 mm
            cu.track(net, [a, b], max(round(w, 3), MIN_W), layer[0])
            have_seg.add(k)
            nt += 1
    return nt, nv


def routed_nets(dsn):
    """Nets the router was asked to route (classes not in NOT_ROUTED)."""
    s = open(dsn).read()
    nets = set()
    for m in re.finditer(r"\n    \(class (\S+)((?:\s+(?:\"[^\"]*\"|[^\s()]+))*)\s*\n\s+\(circuit", s):
        if m.group(1) in NOT_ROUTED:
            continue
        nets.update(t.strip('"') for t in m.group(2).split())
    return nets


def main():
    import design
    passes = int(sys.argv[sys.argv.index("--passes") + 1]) if "--passes" in sys.argv else 20
    base = os.path.join(KICAD_DIR, design.PROJECT)
    # route from the scripted board only: drop the old session and rebuild
    for ext in (".ses", ".routed"):
        if os.path.exists(base + ext):
            os.remove(base + ext)
    pcbgen = [sys.executable, os.path.join(HERE, "pcbgen.py")]
    subprocess.run(pcbgen, check=True)
    work = tempfile.mkdtemp(prefix="autoroute-")
    dsn = os.path.join(work, design.PROJECT + ".dsn")
    export(base + ".kicad_pcb", dsn)
    ses = os.path.join(work, design.PROJECT + ".ses")
    log = os.path.join(work, "freerouting.log")
    run(dsn, ses, passes, log)
    # keep the session and the list of routed nets beside the board, then
    # rebuild the board with them
    open(base + ".ses", "w").write(open(ses).read())
    open(base + ".routed", "w").write("\n".join(sorted(routed_nets(dsn))) + "\n")
    print("router log:", log)
    subprocess.run(pcbgen, check=True)


if __name__ == "__main__":
    main()
