// SPDX-License-Identifier: GPL-2.0-only
// Self-checking testbench for spi_regs + otr_ts_core: register access over
// SPI mode 3 as the FX3 does it (otr_fpga.c OtrFpgaReg), and CH_ENABLE
// switching while the four channels carry synthetic packets.
//   iverilog -g2012 -o tbs.vvp tb_spi.v ../rtl/*.v && vvp -n tbs.vvp [+sck_half=80]
// Each packet: 0x47, PID 0x100+ch, CC, a 32-bit sequence number, then a
// payload derived from (ch, seq), so any truncated or merged packet is caught.
`timescale 1ns/1ps
module tb_spi;
    localparam N = 4;

    reg clk = 0;
    always #10 clk = ~clk;          // 50 MHz system clock (D-39)
    reg rst = 1;

    reg [N-1:0] ts_clk = 0;
    always #15.0 ts_clk[0] = ~ts_clk[0];
    always #12.5 ts_clk[1] = ~ts_clk[1];
    always #8.0  ts_clk[2] = ~ts_clk[2];
    always #6.5  ts_clk[3] = ~ts_clk[3];

    reg  [N-1:0] ts_valid = 0, ts_sync = 0, ts_data = 0, ts_rst = {N{1'b1}};
    wire         out_valid;
    wire [7:0]   out_byte;
    wire [N-1:0] ch_enable;
    wire [16*N-1:0] drop_cnt;
    wire [32*N-1:0] pkt_cnt;
    wire [7:0]   gpio_out;

    reg  sck = 1, ss_n = 1, mosi = 0;
    wire miso_d, miso_oe;
    wire miso = miso_oe ? miso_d : 1'bz;

    otr_ts_core #(.N(N)) core (
        .clk(clk), .rst(rst), .ts_clk(ts_clk), .ts_valid(ts_valid), .ts_sync(ts_sync),
        .ts_data(ts_data), .ts_rst(ts_rst), .ch_enable(ch_enable),
        .out_valid(out_valid), .out_byte(out_byte), .out_ready(1'b1),
        .drop_cnt(drop_cnt), .pkt_cnt(pkt_cnt), .hold(1'b0), .idle()
    );
    spi_regs #(.N(N)) regs (
        .clk(clk), .rst(rst), .spi_sck(sck), .spi_ss_n(ss_n), .spi_mosi(mosi), .spi_miso(miso_d), .spi_miso_oe(miso_oe),
        .ch_enable(ch_enable), .gpio_out(gpio_out), .drop_cnt(drop_cnt), .pkt_cnt(pkt_cnt),
        .status(32'hA5)
    );

    integer errors = 0;
    task fail(input [8*64-1:0] msg); begin errors = errors + 1; $display("FAIL @%0t: %0s", $time, msg); end endtask

    // ---- synthetic packet drivers ----
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
            seed = 31 + g;
            seq  = 0;
            repeat (20) @(posedge ts_clk[g]);
            ts_rst[g] <= 1'b0;
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
                        // even channels: 1-bit SYNC, odd channels: 8-bit SYNC
                        ts_sync[g]  = (b == 0) && (g % 2 == 0 ? k == 7 : 1'b1);
                    end
                end
                @(negedge ts_clk[g]); ts_valid[g] = 0; ts_sync[g] = 0;
                repeat ($random(seed) & 15) @(negedge ts_clk[g]);
                seq = seq + 1;
            end
        end
    end endgenerate

    // ---- output checker ----
    reg [7:0]  pk [0:187];
    integer    pos = 0;
    integer    got [0:N-1];
    reg [31:0] last_seq [0:N-1];
    reg        seen [0:N-1];
    integer    c, i;
    reg [31:0] s;
    initial for (c = 0; c < N; c = c + 1) begin got[c] = 0; seen[c] = 0; end

    always @(posedge clk) if (out_valid) begin
        pk[pos] = out_byte;
        pos = pos + 1;
        if (pos == 188) begin
            pos = 0;
            c = (pk[0] >> 4) - 1;
            if ((pk[0] & 8'h0F) != 8'h07 || c < 0 || c >= N || pk[2] != c) begin
                fail("bad tag or PID");
            end else begin
                s = {pk[4], pk[5], pk[6], pk[7]};
                for (i = 8; i < 188; i = i + 1)
                    if (pk[i] != pbyte(c, s, i)) begin fail("payload mismatch (malformed packet)"); i = 188; end
                if (seen[c] && s <= last_seq[c]) fail("sequence not increasing");
                seen[c] = 1;
                last_seq[c] = s;
                got[c] = got[c] + 1;
            end
        end
    end

    // ---- SPI master, mode 3, as the FX3 drives it ----
    integer sck_half = 125;          // 4 MHz (D-47); +sck_half=80 -> 6.25 MHz
    task spi_xfer(input [7:0] cmd, input [31:0] wdata, input integer nbits, output [31:0] rdata);
        reg [39:0] tx;
        integer n;
        begin
            tx = {cmd, wdata};
            rdata = 0;
            ss_n = 0;
            #(sck_half);
            for (n = 0; n < nbits; n = n + 1) begin
                sck = 0; mosi = tx[39 - n];          // shift out on the falling edge
                #(sck_half);
                sck = 1;                              // sample on the rising edge
                if (n >= 8) rdata = {rdata[30:0], miso};
                #(sck_half);
            end
            ss_n = 1;
            #(sck_half * 2);
        end
    endtask
    task reg_wr(input [6:0] a, input [31:0] v); reg [31:0] d; spi_xfer({1'b0, a}, v, 40, d); endtask
    task reg_rd(input [6:0] a, output [31:0] v); spi_xfer({1'b1, a}, 32'hFFFF_FFFF, 40, v); endtask
    task expect_rd(input [6:0] a, input [31:0] v);
        reg [31:0] d;
        begin
            reg_rd(a, d);
            if (d !== v) begin
                $display("FAIL @%0t: reg 0x%02x = 0x%08x, expected 0x%08x", $time, a, d, v);
                errors = errors + 1;
            end
        end
    endtask

    integer prev [0:N-1];
    reg [31:0] d;
    initial begin
        if ($value$plusargs("sck_half=%d", sck_half)) ;
        $display("SPI SCK %0d kHz", 1_000_000 / (2 * sck_half));
        repeat (10) @(posedge clk);
        rst <= 0;
        repeat (10) @(posedge clk);

        if (miso !== 1'bz) fail("MISO driven while deselected");
        // identification and plain registers
        expect_rd(7'h00, 32'h4F54_5231);
        expect_rd(7'h01, 32'h0001_0000);
        expect_rd(7'h03, 32'h0000_00A5);
        expect_rd(7'h7F, 32'h0);                      // unmapped reads 0
        reg_wr(7'h09, 32'hDEAD_BEEF); expect_rd(7'h09, 32'hDEAD_BEEF);
        reg_wr(7'h09, 32'h1234_5678); expect_rd(7'h09, 32'h1234_5678);
        spi_xfer(8'h09, 32'hCAFE_F00D, 24, d);        // SS released early: discarded
        expect_rd(7'h09, 32'h1234_5678);
        reg_wr(7'h00, 32'h0);  expect_rd(7'h00, 32'h4F54_5231);   // read-only
        reg_wr(7'h08, 32'h0000_00C3); expect_rd(7'h08, 32'h0000_00C3);
        if (gpio_out !== 8'hC3) fail("gpio_out pin");

        // channels disabled after reset: nothing comes out
        expect_rd(7'h02, 32'h0);
        #200_000;
        for (c = 0; c < N; c = c + 1) if (got[c] != 0) fail("output while disabled");

        reg_wr(7'h02, 32'hF); expect_rd(7'h02, 32'hF);
        #400_000;
        // ch1 and ch3 off (mid-packet), give the FIFOs time to drain
        reg_wr(7'h02, 32'h5);
        #60_000;
        for (c = 0; c < N; c = c + 1) prev[c] = got[c];
        #300_000;
        if (got[1] != prev[1] || got[3] != prev[3]) fail("disabled channel still produced packets");
        if (got[0] == prev[0] || got[2] == prev[2]) fail("enabled channel stalled");
        reg_wr(7'h02, 32'hF);
        #300_000;
        if (got[1] == prev[1] || got[3] == prev[3]) fail("re-enabled channel did not resume");
        reg_wr(7'h02, 32'h0);
        #60_000;

        // counters over SPI agree with what came out
        for (c = 0; c < N; c = c + 1) begin
            expect_rd(7'h0C + c, got[c]);
            expect_rd(7'h04 + c, 32'h0);
        end
        if (pos != 0) fail("partial packet at the end");

        $display("packets: %0d %0d %0d %0d", got[0], got[1], got[2], got[3]);
        if (errors == 0) $display("PASS"); else $display("FAIL (%0d errors)", errors);
        $finish;
    end
endmodule
