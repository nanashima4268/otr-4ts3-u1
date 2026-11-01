// SPDX-License-Identifier: GPL-2.0-only
// Dual-clock packet FIFO. The write side commits only complete 188-byte
// packets, so the read side never sees a partial or malformed packet.
// A packet that would not fit is dropped whole and counted.
module ts_pkt_fifo #(
    parameter AW = 10                 // 2^AW bytes (1024 = 2 iCE40 BRAMs)
) (
    // write side: demodulator TS clock domain
    input  wire       wclk,
    input  wire       wrst,
    input  wire       w_stb,
    input  wire [7:0] w_byte,
    input  wire       w_sop,
    output reg  [15:0] drop_cnt,
    // read side: system clock domain
    input  wire       rclk,
    input  wire       rrst,
    output wire       r_pkt_ready,    // at least one whole packet is stored
    input  wire       r_en,
    output reg  [7:0] r_byte
);
    localparam PKT = 188;

    reg [7:0] mem [0:(1<<AW)-1];

    // ---- write domain ----
    reg [AW:0] wptr_commit, wptr_work;
    reg [7:0]  wcount;
    reg        wactive;
    reg [AW:0] rptr_gray_w1, rptr_gray_w2;
    reg [AW:0] rptr_gray_r;           // read pointer (gray), owned by the read domain

    function [AW:0] g2b(input [AW:0] g);
        integer i;
        begin
            g2b[AW] = g[AW];
            for (i = AW-1; i >= 0; i = i - 1) g2b[i] = g2b[i+1] ^ g[i];
        end
    endfunction

    // Pipelined for Fmax: gray->binary, then the room check, each in its own
    // register stage. A stale value only under-reports room (the read pointer
    // only moves forward), and a new packet starts at least 8 clocks after a
    // commit, so `room` is always current by then.
    reg [AW:0] rptr_w;
    reg        room;
    // keep the subtraction at pointer width so that it wraps correctly
    wire [AW:0] used_w = wptr_commit - rptr_w;

    always @(posedge wclk) begin
        rptr_gray_w1 <= rptr_gray_r;
        rptr_gray_w2 <= rptr_gray_w1;
        rptr_w       <= g2b(rptr_gray_w2);
        room         <= used_w <= ((1<<AW) - PKT);
        if (wrst) begin
            wptr_commit <= 0;
            wptr_work   <= 0;
            wcount      <= 0;
            wactive     <= 1'b0;
            drop_cnt    <= 0;
        end else if (w_stb) begin
            if (w_sop) begin
                // a new packet discards any unfinished one
                if (room) begin
                    mem[wptr_commit[AW-1:0]] <= w_byte;
                    wptr_work <= wptr_commit + 1'b1;
                    wcount    <= 8'd1;
                    wactive   <= 1'b1;
                end else begin
                    wactive  <= 1'b0;
                    drop_cnt <= drop_cnt + 1'b1;
                end
            end else if (wactive) begin
                mem[wptr_work[AW-1:0]] <= w_byte;
                wptr_work <= wptr_work + 1'b1;
                wcount    <= wcount + 8'd1;
                if (wcount == PKT - 1) begin
                    wptr_commit <= wptr_work + 1'b1;
                    wactive     <= 1'b0;
                end
            end
        end
    end

    wire [AW:0] wcommit_gray = wptr_commit ^ (wptr_commit >> 1);
    reg  [AW:0] wcommit_gray_q;
    always @(posedge wclk) wcommit_gray_q <= wcommit_gray;

    // ---- read domain ----
    reg [AW:0] rptr;
    reg [AW:0] wgray_r1, wgray_r2;

    // Pipelined the same way. Packets are committed whole, so a ready flag
    // that lags the read pointer by a few bytes still never reports a
    // partial packet (the overcount is always < PKT).
    reg [AW:0] wptr_r;
    reg        pkt_ready_q;
    wire [AW:0] avail_r = wptr_r - rptr;      // pointer width: wraps correctly
    assign r_pkt_ready = pkt_ready_q;

    always @(posedge rclk) begin
        wgray_r1    <= wcommit_gray_q;
        wgray_r2    <= wgray_r1;
        wptr_r      <= g2b(wgray_r2);
        pkt_ready_q <= rrst ? 1'b0 : avail_r >= PKT;
        if (rrst) begin
            rptr        <= 0;
            rptr_gray_r <= 0;
        end else if (r_en) begin
            rptr        <= rptr + 1'b1;
            rptr_gray_r <= (rptr + 1'b1) ^ ((rptr + 1'b1) >> 1);
        end
        r_byte <= mem[rptr[AW-1:0]];
    end
endmodule
