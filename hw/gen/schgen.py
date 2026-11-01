# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Schematic generator for OTR-4TS3-U1 (D-51).

The circuit is described in Python as parts and nets. This module writes a
KiCad 10 hierarchical schematic in which every pin is connected through a
global label at its end point (no wires), so the netlist is exactly the
description. `verify()` exports the netlist with kicad-cli and compares it
with the description, and runs ERC.
"""
import copy
import os
import subprocess
import uuid

from sexp import Q, dump, parse

KICAD_SHARE = "/Applications/KiCad/KiCad.app/Contents/SharedSupport"
GRID = 1.27


def _u():
    return Q(str(uuid.uuid4()))


def _snap(v):
    return round(round(v / GRID) * GRID, 4)


class SymbolLib:
    """Loads symbols from the KiCad libraries and from project libraries."""

    def __init__(self, project_libs):
        self.cache = {}
        self.project_libs = project_libs   # nickname -> path

    def _file(self, nick):
        if nick in self.project_libs:
            return self.project_libs[nick]
        return os.path.join(KICAD_SHARE, "symbols", nick + ".kicad_sym")

    def get(self, lib_id):
        if lib_id in self.cache:
            return self.cache[lib_id]
        nick, name = lib_id.split(":", 1)
        tree = parse(open(self._file(nick)).read())[0]
        syms = {e[1]: e for e in tree[1:] if isinstance(e, list) and e[0] == "symbol"}
        if name not in syms:
            raise KeyError(lib_id)
        sym = copy.deepcopy(syms[name])
        ext = [e for e in sym if isinstance(e, list) and e[0] == "extends"]
        if ext:   # resolve a derived symbol: base graphics/pins + own properties
            base = copy.deepcopy(syms[ext[0][1]])
            props = [e for e in sym if isinstance(e, list) and e[0] == "property"]
            body = [e for e in base[2:] if not (isinstance(e, list) and e[0] == "property")]
            for e in body:   # rename unit sub-symbols
                if isinstance(e, list) and e[0] == "symbol":
                    e[1] = Q(e[1].replace(ext[0][1], name, 1))
            sym = ["symbol", Q(name)] + props + body
        sym[1] = Q(lib_id)
        self.cache[lib_id] = sym
        return sym

    def pins(self, lib_id):
        """{pin number: (unit, x, y, name, type)} in symbol coordinates (y up)."""
        sym = self.get(lib_id)
        name = lib_id.split(":", 1)[1]
        out = {}
        for e in sym:
            if not (isinstance(e, list) and e[0] == "symbol"):
                continue
            unit = int(e[1].split("_")[-2])
            for p in e[2:]:
                if isinstance(p, list) and p[0] == "pin":
                    at = next(x for x in p if isinstance(x, list) and x[0] == "at")
                    num = next(x for x in p if isinstance(x, list) and x[0] == "number")[1]
                    pname = next(x for x in p if isinstance(x, list) and x[0] == "name")[1]
                    out.setdefault(str(num), []).append((unit, float(at[1]), float(at[2]), str(pname), p[1]))
        return out

    def units(self, lib_id):
        return sorted({u for v in self.pins(lib_id).values() for (u, *_r) in v} - {0}) or [1]


class Part:
    def __init__(self, ref, lib_id, value, footprint, nets, lcsc=None, dnp=False, fields=None):
        self.ref, self.lib_id, self.value, self.footprint = ref, lib_id, value, footprint
        self.nets = dict(nets)          # pin number -> net name ("NC" = no connect)
        self.lcsc, self.dnp = lcsc, dnp
        self.fields = dict(fields or {})


class Sheet:
    def __init__(self, name, title):
        self.name, self.title = name, title
        self.parts = []

    def add(self, *parts):
        self.parts.extend(parts)
        return parts[0] if len(parts) == 1 else parts


class Design:
    def __init__(self, project, project_libs):
        self.project = project
        self.lib = SymbolLib(project_libs)
        self.sheets = []

    def sheet(self, name, title):
        s = Sheet(name, title)
        self.sheets.append(s)
        return s

    def stacked_groups(self, lib_id):
        """Pins drawn at the same place in the same unit: KiCad joins them."""
        groups = {}
        for num, entries in self.lib.pins(lib_id).items():
            for (u, x, y, _n, _t) in entries:
                groups.setdefault((u, round(x, 3), round(y, 3)), set()).add(num)
        return [g for g in groups.values() if len(g) > 1]

    # ---- netlist view of the description ----
    def netlist(self):
        nets = {}
        for s in self.sheets:
            for p in s.parts:
                for g in self.stacked_groups(p.lib_id):
                    vals = {p.nets.get(n) for n in g}
                    if len(vals) > 1:
                        raise ValueError(f"{p.ref}: stacked pins {sorted(g)} must share a net, got {vals}")
                pins = self.lib.pins(p.lib_id)
                for num in pins:
                    if num not in p.nets:
                        raise ValueError(f"{p.ref}: pin {num} ({pins[num][0][3]}) not assigned")
                for num, net in p.nets.items():
                    if num not in pins:
                        raise ValueError(f"{p.ref}: no pin {num} in {p.lib_id}")
                    if pins[num][0][4] == "no_connect" and net != "NC":
                        raise ValueError(f"{p.ref}: pin {num} is a library no-connect pin; use NC")
                    if net != "NC":
                        nets.setdefault(net, set()).add((p.ref, num))
        return nets

    # ---- writer ----
    def write(self, outdir):
        os.makedirs(outdir, exist_ok=True)
        root_uuid = str(uuid.uuid4())
        sheet_uuids = {s.name: str(uuid.uuid4()) for s in self.sheets}
        for i, s in enumerate(self.sheets):
            self._write_sheet(outdir, s, root_uuid, sheet_uuids[s.name], i + 2)
        # root sheet: one hierarchical sheet box per sheet
        items = []
        for i, s in enumerate(self.sheets):
            x, y = 25.4 + (i % 4) * 63.5, 30.48 + (i // 4) * 38.1
            items.append(["sheet", ["at", x, y], ["size", 50.8, 25.4], ["exclude_from_sim", "no"],
                          ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"],
                          ["fields_autoplaced", "yes"], ["stroke", ["width", 0.1524], ["type", "solid"]],
                          ["fill", ["color", 0, 0, 0, 0.0]], ["uuid", Q(sheet_uuids[s.name])],
                          ["property", Q("Sheetname"), Q(s.title), ["at", x, y - 0.7, 0],
                           ["effects", ["font", ["size", 1.27, 1.27]], ["justify", "left", "bottom"]]],
                          ["property", Q("Sheetfile"), Q(s.name + ".kicad_sch"), ["at", x, y + 26.0, 0],
                           ["effects", ["font", ["size", 1.27, 1.27]], ["justify", "left", "top"]]],
                          ["instances", ["project", Q(self.project),
                                         ["path", Q("/" + root_uuid), ["page", Q(str(i + 2))]]]]])
        root = ["kicad_sch", ["version", 20250114], ["generator", Q("otr-gen")],
                ["generator_version", Q("10.0")], ["uuid", Q(root_uuid)], ["paper", Q("A3")],
                ["title_block", ["title", Q("OTR-4TS3-U1")], ["comment", 1, Q("Generated by hw/gen (do not edit by hand)")]],
                ["lib_symbols"]] + items + [["sheet_instances", ["path", Q("/"), ["page", Q("1")]]]]
        open(os.path.join(outdir, self.project + ".kicad_sch"), "w").write(dump(root) + "\n")

    def _write_sheet(self, outdir, s, root_uuid, sheet_uuid, page):
        libsyms, placed, labels, ncs = {}, [], [], []
        x0, y0, x, y, row_h = 25.4, 25.4, 25.4, 25.4, 0.0
        width = 380.0
        for p in s.parts:
            libsyms[p.lib_id] = self.lib.get(p.lib_id)
            pins = self.lib.pins(p.lib_id)
            for unit in self.lib.units(p.lib_id):
                upins = {n: v for n, vs in pins.items() for v in vs if v[0] in (0, unit)}
                xs = [v[1] for v in upins.values()] or [0]
                ys = [v[2] for v in upins.values()] or [0]
                w = max(xs) - min(xs) + 40.0
                h = max(ys) - min(ys) + 15.0
                if x + w > width:
                    x, y, row_h = x0, y + row_h, 0.0
                cx, cy = _snap(x - min(xs) + 20.0), _snap(y + max(ys) + 7.5)
                x += w
                row_h = max(row_h, h)
                props = [["property", Q("Reference"), Q(p.ref), ["at", cx, cy - (max(ys) + 2.54), 0],
                          ["effects", ["font", ["size", 1.27, 1.27]]]],
                         ["property", Q("Value"), Q(p.value), ["at", cx, cy - min(ys) + 2.54, 0],
                          ["effects", ["font", ["size", 1.27, 1.27]]]],
                         ["property", Q("Footprint"), Q(p.footprint), ["at", cx, cy, 0],
                          ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]]]]
                extra = dict(p.fields)
                if p.lcsc:
                    extra["LCSC"] = p.lcsc
                for k, v in extra.items():
                    props.append(["property", Q(k), Q(v), ["at", cx, cy, 0],
                                  ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]]])
                placed.append(["symbol", ["lib_id", Q(p.lib_id)], ["at", cx, cy, 0], ["unit", unit],
                               ["exclude_from_sim", "no"], ["in_bom", "no" if p.dnp else "yes"],
                               ["on_board", "yes"], ["dnp", "yes" if p.dnp else "no"], ["uuid", _u()]]
                              + props
                              + [["pin", Q(n), ["uuid", _u()]] for n in upins]
                              + [["instances", ["project", Q(self.project),
                                                ["path", Q(f"/{root_uuid}/{sheet_uuid}"),
                                                 ["reference", Q(p.ref)], ["unit", unit]]]]])
                seen = set()
                for n, (u, px, py, pname, ptype) in upins.items():
                    wx, wy = _snap(cx + px), _snap(cy - py)
                    if (wx, wy) in seen:
                        continue
                    seen.add((wx, wy))
                    net = p.nets[n]
                    if net == "NC":
                        ncs.append(["no_connect", ["at", wx, wy], ["uuid", _u()]])
                        continue
                    labels.append(["global_label", Q(net), ["shape", "passive"], ["at", wx, wy, 0],
                                   ["fields_autoplaced", "yes"],
                                   ["effects", ["font", ["size", 1.0, 1.0]], ["justify", "left"]],
                                   ["uuid", _u()]])
        sch = ["kicad_sch", ["version", 20250114], ["generator", Q("otr-gen")],
               ["generator_version", Q("10.0")], ["uuid", Q(sheet_uuid)], ["paper", Q("A3")],
               ["title_block", ["title", Q(s.title)], ["comment", 1, Q("Generated by hw/gen (do not edit by hand)")]],
               ["lib_symbols"] + list(libsyms.values())] + placed + labels + ncs
        open(os.path.join(outdir, s.name + ".kicad_sch"), "w").write(dump(sch) + "\n")


def kicad_netlist(sch_path, out_path):
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", out_path, sch_path],
                   check=True, capture_output=True)
    tree = parse(open(out_path).read())[0]
    nets = {}
    for e in tree:
        if isinstance(e, list) and e[0] == "nets":
            for n in e[1:]:
                name = next(x for x in n if isinstance(x, list) and x[0] == "name")[1].lstrip("/")
                nodes = {(next(x for x in nd if x[0] == "ref")[1], next(x for x in nd if x[0] == "pin")[1])
                         for nd in n if isinstance(nd, list) and nd[0] == "node"}
                nets[str(name)] = {(str(a), str(b)) for a, b in nodes}
    return nets


def verify(design, outdir):
    """Exported netlist == description; returns (ok, messages)."""
    want = design.netlist()
    got = kicad_netlist(os.path.join(outdir, design.project + ".kicad_sch"),
                        os.path.join(outdir, design.project + ".net"))
    got = {k: v for k, v in got.items() if not k.startswith("unconnected-")}
    msgs = []
    for k in sorted(set(want) | set(got)):
        if want.get(k) != got.get(k):
            msgs.append(f"net {k}: want {sorted(want.get(k, []))} got {sorted(got.get(k, []))}")
    return not msgs, msgs


def erc(design, outdir):
    rpt = os.path.join(outdir, "erc.rpt")
    subprocess.run(["kicad-cli", "sch", "erc", "--severity-error", "-o", rpt,
                    os.path.join(outdir, design.project + ".kicad_sch")], capture_output=True)
    return open(rpt).read()
