// SPDX-License-Identifier: GPL-2.0-only
// Self-checking testbench for stream stop/start alignment (D-50): otr_top with
// four synthetic TS channels, the FX3 slave FIFO model, and the control
// registers driven over SPI in the order otrd uses:
//   start: PATH_RESET (wait STATUS bit 1 = 0) -> STREAM 1 -> CH_ENABLE
//   stop:  CH_ENABLE = 0 -> STREAM 0 (the FX3 drops its partial buffer)
// Only committed (full) FX3 buffers are checked, as the host sees them.
// Every packet must be whole, tagged, and in sequence per channel; the FX3
// model must see no overruns. +no_path_reset skips the reset and must fail.
//   iverilog -g2012 -o tbp.vvp tb_path.v fx3_sfifo_model.v ../rtl/*.v && vvp -n tbp.vvp
`timescale 1ns/1ps
module tb_path;
    localparam N = 4;
    localparam BUFW = 8192;

    reg clk = 0;
    always #10 clk = ~clk;          // 50 MHz system clock / PCLK

    reg [N-1:0] ts_clk = 0;
    always #15.0 ts_clk[0] = ~ts_clk[0];
    always #12.5 ts_clk[1] = ~ts_clk[1];
    always #8.0  ts_clk[2] = ~ts_clk[2];
    always #6.5  ts_clk[3] = ~ts_clk[3];
    reg [N-1:0] ts_valid = 0, ts_sync = 0, ts_data = 0;

    wire slcs_n, slwr_n, slrd_n, sloe_n, pktend_n, flaga, flagb;
    wire [1:0]  fifo_addr;
    wire [15:0] dq;
    reg  sck = 1, ss_n = 1, mosi = 0;
    wire miso;
    wire [7:0] gpio_out;
    reg  gpif_on = 0;
    wire commit;
    wire [31:0] overruns, words;

    otr_top dut (
        .clk(clk), .ts_clk(ts_clk), .ts_valid(ts_valid), .ts_sync(ts_sync), .ts_data(ts_data),
        .slcs_n(slcs_n), .slwr_n(slwr_n), .slrd_n(slrd_n), .sloe_n(sloe_n), .pktend_n(pktend_n),
        .fifo_addr(fifo_addr), .dq(dq), .flaga(flaga), .flagb(flagb),
        .spi_sck(sck), .spi_ss_n(ss_n), .spi_mosi(mosi), .spi_miso(miso), .gpio_out(gpio_out)
    );
    fx3_sfifo_model #(.BUFW(BUFW)) fx3 (
        .pclk(clk), .slcs_n(slcs_n), .slwr_n(slwr_n), .dq(dq),
        .flaga(flaga), .flagb(flagb), .overruns(overruns), .words(words),
        .gpif_on(gpif_on), .commit(commit)
    );

    integer errors = 0;
    task fail(input [8*64-1:0] msg); begin errors = errors + 1; $display("FAIL @%0t: %0s", $time, msg); end endtask

    // ---- synthetic packets (same format as tb_spi) ----
    function [7:0] pbyte(input integer c, input [31:0] seq, input integer i);
        case (i)
            0: pbyte = 8'h47;
            1: pbyte = 8'h01;
            2: pbyte = c;
            3: pbyte = 8'h10 | (seq & 15);
            4: pbyte = seq[31:24];
            5: pbyte = seq[23:16];
            6: pbyte = seq[15:8];
            7: pbyte = seq[7:0];
            default: pbyte = seq * 7 + i + c * 13;
        endcase
    endfunction

    genvar g;
    generate for (g = 0; g < N; g = g + 1) begin : drv
        integer b, k, seed;
        reg [31:0] seq;
        reg [7:0]  cur;
        initial begin
            seed = 51 + g;
            seq  = 0;
            repeat (400) @(posedge ts_clk[g]);   // after the power-on reset
            forever begin
                for (b = 0; b < 188; b = b + 1) begin
                    cur = pbyte(g, seq, b);
                    for (k = 7; k >= 0; k = k - 1) begin
                        while (($random(seed) & 15) == 0) begin
                            @(negedge ts_clk[g]); ts_valid[g] = 0; ts_sync[g] = 0;
                        end
                        @(negedge ts_clk[g]);
                        ts_valid[g] = 1;
                        ts_data[g]  = cur[k];
                        ts_sync[g]  = (b == 0) && (g % 2 == 0 ? k == 7 : 1'b1);
                    end
                end
                @(negedge ts_clk[g]); ts_valid[g] = 0; ts_sync[g] = 0;
                repeat ($random(seed) & 15) @(negedge ts_clk[g]);
                seq = seq + 1;
            end
        end
    end endgenerate

    // ---- checker on committed buffers ----
    reg [7:0]  pk [0:187];
    integer    pos = 0;
    integer    got [0:N-1];
    reg [31:0] last_seq [0:N-1];
    reg        seen [0:N-1];
    integer    c, i, w, bi;
    reg [31:0] s;
    reg [7:0]  by;
    initial for (c = 0; c < N; c = c + 1) begin got[c] = 0; seen[c] = 0; end

    task take_byte(input [7:0] v);
        begin
            pk[pos] = v;
            pos = pos + 1;
            if (pos == 188) begin
                pos = 0;
                c = (pk[0] >> 4) - 1;
                if ((pk[0] & 8'h0F) != 8'h07 || c < 0 || c >= N || pk[2] != c) begin
                    fail("bad tag or PID (misaligned stream)");
                end else begin
                    s = {pk[4], pk[5], pk[6], pk[7]};
                    for (i = 8; i < 188; i = i + 1)
                        if (pk[i] != pbyte(c, s, i)) begin fail("payload mismatch"); i = 188; end
                    if (seen[c] && s <= last_seq[c]) fail("sequence not increasing");
                    seen[c] = 1;
                    last_seq[c] = s;
                    got[c] = got[c] + 1;
                end
            end
        end
    endtask

    always @(posedge clk) if (commit) begin
        for (w = 0; w < BUFW; w = w + 1) begin
            take_byte(fx3.buf_mem[w][7:0]);
            take_byte(fx3.buf_mem[w][15:8]);
        end
    end

    // ---- SPI master (mode 3, 4 MHz) ----
    integer sck_half = 125;
    task spi_xfer(input [7:0] cmd, input [31:0] wdata, output [31:0] rdata);
        reg [39:0] tx;
        integer n;
        begin
            tx = {cmd, wdata};
            rdata = 0;
            ss_n = 0;
            #(sck_half);
            for (n = 0; n < 40; n = n + 1) begin
                sck = 0; mosi = tx[39 - n];
                #(sck_half);
                sck = 1;
                if (n >= 8) rdata = {rdata[30:0], miso};
                #(sck_half);
            end
            ss_n = 1;
            #(sck_half * 2);
        end
    endtask
    task reg_wr(input [6:0] a, input [31:0] v); reg [31:0] d; spi_xfer({1'b0, a}, v, d); endtask
    task reg_rd(input [6:0] a, output [31:0] v); spi_xfer({1'b1, a}, 32'h0, v); endtask

    reg skip_reset = 0;
    task stream_start;
        reg [31:0] st;
        integer tries;
        begin
            if (!skip_reset) begin
                reg_wr(7'h0A, 32'h1);                   // CTRL: PATH_RESET
                tries = 0;
                st = 32'h2;
                while (st[1] && tries < 10) begin reg_rd(7'h03, st); tries = tries + 1; end
                if (st[1]) fail("path reset did not complete");
            end
            gpif_on = 1;                                // STREAM 1
            reg_wr(7'h02, 32'hF);                       // CH_ENABLE
        end
    endtask
    task stream_stop;
        begin
            reg_wr(7'h02, 32'h0);
            gpif_on = 0;                                // STREAM 0: partial buffer dropped
            pos = 0;                                    // the host never sees that tail
        end
    endtask

    integer cycle;
    initial begin
        if ($test$plusargs("no_path_reset")) skip_reset = 1;
        #20_000;                                        // power-on reset (256 clocks)
        for (cycle = 0; cycle < 4; cycle = cycle + 1) begin
            stream_start;
            #(1_500_000 + cycle * 370_000);             // a few buffers, stop at an odd point
            stream_stop;
            #(50_000);
        end
        $display("packets: %0d %0d %0d %0d, FX3 words %0d, overruns %0d",
                 got[0], got[1], got[2], got[3], words, overruns);
        if (overruns != 0) fail("FX3 overruns (writer out of step with the DMA buffers)");
        for (c = 0; c < N; c = c + 1) if (got[c] == 0) fail("channel produced nothing");
        if (errors == 0) $display("PASS"); else $display("FAIL (%0d errors)", errors);
        $finish;
    end
endmodule
