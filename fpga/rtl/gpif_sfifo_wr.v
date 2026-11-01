// SPDX-License-Identifier: GPL-2.0-only
// Write-only master for the FX3 synchronous slave FIFO (16-bit, thread 0).
// Takes the tagged byte stream from ts_mux, packs it into little-endian
// 16-bit words (FX3 GPIF is little endian: the first byte goes on DQ[7:0])
// and writes them while the FX3 partial flag (FLAGB) reports room.
//
// Flow control by buffer counting. The FX3 commits a DMA buffer to USB only
// when the buffer is full (PKTEND# is not used), so the master must fill
// every buffer exactly. Its flags lag SLWR# by 3 PCLK cycles (TRM Figure
// 7-52). So the master writes exactly BUFW words, waits for the flag latency,
// and resumes only when FLAGA ("thread 0 not full") shows that the next
// buffer is ready. BUFW must equal the firmware's DMA buffer size in 16-bit
// words.
// The write side keeps a small word FIFO so that ts_mux sees the backpressure
// as "room for one more packet".
module gpif_sfifo_wr #(
    parameter AW   = 9,               // word FIFO depth 2^AW (512 x 16 = 2 BRAMs)
    parameter BUFW = 8192             // FX3 DMA buffer size in words (16 KiB)
) (
    input  wire        clk,           // also forwarded to the FX3 as PCLK
    input  wire        rst,
    // byte stream from ts_mux
    input  wire        in_valid,
    input  wire [7:0]  in_byte,
    output wire        in_ready,      // room for at least one more 188-byte packet
    // FX3 slave FIFO pins (active-low strobes)
    output reg         slcs_n,
    output reg         slwr_n,
    output wire        slrd_n,
    output wire        sloe_n,
    output wire        pktend_n,
    output wire [1:0]  fifo_addr,
    output reg  [15:0] dq,
    input  wire        flaga,         // thread 0 not full (a buffer is ready)
    input  wire        flagb          // partial flag, unused
);
    localparam PKT_WORDS = 94;        // 188 bytes

    assign slrd_n    = 1'b1;          // the FPGA never reads from the FX3
    assign sloe_n    = 1'b1;
    assign pktend_n  = 1'b1;          // full buffers only; stop/start alignment is the path reset (D-50)
    assign fifo_addr = 2'b00;

    // ---- byte -> word packing ----
    reg       half;                   // a low byte is waiting
    reg [7:0] lo;
    reg       w_en;
    reg [15:0] w_word;

    always @(posedge clk) begin
        w_en <= 1'b0;
        if (rst) begin
            half <= 1'b0;
        end else if (in_valid) begin
            if (!half) begin
                lo   <= in_byte;
                half <= 1'b1;
            end else begin
                w_word <= {in_byte, lo};
                w_en   <= 1'b1;
                half   <= 1'b0;
            end
        end
    end

    // ---- word FIFO (single clock) ----
    reg [15:0] mem [0:(1<<AW)-1];
    reg [AW:0] wp, rp;
    wire [AW:0] used = wp - rp;
    // ts_mux checks in_ready once per packet, then sends 188 bytes; keep one
    // packet of margin for the bytes already in flight.
    assign in_ready = used <= ((1<<AW) - 2*PKT_WORDS);

    always @(posedge clk) begin
        if (rst) wp <= 0;
        else if (w_en) begin
            mem[wp[AW-1:0]] <= w_word;
            wp <= wp + 1'b1;
        end
    end

    // ---- FX3 write side ----
    // Pipeline: pop (rp++, BRAM read) -> v1/rd_data -> dq/slwr_n.
    localparam LAT_WAIT = 6;          // > FX3 flag latency + our flag register
    reg        flaga_q;
    reg        v1;
    reg [15:0] rd_data;
    reg [15:0] wcnt;                  // words popped into the current buffer
    reg        buf_open;
    reg [3:0]  hold;
    wire       pop = buf_open && (used != 0);

    always @(posedge clk) begin
        flaga_q <= flaga;
        rd_data <= mem[rp[AW-1:0]];
        if (rst) begin
            rp       <= 0;
            v1       <= 1'b0;
            slwr_n   <= 1'b1;
            slcs_n   <= 1'b1;
            buf_open <= 1'b0;
            wcnt     <= 0;
            hold     <= LAT_WAIT;
        end else begin
            slcs_n <= 1'b0;
            if (pop) begin
                rp   <= rp + 1'b1;
                wcnt <= wcnt + 1'b1;
                if (wcnt == BUFW - 1) begin
                    buf_open <= 1'b0;     // buffer full: wait for the switch
                    hold     <= LAT_WAIT;
                end
            end
            if (!buf_open) begin
                if (hold != 0) hold <= hold - 1'b1;
                else if (flaga_q) begin
                    buf_open <= 1'b1;
                    wcnt     <= 0;
                end
            end
            v1     <= pop;
            slwr_n <= !v1;
            if (v1) dq <= rd_data;
        end
    end
endmodule
