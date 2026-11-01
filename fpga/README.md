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
- After the fix below, a full build (`syn/syn_top.v`: TS core + FX3 writer) uses 21% of the logic cells (1614/7680), 10 of 32 BRAMs, and 48 of 107 IOs. Fmax: system clock 99 MHz (target 50 MHz), TS clocks 140-151 MHz.

## Output format

Each 188-byte packet is passed through whole. Its sync byte is rewritten to `((ch + 1) << 4) | 0x07` (0x17/0x27/0x37/0x47), the same tagging that px4_drv uses for the IT930x.

## FX3 path (gpif_sfifo_wr)

`gpif_sfifo_wr` is a write-only master for the FX3 synchronous slave FIFO (16-bit, thread 0, PCLK = the 50 MHz system clock, D-39).
Flow control works by buffer counting. The FX3 commits a DMA buffer only when it is full, and its flags lag SLWR# by 3 cycles. So the FPGA writes exactly `BUFW` words per buffer, waits for the flag latency, and resumes when FLAGA reports the next buffer ready. `BUFW` must equal the firmware DMA buffer size (8192 words = 16 KiB). The FLAGB partial flag is not used. The first design stopped on FLAGB, which left buffers short of full; they were never committed, so the stream deadlocked.

`sim/tb_gpif.v` + `sim/fx3_sfifo_model.v` simulate the whole path: real TS through the core and the writer into a model of the FX3. The model includes buffer fill, the 3-cycle flag latency, random buffer-switch delays, and occasional 60 us USB stalls. It also counts overruns.
- Result (2026-11-01): all 1,599 packets were bit-exact and in order, with 0 drops and 0 overruns, both with and without stalls (`+no_stall`).

### Bug found and fixed

`ts_pkt_fifo` compared pointer differences in 32-bit context: `(a - b) <= ((1<<AW) - PKT)`. When the write pointer had wrapped, the difference came out as a huge number rather than wrapping, so the FIFO reported "full" and dropped packets (32 per channel in the 50 MHz run). Earlier runs had missed this only by timing luck. The subtractions are now pointer-width wires (`used_w`, `avail_r`).

## Synthetic stimulus and host cross-check

`tb_check.py prep-synth` writes `ch0..3.hex` from a deterministic synthetic generator: no broadcast content, sync 0x47, PID 0x100+ch, an incrementing CC, and an LCG payload. It is the same generator as otr-userland `tests/ts_path_tests.cpp`. The FPGA output (`out.hex` from `tb_gpif`) can then be fed to the host demux:

```sh
python3 tb_check.py prep-synth && vvp -n tbg.vvp && python3 tb_check.py check
OTR_FPGA_SIM_DIR=$PWD <otr-userland>/build/otr_ts_path_tests
```

Result (2026-11-01): the FPGA check passed, and px4-userland's `TaggedTsDemux` (inside otr-userland) recovered all 1,599 packets bit-exact and in order. The tag format is therefore compatible end to end: FPGA, then FX3 model, then host demux.
