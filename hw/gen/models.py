# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Simplified 3D models (VRML 2) for parts without a usable KiCad model.

They are drawn from the makers' outline drawings, for the mechanical check
at the bracket only. Coordinates in mm, footprint frame: x right, y down
(PCB), z up from the board surface. KiCad VRML units are 0.1 inch.
"""
import math
import os

U = 1 / 2.54          # mm -> KiCad VRML units


def box(x0, x1, y0, y1, z0, z1):
    """Axis-aligned box, PCB coordinates (y down)."""
    p = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    f = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    return p, f


def cyl_x(x0, x1, yc, zc, r, n=32):
    """Cylinder along x."""
    p = []
    for x in (x0, x1):
        for i in range(n):
            a = 2 * math.pi * i / n
            p.append((x, yc + r * math.cos(a), zc + r * math.sin(a)))
    f = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    return p, f


def shape(mesh, rgb):
    p, f = mesh
    pts = ", ".join(f"{x * U:.4f} {-y * U:.4f} {z * U:.4f}" for x, y, z in p)
    # both windings, so every face is lit whichever way its normal points
    faces = list(f) + [tuple(reversed(face)) for face in f]
    idx = ", ".join(" ".join(str(i) for i in face) + " -1" for face in faces)
    r, g, b = rgb
    return ("Shape {\n appearance Appearance { material Material { diffuseColor %.3f %.3f %.3f "
            "emissiveColor 0 0 0 specularColor 0.3 0.3 0.3 ambientIntensity 0.4 shininess 0.4 transparency 0 } }\n geometry IndexedFaceSet { ccw TRUE solid TRUE\n"
            "  coord Coordinate { point [ %s ] }\n  coordIndex [ %s ] }\n}\n") % (r, g, b, pts, idx)


METAL = (0.78, 0.78, 0.76)
DARK = (0.1, 0.1, 0.1)
WHITE = (0.92, 0.92, 0.9)


def usb_c_samesky_uj32():
    """Same Sky UJ32-C-H-G-H2-SMT-TR, in the frame of otr:USB_C_Receptacle_SameSky_
    UJ32-C-H-G-H2-SMT (origin = front B sub-row, mating face at y = +7.75):
    shell 8.34 x 2.56 on a 1.75 mm centreline over the board, body 10.0 mm long
    (rear at y = -2.25), 3.42 mm overall height (datasheet sheet 2)."""
    out = shape(box(-4.17, 4.17, -2.25, 7.75, 0.47, 3.03), METAL)
    out += shape(box(-4.825, 4.825, -2.25, 1.2, 0.0, 3.42), DARK)    # insulator block at the rear
    out += shape(box(-3.9, 3.9, 7.70, 7.77, 0.75, 2.75), DARK)       # opening
    out += shape(box(-2.9, 2.9, 7.6, 7.78, 1.5, 2.0), WHITE)         # tongue
    return out


def f_jack_ds803():
    """DOSIN DS803FPR0016, in the frame of otr:F_Female_DOSIN_DS803FPR0016_Horizontal
    (origin = the single front body hole, mating axis -x). From the maker's
    drawing and LCSC's footprint: body 10.75 mm square from x = -1.0 to +8.0,
    collar d10.4 from -2.0 to -1.0, M9.7 thread to x = -16.0 (24.0 mm in all)."""
    h = 10.75 / 2
    out = shape(box(-1.0, 8.0, -h, h, 0.0, 10.75), METAL)
    out += shape(cyl_x(-2.0, -1.0, 0.0, h, 5.2), METAL)
    out += shape(cyl_x(-16.0, -2.0, 0.0, h, 4.85), METAL)
    out += shape(cyl_x(-16.05, -15.0, 0.0, h, 2.0), WHITE)           # insulator face
    return out


def write_all(dirpath):
    os.makedirs(dirpath, exist_ok=True)
    for name, body in (("USB_C_Receptacle_SameSky_UJ32-C-H-G-H2-SMT_simple", usb_c_samesky_uj32()),
                       ("F_Female_DOSIN_DS803FPR0016_simple", f_jack_ds803())):
        open(os.path.join(dirpath, name + ".wrl"), "w").write("#VRML V2.0 utf8\n" + body)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    write_all(os.path.join(here, "..", "lib", "otr.3dshapes"))
    print("wrote hw/lib/otr.3dshapes")
