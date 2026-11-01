# hw

KiCad project for the OTR-4TS3-U1 board (4-layer, JLC04161H-7628 stackup). License: CERN-OHL-S-2.0 (see ../LICENSES).
See ../docs/architecture.md.

## Generated design (D-51)

The schematic is generated, not drawn: `hw/gen/design.py` describes the circuit in Python, and `hw/gen/schgen.py` writes `hw/kicad/*.kicad_sch`. Every pin connects through a global label at its end point, so the netlist is exactly the description.

```sh
python3 hw/gen/symbols.py   # project symbols -> hw/lib/otr.kicad_sym (FX3 from the datasheet ball map)
python3 hw/gen/design.py    # schematic + verification
```

Verification:
- The netlist that KiCad exports (`kicad-cli sch export netlist`) must equal the description.
- Every pin of every symbol must be assigned (`NC` for unused pins).
- Pins that the library draws stacked must share a net.
- Library no-connect pins must be `NC`.
- ERC runs (`kicad-cli sch erc`).

Phase 1 covers everything except the Sony receiver core. The receiver core waits for the reference-board measurement and the photo survey, because the CXD2856ER/CXD2858ER pinouts are not public.

Status (2026-11-01):
- The FPGA sheet is done: iCE40HX4K-TQ144 with its supplies, configuration pins (CRESET_B pull-down, CDONE and SS_B pull-ups), and the 50 MHz oscillator that also drives the FX3 PCLK. It also has a status LED and test pads. It generates `fpga/syn/otr_top.pcf`.
- The FX3 sheet is done: CYUSB3014, its supplies, the 19.2 MHz crystal, reset, PMODE strapping (SPI boot, USB fallback), JTAG pads, and the W25Q32JV boot flash with the BOOT_USB jumper.
- Its netlist matches the description.
- ERC still reports undriven supply nets and USB RX inputs. These clear once the power and USB sheets exist.
