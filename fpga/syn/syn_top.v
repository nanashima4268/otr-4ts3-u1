// SPDX-License-Identifier: GPL-2.0-only
// Synthesis-only wrapper to check resources and Fmax on the iCE40HX4K-TQ144
// (HX8K die). Drop counters are folded so that the design fits the pin count.
module syn_top (
    input  wire       clk,
    input  wire       rst,
    input  wire [3:0] ts_clk, ts_valid, ts_sync, ts_data, ts_rst,
    output wire       out_valid,
    output wire [7:0] out_byte,
    input  wire       out_ready,
    output wire       drop_any
);
    wire [63:0] drop_cnt;
    otr_ts_core core (
        .clk(clk), .rst(rst), .ts_clk(ts_clk), .ts_valid(ts_valid), .ts_sync(ts_sync),
        .ts_data(ts_data), .ts_rst(ts_rst), .out_valid(out_valid), .out_byte(out_byte),
        .out_ready(out_ready), .drop_cnt(drop_cnt)
    );
    assign drop_any = |drop_cnt;
endmodule
