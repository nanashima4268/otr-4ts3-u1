// SPDX-License-Identifier: GPL-2.0-only
// Serial TS receiver for one demodulator output (CXD2856ER-style serial TS).
// Runs in the demodulator's TS clock domain. Bits are MSB first and qualified
// by VALID. A rising edge of SYNC marks the first bit of a packet.
// Emits one byte per 8 valid bits, flagging the first byte of each packet.
module ts_serial_rx (
    input  wire       ts_clk,
    input  wire       rst,       // synchronous to ts_clk
    input  wire       ts_valid,
    input  wire       ts_sync,
    input  wire       ts_data,
    output reg        byte_stb,
    output reg  [7:0] byte_out,
    output reg        byte_sop   // first byte of a packet
);
    reg [6:0] shreg;
    reg [2:0] bitcnt;
    reg       sync_d;
    reg       in_pkt;
    reg       first;
    reg [7:0] bytecnt;           // bytes emitted in the current packet

    wire start = ts_valid && ts_sync && !sync_d;

    always @(posedge ts_clk) begin
        byte_stb <= 1'b0;
        if (rst) begin
            // track SYNC during reset: a SYNC that is already high when reset
            // is released (8-bit SYNC style, mid-byte) is not a packet start
            sync_d  <= ts_sync;
            in_pkt  <= 1'b0;
            bitcnt  <= 3'd0;
            bytecnt <= 8'd0;
        end else if (ts_valid) begin
            sync_d <= ts_sync;
            if (start) begin
                shreg   <= {6'd0, ts_data};
                bitcnt  <= 3'd1;
                in_pkt  <= 1'b1;
                first   <= 1'b1;
                bytecnt <= 8'd0;
            end else if (in_pkt) begin
                shreg  <= {shreg[5:0], ts_data};
                bitcnt <= bitcnt + 3'd1;
                if (bitcnt == 3'd7) begin
                    byte_stb <= 1'b1;
                    byte_out <= {shreg, ts_data};
                    byte_sop <= first;
                    first    <= 1'b0;
                    bytecnt  <= bytecnt + 8'd1;
                    if (bytecnt == 8'd187)
                        in_pkt <= 1'b0;   // wait for the next SYNC
                end
            end
        end
    end
endmodule
