// SPDX-License-Identifier: GPL-2.0-only
// Synthesis-only wrapper to check resources and Fmax on the iCE40HX4K-TQ144
// (HX8K die): four serial TS inputs -> otr_ts_core -> FX3 slave FIFO writer.
module syn_top (
    input  wire        clk,            // 50 MHz oscillator, also PCLK (D-39)
    input  wire        rst,
    input  wire [3:0]  ts_clk, ts_valid, ts_sync, ts_data, ts_rst,
    output wire        slcs_n, slwr_n, slrd_n, sloe_n, pktend_n,
    output wire [1:0]  fifo_addr,
    output wire [15:0] dq,
    input  wire        flaga, flagb,
    output wire        drop_any
);
    wire        v, rdy;
    wire [7:0]  b;
    wire [63:0] drop_cnt;
    otr_ts_core core (
        .clk(clk), .rst(rst), .ts_clk(ts_clk), .ts_valid(ts_valid), .ts_sync(ts_sync),
        .ts_data(ts_data), .ts_rst(ts_rst), .out_valid(v), .out_byte(b),
        .out_ready(rdy), .drop_cnt(drop_cnt)
    );
    gpif_sfifo_wr wr (
        .clk(clk), .rst(rst), .in_valid(v), .in_byte(b), .in_ready(rdy),
        .slcs_n(slcs_n), .slwr_n(slwr_n), .slrd_n(slrd_n), .sloe_n(sloe_n), .pktend_n(pktend_n),
        .fifo_addr(fifo_addr), .dq(dq), .flaga(flaga), .flagb(flagb)
    );
    assign drop_any = |drop_cnt;
endmodule
