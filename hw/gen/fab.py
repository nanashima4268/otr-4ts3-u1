# SPDX-License-Identifier: CERN-OHL-S-2.0
"""JLCPCB fabrication and assembly outputs (B-7, D-72).

Run with KiCad's bundled python3 after pcbgen.py:
    fab.py [OUT_DIR]          (default ~/otr-data/work/fab/<commit>)

Writes
  gerber/      Gerbers (Protel extensions, soldermask subtracted from silk,
               vias tented by the board setting) + Excellon drill (mm,
               absolute, decimal, PTH and NPTH merged as JLC asks)
  <name>-gerber.zip
  bom.csv      Comment, Designator, Footprint, LCSC Part #   (fitted parts)
  cpl.csv      Designator, Mid X, Mid Y, Layer, Rotation     (fitted parts)

Footprints that are copper only (test pads, screw holes, solder jumper,
PCIe fingers) are not parts and stay out of the BOM and CPL. A fitted part
without an LCSC number stops the script.

Rotation: JLC's part models do not always share KiCad's zero orientation.
JLC_ROT adds a per-footprint correction; each entry is checked in JLC's
assembly preview (D-72) before ordering.
"""
import csv
import os
import re
import subprocess
import sys
import zipfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, "..", "kicad", "otr-4ts3-u1.kicad_pcb")
CLI = os.environ.get("KICAD_CLI", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.Paste", "B.Paste", "F.Silkscreen", "B.Silkscreen",
          "F.Mask", "B.Mask", "Edge.Cuts"]
PATTERN_ONLY = re.compile(r"^(TestPoint_|MountingHole_|SolderJumper|BUS_PCIexpress)")
# footprint name regex -> degrees added to KiCad's rotation (checked in JLC's preview)
JLC_ROT = []


def commit():
    try:
        return subprocess.run(["git", "-C", HERE, "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "nogit"


def parts(board):
    out, missing = [], []
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        name = str(fp.GetFPID().GetLibItemName())
        if fp.IsDNP() or fp.IsExcludedFromBOM() or fp.IsExcludedFromPosFiles() or PATTERN_ONLY.match(name):
            continue
        fields = {f.GetName(): f.GetText() for f in fp.GetFields()}
        lcsc = fields.get("LCSC", "").strip()
        if not lcsc:
            missing.append(fp.GetReference())
        out.append((fp, name, lcsc))
    if missing:
        sys.exit("fitted parts without an LCSC number: " + " ".join(missing))
    return out


def rotation(fp, name):
    rot = fp.GetOrientationDegrees()
    for pat, add in JLC_ROT:
        if re.search(pat, name):
            rot += add
            break
    return rot % 360


def main(out):
    gdir = os.path.join(out, "gerber")
    os.makedirs(gdir, exist_ok=True)
    for f in os.listdir(gdir):
        os.remove(os.path.join(gdir, f))
    subprocess.run([CLI, "pcb", "export", "gerbers", "-o", gdir, "-l", ",".join(LAYERS),
                    "--subtract-soldermask", "--check-zones", BOARD], check=True, capture_output=True)
    subprocess.run([CLI, "pcb", "export", "drill", "-o", gdir + "/", "--format", "excellon",
                    "--drill-origin", "absolute", "--excellon-zeros-format", "decimal",
                    "--excellon-oval-format", "alternate", "-u", "mm", "--generate-map", "--map-format", "pdf",
                    BOARD], check=True, capture_output=True)
    name = os.path.splitext(os.path.basename(BOARD))[0]
    zpath = os.path.join(out, f"{name}-gerber.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(gdir)):
            if not f.endswith(".pdf"):
                z.write(os.path.join(gdir, f), f)

    board = pcbnew.LoadBoard(BOARD)
    ps = parts(board)
    groups = {}
    for fp, fname, lcsc in ps:
        groups.setdefault((fp.GetValue(), fname, lcsc), []).append(fp.GetReference())
    with open(os.path.join(out, "bom.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, fname, lcsc), refs in sorted(groups.items(), key=lambda g: g[1][0]):
            w.writerow([value, ",".join(sorted(refs, key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0)))),
                        fname, lcsc])
    with open(os.path.join(out, "cpl.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for fp, fname, lcsc in ps:
            p = fp.GetPosition()
            # JLC's coordinates: x right, y up (KiCad's y grows downwards)
            w.writerow([fp.GetReference(), f"{pcbnew.ToMM(p.x):.4f}mm", f"{-pcbnew.ToMM(p.y):.4f}mm",
                        "Top" if fp.GetLayer() == pcbnew.F_Cu else "Bottom", f"{rotation(fp, fname):.1f}"])
    print(f"wrote {out}: {len(os.listdir(gdir))} gerber/drill files, {len(groups)} BOM lines, {len(ps)} placements")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(f"~/otr-data/work/fab/{commit()}"))
