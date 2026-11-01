# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Design rules and net classes for OTR-4TS3-U1 (JLC04161H-7628, D-53).

Trace geometry from a 2D quasi-static field solve of the outer-layer
cross-section (prepreg 0.2104 mm, er 4.4, 1 oz copper, solder mask er 3.8,
reference plane L2): 50 ohm = 0.355 mm (sanity check), 75 ohm microstrip =
0.145 mm, 90 ohm differential = 0.263 mm wide / 0.15 mm gap.
JLC limits (capabilities page, 2026-11): track/space 0.09 mm, vias free
from 0.45 mm diameter with 0.2-0.25 mm holes, copper to routed edge 0.2 mm,
pad hole to pad hole 0.45 mm, silkscreen 0.15 mm line / 1.0 mm text.
"""
import json

# name: (track, clearance, diff width, diff gap), patterns (KiCad wildcards)
CLASSES = {
    "USB_90": ((0.263, 0.15, 0.263, 0.15),
               ["FX3_SSTX_*", "USB_SSRX_*", "MUX_TX*", "MUX_RX*", "USBC_TX*", "USBC_RX*",
                "HDR_SS*", "HDR_TX_*", "USB_DP", "USB_DM", "USBC_DP", "USBC_DM", "HDR_DP", "HDR_DM"]),
    # 75 ohm microstrip; ground pours are kept ~3 widths away by the custom rule
    # below (a class clearance would also hit the parts' own fine-pitch pads)
    "RF_75": ((0.145, 0.15, 0.145, 0.2),
              ["ANT_*", "RF_T*", "RF_S*", "RFT_SW*", "RFS_SW*", "RFT_LNA_*", "RFS_LNA_*",
               "RFT_SPLIT_IN", "RFS_SPLIT_IN", "RFT_STAR", "RFS_STAR"]),
    "POWER": ((0.5, 0.2, 0.2, 0.25),
              ["+*", "PCIE_12V", "PCIE_3V3", "DC_12V", "VBUS", "BUCK_SW", "HDR_VBUS"]),
    "GPIF": ((0.15, 0.15, 0.15, 0.15), ["GPIF_*"]),
}
DEFAULT = dict(track_width=0.15, clearance=0.15, via_diameter=0.45, via_drill=0.25,
               diff_pair_width=0.2, diff_pair_gap=0.2)
MINIMUMS = dict(min_clearance=0.1, min_track_width=0.09, min_via_diameter=0.45,
                min_via_annular_width=0.1, min_through_hole_diameter=0.2, min_hole_to_hole=0.2,
                min_hole_clearance=0.2, min_copper_edge_clearance=0.3, min_silk_clearance=0.0,
                min_text_height=1.0, min_text_thickness=0.15)

DRU = """(version 1)
# JLCPCB (4 layers, 1 oz outer) limits that KiCad's global settings do not cover
(rule "pad hole to pad hole (JLC 0.45 mm)"
  (condition "A.Type == 'Pad' && B.Type == 'Pad' && A.Pad_Type == 'Through-hole' && B.Pad_Type == 'Through-hole'")
  (constraint hole_to_hole (min 0.45mm)))
(rule "BGA fan-out (JLC allows 0.09 mm near BGA pads)"
  (condition "A.intersectsCourtyard('U1')")
  (constraint clearance (min 0.09mm)))
(rule "RF 75 ohm keeps copper pours away"
  (condition "A.NetClass == 'RF_75' && B.Type == 'Zone'")
  (constraint clearance (min 0.45mm)))
"""


def apply(pro_path, dru_path):
    pro = json.load(open(pro_path))
    ns = pro.setdefault("net_settings", {})
    base = ns["classes"][0] if ns.get("classes") else {}
    base = dict(base, name="Default", **DEFAULT)
    classes = [base]
    patterns = []
    for i, (name, ((tw, cl, dw, dg), pats)) in enumerate(CLASSES.items()):
        c = dict(base, name=name, track_width=tw, clearance=cl, diff_pair_width=dw,
                 diff_pair_gap=dg, priority=i)
        classes.append(c)
        patterns += [{"netclass": name, "pattern": p} for p in pats]
    ns["classes"] = classes
    ns["netclass_patterns"] = patterns
    rules = pro["board"]["design_settings"]["rules"]
    rules.update(MINIMUMS)
    json.dump(pro, open(pro_path, "w"), indent=2, ensure_ascii=False)
    open(dru_path, "w").write(DRU)
