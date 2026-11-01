// SPDX-License-Identifier: GPL-2.0-only
// Round-robin packet multiplexer. Moves whole 188-byte packets from N channel
// FIFOs into one byte stream and tags each packet by rewriting its sync byte
// to ((ch + 1) << 4) | 0x07, the same scheme px4_drv uses for the IT930x
// (0x17, 0x27, 0x37, 0x47 for channels 0-3).
module ts_mux #(
    parameter N = 4
) (
    input  wire         clk,
    input  wire         rst,
    input  wire [N-1:0] pkt_ready,
    output reg  [N-1:0] rd_en,
    input  wire [8*N-1:0] rd_byte,   // channel FIFO outputs, valid 1 cycle after rd_en
    output reg          out_valid,
    output reg  [7:0]   out_byte,
    input  wire         out_ready,   // sink can take 188 more bytes
    output reg  [32*N-1:0] pkt_cnt   // packets forwarded per channel
);
    localparam PKT = 188;

    reg [1:0]  ch;          // current / next channel (N <= 4)
    reg        busy;
    reg [7:0]  cnt;         // bytes requested so far
    reg        rd_d;        // a byte was requested last cycle
    reg        first_d;
    reg [1:0]  ch_d;
    reg        rd_q, first_q;   // request aligned with the FIFO's registered output
    reg [1:0]  ch_q;

    integer i, j;
    reg [1:0] pick;
    reg       found;

    // next channel with a packet, searching from ch + 1 (round robin)
    always @(*) begin
        found = 1'b0;
        pick  = ch;
        for (i = 1; i <= N; i = i + 1)
            if (!found && pkt_ready[(ch + i) % N]) begin
                found = 1'b1;
                pick  = (ch + i) % N;
            end
    end

    always @(posedge clk) begin
        rd_en     <= {N{1'b0}};
        out_valid <= 1'b0;
        if (rst) begin
            ch    <= 2'd0;
            busy  <= 1'b0;
            cnt   <= 8'd0;
            rd_d  <= 1'b0;
            pkt_cnt <= {32*N{1'b0}};
        end else begin
            rd_d    <= 1'b0;
            // count a packet the cycle after it was picked (ch is registered)
            for (j = 0; j < N; j = j + 1)
                if (busy && cnt == 8'd0 && ch == j)
                    pkt_cnt[32*j +: 32] <= pkt_cnt[32*j +: 32] + 32'd1;
            if (!busy) begin
                if (found && out_ready) begin
                    ch    <= pick;
                    busy  <= 1'b1;
                    cnt   <= 8'd0;
                end
            end else begin
                rd_en[ch] <= 1'b1;
                rd_d      <= 1'b1;
                first_d   <= (cnt == 8'd0);
                ch_d      <= ch;
                cnt       <= cnt + 8'd1;
                if (cnt == PKT - 1)
                    busy <= 1'b0;
            end
            // FIFO data appears one cycle after rd_en (registered) -> two cycles after rd_d set
            if (rd_q) begin
                out_valid <= 1'b1;
                out_byte  <= first_q ? {1'b0, {1'b0, ch_q} + 3'd1, 4'h7} : rd_byte[8*ch_q +: 8];
            end
        end
    end

    always @(posedge clk) begin
        rd_q    <= rst ? 1'b0 : rd_d;
        first_q <= first_d;
        ch_q    <= ch_d;
    end
endmodule
