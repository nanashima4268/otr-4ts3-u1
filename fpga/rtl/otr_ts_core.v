// SPDX-License-Identifier: GPL-2.0-only
// Four serial TS inputs -> per-channel packet FIFOs -> one tagged byte stream.
// ch_enable (system clock domain) is synchronised into each TS clock domain;
// a disabled channel's receiver is held in reset, so it emits nothing and an
// unfinished packet in its FIFO is discarded at the next start of packet.
module otr_ts_core #(
    parameter N  = 4,
    parameter AW = 10
) (
    input  wire         clk,          // system clock
    input  wire         rst,          // synchronous to clk
    input  wire [N-1:0] ts_clk,
    input  wire [N-1:0] ts_valid,
    input  wire [N-1:0] ts_sync,
    input  wire [N-1:0] ts_data,
    input  wire [N-1:0] ts_rst,       // per-channel reset, synchronous to ts_clk[i]
    input  wire [N-1:0] ch_enable,    // clk domain
    output wire         out_valid,
    output wire [7:0]   out_byte,
    input  wire         out_ready,
    output wire [16*N-1:0] drop_cnt,  // clk domain
    output wire [32*N-1:0] pkt_cnt    // clk domain, packets forwarded by the mux
);
    wire [N-1:0]   pkt_ready, rd_en;
    wire [8*N-1:0] rd_byte;

    genvar i;
    generate for (i = 0; i < N; i = i + 1) begin : ch
        wire       stb, sop;
        wire [7:0] b;
        reg  [1:0] en_s;
        always @(posedge ts_clk[i]) en_s <= {en_s[0], ch_enable[i]};

        ts_serial_rx rx (
            .ts_clk(ts_clk[i]), .rst(ts_rst[i] | ~en_s[1]),
            .ts_valid(ts_valid[i]), .ts_sync(ts_sync[i]), .ts_data(ts_data[i]),
            .byte_stb(stb), .byte_out(b), .byte_sop(sop)
        );

        ts_pkt_fifo #(.AW(AW)) fifo (
            .wclk(ts_clk[i]), .wrst(ts_rst[i]),
            .w_stb(stb), .w_byte(b), .w_sop(sop),
            .rclk(clk), .rrst(rst),
            .r_pkt_ready(pkt_ready[i]), .r_en(rd_en[i]), .r_byte(rd_byte[8*i +: 8]),
            .r_drop_cnt(drop_cnt[16*i +: 16])
        );
    end endgenerate

    ts_mux #(.N(N)) mux (
        .clk(clk), .rst(rst),
        .pkt_ready(pkt_ready), .rd_en(rd_en), .rd_byte(rd_byte),
        .out_valid(out_valid), .out_byte(out_byte), .out_ready(out_ready),
        .pkt_cnt(pkt_cnt)
    );
endmodule
