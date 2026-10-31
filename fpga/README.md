# fpga

iCE40HX4K-TQ144 (HX8K die; nextpnr: --hx8k --package tq144:4k).
Serial TS receivers x4, channel tagging, mux, and a GPIF II synchronous slave FIFO toward the FX3.
Toolchain: yosys, nextpnr-ice40, icepack, iverilog, cocotb. License: GPL-2.0-only (see ../LICENSES).

## Setup (macOS)

Install oss-cad-suite (YosysHQ/oss-cad-suite-build) to `~/opt/oss-cad-suite`, then `source ~/opt/oss-cad-suite/environment`. This provides yosys, nextpnr-ice40, icepack, iverilog, and cocotb.

## Simulation (S2)

The stimulus is real raw TS captured in S0. It contains broadcast content, so it is kept outside the repository (`~/otr-data/`), and run in a scratch directory:

```sh
source ~/opt/oss-cad-suite/environment
mkdir -p /tmp/otr-sim && cd /tmp/otr-sim
python3 <repo>/fpga/sim/tb_check.py prep raw_T27.ts raw_T20.ts raw_BS15_0.ts raw_BS01_0.ts
iverilog -g2012 -o tb.vvp <repo>/fpga/sim/tb_ts_core.v <repo>/fpga/rtl/*.v
vvp -n tb.vvp && python3 <repo>/fpga/sim/tb_check.py check          # normal
vvp -n tb.vvp +stall && python3 <repo>/fpga/sim/tb_check.py check   # sink stalled -> whole-packet drops
```

Results (2026-11-01):
- Four channels at 33/40/62/77 MHz, with random VALID gaps and both SYNC styles (1-bit and 8-bit). 400 real packets per channel came out bit-exact and in order.
- A truncated packet was dropped as intended.
- When the sink stalled, the FIFOs overflowed and dropped only whole packets. The drop counters matched the missing packets (2/4/8/10).
- iCE40HX4K-TQ144 (`--hx8k --package tq144:4k`) used 20% of the logic cells (1602/7680), 8 of 32 BRAMs, and 33 IOs. Fmax: TS clocks 94-97 MHz, system clock 84-85 MHz.

## Output format

Each 188-byte packet is passed through whole. Its sync byte is rewritten to `((ch + 1) << 4) | 0x07` (0x17/0x27/0x37/0x47), the same tagging that px4_drv uses for the IT930x.
