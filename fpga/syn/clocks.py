# Timing constraints for nextpnr-ice40 (--pre-pack): 50 MHz system clock,
# TS clocks checked against 100 MHz (the demodulator TS clock is not yet known, R-12).
ctx.addClock("clk", 50)
for i in range(4):
    ctx.addClock("ts_clk[%d]" % i, 100)
