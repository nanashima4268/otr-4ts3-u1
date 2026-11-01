#!/bin/sh
# Export the KiCad project into the browser viewer (hw/view/build/).
# Usage: hw/view/build.sh [--if-changed]
#   --if-changed  exit 3 without exporting when hw/kicad and hw/lib are unchanged since the last build
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
KI="$ROOT/hw/kicad"
OUT="$ROOT/hw/view/build"
PCB="$KI/otr-4ts3-u1.kicad_pcb"
SCH="$KI/otr-4ts3-u1.kicad_sch"
GT="npx -y @gltf-transform/cli@4.1.1"

# Fingerprint of the design inputs (content, not mtime).
STAMP=$(cat "$KI"/*.kicad_sch "$PCB" "$ROOT"/hw/lib/otr.kicad_sym "$ROOT"/hw/lib/otr.pretty/* | shasum -a 256 | cut -c1-16)
if [ "${1:-}" = "--if-changed" ] && [ -f "$OUT/stamp.txt" ] && [ "$(cat "$OUT/stamp.txt")" = "$STAMP" ]; then
  echo "unchanged ($STAMP)"; exit 3
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/sch" "$TMP/pcb" "$TMP/3d"

kicad-cli sch export svg -o "$TMP/sch" "$SCH" >/dev/null
kicad-cli pcb export svg -o "$TMP/pcb/top.svg" --layers F.Cu,F.SilkS,F.Fab,F.CrtYd,Edge.Cuts,User.Drawings,User.Comments \
  --mode-single --exclude-drawing-sheet --fit-page-to-board "$PCB" >/dev/null
kicad-cli pcb export svg -o "$TMP/pcb/bottom.svg" --layers B.Cu,B.SilkS,B.Fab,B.CrtYd,Edge.Cuts \
  --mode-single --mirror --exclude-drawing-sheet --fit-page-to-board "$PCB" >/dev/null
for s in top bottom; do
  kicad-cli pcb render -o "$TMP/3d/$s.png" --side $s --width 1800 --height 1200 --quality high --background opaque "$PCB" >/dev/null
done
kicad-cli pcb render -o "$TMP/3d/iso.png" --side top --rotate '-45,0,30' --width 1800 --height 1200 --quality high --background opaque "$PCB" >/dev/null
kicad-cli pcb export glb -o "$TMP/3d/raw.glb" --subst-models --include-tracks --include-pads --include-zones \
  --include-silkscreen --include-soldermask "$PCB" >/dev/null
# three.js r147 cannot read EXT_mesh_gpu_instancing or meshopt, so: no instancing, no compression.
$GT optimize "$TMP/3d/raw.glb" "$TMP/3d/opt.glb" --compress false --texture-compress false --instance false \
  --simplify-ratio 0.2 --simplify-error 0.002 >/dev/null 2>&1
# Artifacts do not serve .glb: ship it gzip + base64 as text, the page inflates it.
gzip -9 -c "$TMP/3d/opt.glb" | base64 > "$TMP/3d/board.glb.gz.b64.txt"
rm "$TMP/3d/raw.glb" "$TMP/3d/opt.glb"

python3 -I - "$TMP" "$ROOT" "$STAMP" <<'PY'
import sys, re, glob, json, os, subprocess, datetime
tmp, root, stamp = sys.argv[1:4]
# Sheet SVGs: stable names from the sheet title, no DOCTYPE (artifacts refuse DTDs).
names = {"FX3": "fx3", "iCE40": "fpga", "Power": "power", "USB:": "usb", "I2C": "control", "RF": "rf"}
sheets = []
for f in sorted(glob.glob(f"{tmp}/sch/*.svg")):
    base = os.path.basename(f)[:-4]
    title = base.split("otr-4ts3-u1-", 1)[1] if "otr-4ts3-u1-" in base else "トップ"
    key = "root" if title == "トップ" else next((v for k, v in names.items() if title.startswith(k)), re.sub(r"\W+", "_", title).lower())
    os.rename(f, f"{tmp}/sch/{key}.svg")
    sheets.append({"file": f"{key}.svg", "title": title, "key": key})
order = ["root", "fx3", "fpga", "power", "usb", "control", "rf"]
sheets.sort(key=lambda s: order.index(s["key"]) if s["key"] in order else 99)
for f in glob.glob(f"{tmp}/sch/*.svg") + glob.glob(f"{tmp}/pcb/*.svg"):
    s = open(f).read()
    open(f, "w").write(re.sub(r"<!DOCTYPE[^>]*>", "", s, count=1, flags=re.S))
pcb = open(f"{root}/hw/kicad/otr-4ts3-u1.kicad_pcb").read()
fps = re.split(r"\n\t\(footprint ", pcb)[1:]
nomodel = [re.search(r'\(property "Reference" "([^"]+)"', f).group(1) for f in fps if "(model" not in f]
git = lambda *a: subprocess.run(["git", "-C", root, *a], capture_output=True, text=True).stdout.strip()
dirty = bool(git("status", "--porcelain", "--", "hw/kicad", "hw/lib"))
meta = {
    "commit": git("log", "-1", "--format=%h", "--", "hw/kicad", "hw/lib"),
    "commitSubject": git("log", "-1", "--format=%s", "--", "hw/kicad", "hw/lib"),
    "dirty": dirty,
    "built": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    "kicad": subprocess.run(["kicad-cli", "version"], capture_output=True, text=True).stdout.strip(),
    "footprints": len(fps),
    "segments": pcb.count("\n\t(segment"),
    "vias": pcb.count("\n\t(via"),
    "zones": pcb.count("\n\t(zone"),
    "noModel": sorted(nomodel, key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0))),
    "sheets": sheets,
    "stamp": stamp,
}
json.dump(meta, open(f"{tmp}/meta.json", "w"), ensure_ascii=False, indent=1)
PY

rm -rf "$OUT"
mkdir -p "$OUT"
cp -R "$TMP/sch" "$TMP/pcb" "$TMP/3d" "$TMP/meta.json" "$OUT/"
cp "$ROOT/hw/view/index.html" "$OUT/index.html"
echo "$STAMP" > "$OUT/stamp.txt"
echo "built $OUT ($STAMP)"
