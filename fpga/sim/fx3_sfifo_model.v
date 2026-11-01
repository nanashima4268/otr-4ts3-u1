// SPDX-License-Identifier: GPL-2.0-only
// Behavioural model of the FX3 synchronous slave FIFO (write direction,
// thread 0, 16-bit). It models the DMA buffer filling, the 3-cycle flag
// latency (TRM Figure 7-52), buffer switch delays and occasional long USB
// stalls. Writes into a full buffer are counted as overruns.
`timescale 1ns/1ps
module fx3_sfifo_model #(
    parameter BUFW = 1024,        // words per DMA buffer
    parameter WM   = 8            // FLAGB watermark: words of space left when FLAGB falls
) (
    input  wire        pclk,
    input  wire        slcs_n,
    input  wire        slwr_n,
    input  wire [15:0] dq,
    output wire        flaga,
    output wire        flagb,
    output reg  [31:0] overruns,
    output reg  [31:0] words
);
    integer remaining = BUFW;
    integer wait_cnt  = 0;
    integer seed      = 7;
    reg     long_stalls = 1;
    initial if ($test$plusargs("no_stall")) long_stalls = 0;
    reg [2:0] fa_d = 3'b111, fb_d = 3'b111;
    assign flaga = fa_d[2];
    assign flagb = fb_d[2];

    integer fo;
    initial begin
        overruns = 0; words = 0;
        fo = $fopen("out.hex", "w");
    end

    always @(posedge pclk) begin
        if (!slcs_n && !slwr_n) begin
            if (remaining == 0) overruns <= overruns + 1;
            else begin
                remaining = remaining - 1;
                words <= words + 1;
                $fwrite(fo, "%02x\n%02x\n", dq[7:0], dq[15:8]);
            end
        end
        // buffer switch: once full, a new buffer becomes available after a delay
        if (remaining == 0) begin
            if (wait_cnt == 0)
                wait_cnt = (long_stalls && ($random(seed) & 63) == 0) ? 3000 : 1 + ($random(seed) & 31);
            else if (wait_cnt == 1) begin
                remaining = BUFW;
                wait_cnt  = 0;
            end else
                wait_cnt = wait_cnt - 1;
        end
        fa_d <= {fa_d[1:0], remaining > 0};
        fb_d <= {fb_d[1:0], remaining > WM};
    end

    task close_out(input [16*4-1:0] drops);
        begin
            $fwrite(fo, "// drops %0d %0d %0d %0d\n", drops[15:0], drops[31:16], drops[47:32], drops[63:48]);
            $fclose(fo);
        end
    endtask
endmodule
