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
- After the fix below, a full build (TS core + FX3 writer) used 21% of the logic cells (1614/7680), 10 of 32 BRAMs, and 48 of 107 IOs. Fmax: system clock 99 MHz (target 50 MHz), TS clocks 140-151 MHz. For the current build with the control registers, see "Synthesis" below.

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

## Control registers (spi_regs)

After configuration, the four iCE40 configuration SPI pins (TQ144 pins 67 SDO, 68 SDI, 70 SCK, 71 SS_B) become user I/O. `spi_regs` uses them as a register port for the FX3 (D-47).

- One transaction is SS low, a command byte, 4 data bytes MSB first, then SS high. The command byte is `addr` for a write or `0x80 | addr` for a read. SPI mode 3.
- The slave oversamples SCK with the 50 MHz system clock, so SCK must be at most clk/8. The firmware configures the FPGA at 20 MHz and accesses registers at 4 MHz (`otr_fpga.c`).
- A read value is captured when the command byte completes. A frame that ends before the 40th bit is discarded.
- The bus is shared with the FX3 boot flash (D-49). MISO is therefore driven only while SS is low (`spi_miso_oe`), and the top level maps it to a tri-state SB_IO. The test checks that MISO is high-Z while deselected.

| Address | Name | Access | Content |
|---|---|---|---|
| 0x00 | ID | R | `0x4F545231` ("OTR1") |
| 0x01 | VERSION | R | `[31:16]` major, `[15:0]` minor (currently 1.0) |
| 0x02 | CH_ENABLE | R/W | Bits 0-3: channel enables. All 0 after reset |
| 0x03 | STATUS | R | Bit 0: FX3 FLAGA (a DMA buffer is ready). Bit 1: path reset pending |
| 0x04-0x07 | DROP_CNT[0..3] | R | Packets dropped because a channel FIFO was full (16 bits, wraps) |
| 0x08 | GPIO_OUT | R/W | 8 general outputs, reserved for the case where the FX3 runs out of GPIOs. 0 after reset |
| 0x09 | SCRATCH | R/W | Link test |
| 0x0A | CTRL | W | Bit 0: path reset (D-50). Reads 0 |
| 0x0C-0x0F | PKT_CNT[0..3] | R | Packets forwarded to the FX3 per channel (32 bits, wraps) |

Unmapped addresses read 0. Writes to read-only registers are ignored.

A disabled channel's serial receiver is held in reset, and the mux reads out and discards the packets still in that channel's FIFO (they are not counted in PKT_CNT). An unfinished packet in its FIFO is discarded at the next start of packet, so turning a channel off or on in the middle of a packet never produces a malformed packet. After reset, the receiver also needs SYNC to go low before it counts a packet start, because a SYNC that is already high when reset is released (the 8-bit SYNC style) would otherwise start a packet in the middle of a byte.

`sim/tb_spi.v` checks itself. It drives the registers over SPI the way the FX3 does, while four channels carry synthetic packets that hold a sequence number and a payload derived from it, so any truncated or merged packet shows up as a mismatch. It checks:

- ID, VERSION, STATUS, unmapped addresses, write and read-back, an aborted frame, and a write to a read-only register
- no output while disabled
- channels 1 and 3 turned off in the middle of a packet stop, while channels 0 and 2 keep running
- channels 1 and 3 resume when turned back on
- PKT_CNT and DROP_CNT read over SPI agree with the packets that actually came out

```sh
iverilog -g2012 -o tbs.vvp <repo>/fpga/sim/tb_spi.v <repo>/fpga/rtl/*.v
vvp -n tbs.vvp                  # 4 MHz SCK; +sck_half=80 for 6.25 MHz
```

Result (2026-11-01): PASS at 4, 6.25, and 8.3 MHz. Two deliberately broken versions both fail the test, which shows that it catches errors: enable not gating the receiver, and MISO one bit early. The earlier tests (`tb_ts_core` with and without `+stall`, and `tb_gpif`) still pass. The drop counts (2/4/8/10) now come through the clock-domain crossing.

## Synthesis

`rtl/otr_top.v` is the design top: the TS core, the FX3 writer, the control registers, and a power-on reset. Pin constraints come with the schematic.

```sh
yosys -p "read_verilog rtl/*.v; synth_ice40 -top otr_top -json top.json"
nextpnr-ice40 --hx8k --package tq144:4k --json top.json --pcf-allow-unconstrained --pre-pack syn/clocks.py
```

Result (2026-11-01):

| Resource | Used |
|---|---|
| Logic cells | 31% (2435/7680) |
| BRAMs | 10/32 |
| I/Os | 54/107 |

Fmax is 84-87 MHz for the system clock (target 50 MHz) and 128-141 MHz for the TS clocks.

The packet counters count in the system clock domain, where the mux forwards packets. When they were counted in the TS clock domain, the TS clock Fmax dropped to about 110 MHz.

## Stream stop and start (path reset, D-50)

When the stream stops, the FX3 discards its partly filled DMA buffer. The FPGA writer, however, still counts the words it has written into that buffer. After a restart, its buffer boundaries would no longer match the FX3's, and it would write past a full buffer whenever USB backs up.

Setting CTRL bit 0 does a path reset:
1. The mux is held.
2. Once no packet has been in flight for 8 clocks, `gpif_sfifo_wr` (its word FIFO and counters) is reset.
3. STATUS bit 1 clears.

Only whole packets are ever in the writer at that point, so nothing is split.

otrd uses this order:

| Step | Sequence |
|---|---|
| Start | PATH_RESET, wait until STATUS bit 1 = 0, STREAM 1, CH_ENABLE |
| Stop | CH_ENABLE = 0, STREAM 0 |

When the last receiver stops, at most one partial buffer (< 16 KiB, a few ms) at the end of the stream is lost. That is the cost of not using PKTEND.

`sim/tb_path.v` tests this on the whole design: `otr_top`, the FX3 model, and SPI.
- The FX3 model drops its partial buffer when the stream stops.
- Only committed buffers are checked, which is what the host sees.
- The test runs four start/stop cycles, stopping at odd points.

```sh
iverilog -g2012 -o tbp.vvp <repo>/fpga/sim/tb_path.v <repo>/fpga/sim/fx3_sfifo_model.v <repo>/fpga/rtl/*.v
vvp -n tbp.vvp                  # +no_path_reset must fail
```

Result (2026-11-01): PASS. Every packet was whole, tagged, and in sequence, and there were 0 overruns. With `+no_path_reset`, the test fails with misaligned packets and 83 overruns.

The other tests still pass: `tb_ts_core` (with and without stall), `tb_gpif`, and `tb_spi`. The synthesis uses 31% of the logic cells. Fmax is 85 MHz for the system clock and 134-141 MHz for the TS clocks.
