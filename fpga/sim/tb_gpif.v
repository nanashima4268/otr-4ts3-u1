// SPDX-License-Identifier: GPL-2.0-only
// Testbench: replays real TS packets (hex files) on four serial TS inputs with
// different clock rates, random VALID gaps and SYNC styles, and dumps the
// multiplexed output for tb_check.py.
`timescale 1ns/1ps
module tb_gpif;
    localparam N = 4;
    localparam NPKT = 400;          // packets per channel in the hex files
    localparam TRUNC_CH = 1, TRUNC_AT = 100, TRUNC_LEN = 100;   // malformed packet injection

    reg clk = 0, rst = 1;
    always #10 clk = ~clk;          // 50 MHz system clock = PCLK (D-39)

    reg [N-1:0] ts_clk = 0;
    always #15.0 ts_clk[0] = ~ts_clk[0];   // ~33 MHz
    always #12.5 ts_clk[1] = ~ts_clk[1];   //  40 MHz
    always #8.0  ts_clk[2] = ~ts_clk[2];   // ~62 MHz
    always #6.5  ts_clk[3] = ~ts_clk[3];   // ~77 MHz

    reg [N-1:0] ts_valid = 0, ts_sync = 0, ts_data = 0, ts_rst = {N{1'b1}};
    wire out_ready;
    wire out_valid;
    wire [7:0] out_byte;
    wire [16*N-1:0] drop_cnt;

    otr_ts_core #(.N(N)) dut (
        .clk(clk), .rst(rst),
        .ts_clk(ts_clk), .ts_valid(ts_valid), .ts_sync(ts_sync), .ts_data(ts_data), .ts_rst(ts_rst),
        .out_valid(out_valid), .out_byte(out_byte), .out_ready(out_ready), .drop_cnt(drop_cnt)
    );

    wire slcs_n, slwr_n, slrd_n, sloe_n, pktend_n, flaga, flagb;
    wire [1:0] fifo_addr;
    wire [15:0] dq;
    wire [31:0] overruns, words;
    gpif_sfifo_wr #(.BUFW(1024)) wr (
        .clk(clk), .rst(rst), .in_valid(out_valid), .in_byte(out_byte), .in_ready(out_ready),
        .slcs_n(slcs_n), .slwr_n(slwr_n), .slrd_n(slrd_n), .sloe_n(sloe_n), .pktend_n(pktend_n),
        .fifo_addr(fifo_addr), .dq(dq), .flaga(flaga), .flagb(flagb)
    );
    fx3_sfifo_model fx3 (
        .pclk(clk), .slcs_n(slcs_n), .slwr_n(slwr_n), .dq(dq),
        .flaga(flaga), .flagb(flagb), .overruns(overruns), .words(words)
    );

    reg [7:0] pk0 [0:NPKT*188-1];
    reg [7:0] pk1 [0:NPKT*188-1];
    reg [7:0] pk2 [0:NPKT*188-1];
    reg [7:0] pk3 [0:NPKT*188-1];
    initial begin
        $readmemh("ch0.hex", pk0);
        $readmemh("ch1.hex", pk1);
        $readmemh("ch2.hex", pk2);
        $readmemh("ch3.hex", pk3);
    end

    function [7:0] pkbyte(input integer c, input integer idx);
        case (c)
            0: pkbyte = pk0[idx];
            1: pkbyte = pk1[idx];
            2: pkbyte = pk2[idx];
            default: pkbyte = pk3[idx];
        endcase
    endfunction

    // one serial driver per channel
    reg [N-1:0] done = 0;
    genvar g;
    generate for (g = 0; g < N; g = g + 1) begin : drv
        integer p, b, bit_i, len, seed;
        reg [7:0] cur;
        initial begin
            seed = 17 + g;
            repeat (20) @(posedge ts_clk[g]);
            ts_rst[g] <= 1'b0;
            repeat (5) @(posedge ts_clk[g]);
            for (p = 0; p < NPKT; p = p + 1) begin
                len = (g == TRUNC_CH && p == TRUNC_AT) ? TRUNC_LEN : 188;
                for (b = 0; b < len; b = b + 1) begin
                    cur = pkbyte(g, p*188 + b);
                    for (bit_i = 7; bit_i >= 0; bit_i = bit_i - 1) begin
                        // random idle clocks with VALID low (gated-clock behaviour)
                        while (($random(seed) & 15) == 0) begin
                            @(negedge ts_clk[g]); ts_valid[g] = 0; ts_sync[g] = 0;
                        end
                        @(negedge ts_clk[g]);
                        ts_valid[g] = 1;
                        ts_data[g]  = cur[bit_i];
                        // ch0/1: SYNC on the first bit only; ch2/3: SYNC for the whole first byte
                        ts_sync[g]  = (b == 0) && (g < 2 ? bit_i == 7 : 1'b1);
                    end
                end
                @(negedge ts_clk[g]); ts_valid[g] = 0; ts_sync[g] = 0;
                repeat ($random(seed) & 31) @(negedge ts_clk[g]);
            end
            done[g] = 1;
        end
    end endgenerate

    initial begin
        repeat (10) @(posedge clk);
        rst <= 0;
        wait (&done);
        repeat (20000) @(posedge clk);
        $display("fx3: words=%0d overruns=%0d", words, overruns);
        fx3.close_out(drop_cnt);
        $finish;
    end
endmodule
