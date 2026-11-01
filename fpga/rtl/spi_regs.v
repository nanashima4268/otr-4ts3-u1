// SPDX-License-Identifier: GPL-2.0-only
// FPGA control registers over the iCE40 configuration SPI pins (user I/O after
// configuration). The FX3 is the master (otr_fpga.c OtrFpgaReg):
//   SS low, cmd byte, 4 data bytes MSB first, SS high.
//   cmd = addr (write) or 0x80 | addr (read); during a read the master's data
//   bytes are ignored. SPI mode 3 (sample on the rising edge).
// The slave is oversampled in the system clock domain, so SCK must be
// <= clk / 8 (the firmware uses 4 MHz with the 50 MHz system clock, D-47).
// MISO changes a few system clocks after each rising edge, which leaves almost
// a full SCK period of setup before the master samples it.
// A frame that ends (SS high) before the 40th bit is discarded.
module spi_regs #(
    parameter N       = 4,
    parameter VERSION = 32'h0001_0000          // [31:16] major, [15:0] minor
) (
    input  wire          clk,
    input  wire          rst,
    // SPI pins (asynchronous)
    input  wire          spi_sck,
    input  wire          spi_ss_n,
    input  wire          spi_mosi,
    output reg           spi_miso,
    // registers
    output reg  [N-1:0]  ch_enable,            // 0x02
    output reg  [7:0]    gpio_out,             // 0x08
    input  wire [16*N-1:0] drop_cnt,           // 0x04.. (clk domain)
    input  wire [32*N-1:0] pkt_cnt,            // 0x0C.. (clk domain)
    input  wire [31:0]   status                // 0x03
);
    localparam [31:0] ID = 32'h4F54_5231;      // "OTR1"

    // ---- synchronisers and edge detection ----
    reg [2:0] sck_s;
    reg [1:0] ss_s, mosi_s;
    always @(posedge clk) begin
        sck_s  <= {sck_s[1:0], spi_sck};
        ss_s   <= {ss_s[0], spi_ss_n};
        mosi_s <= {mosi_s[0], spi_mosi};
    end
    wire ss_n  = ss_s[1];
    wire sck_r = sck_s[1] & ~sck_s[2];
    wire mosi  = mosi_s[1];

    // ---- register file ----
    reg [31:0] scratch;                        // 0x09

    function [31:0] rd(input [6:0] a);
        integer i;
        begin
            rd = 32'd0;
            case (a)
                7'h00: rd = ID;
                7'h01: rd = VERSION;
                7'h02: rd = {{(32-N){1'b0}}, ch_enable};
                7'h03: rd = status;
                7'h08: rd = {24'd0, gpio_out};
                7'h09: rd = scratch;
                default: begin
                    for (i = 0; i < N; i = i + 1) begin
                        if (a == 7'h04 + i) rd = {16'd0, drop_cnt[16*i +: 16]};
                        if (a == 7'h0C + i) rd = pkt_cnt[32*i +: 32];
                    end
                end
            endcase
        end
    endfunction

    // ---- frame ----
    reg [5:0]  nbits;        // bits received in this frame (saturates at 40)
    reg [7:0]  cmd;
    reg [31:0] wsh, rsh;

    wire [7:0]  cmd_next = {cmd[6:0], mosi};
    wire [31:0] rd_val   = rd(cmd_next[6:0]);

    always @(posedge clk) begin
        if (rst) begin
            nbits     <= 6'd0;
            spi_miso  <= 1'b0;
            ch_enable <= {N{1'b0}};
            gpio_out  <= 8'd0;
            scratch   <= 32'd0;
        end else if (ss_n) begin
            nbits <= 6'd0;
        end else if (sck_r && nbits != 6'd40) begin
            nbits <= nbits + 6'd1;
            if (nbits < 6'd8) begin
                cmd <= cmd_next;
                if (nbits == 6'd7) begin
                    // command complete: snapshot the read value, present bit 31
                    rsh      <= {rd_val[30:0], 1'b0};
                    spi_miso <= rd_val[31];
                end
            end else begin
                wsh      <= {wsh[30:0], mosi};
                spi_miso <= rsh[31];
                rsh      <= {rsh[30:0], 1'b0};
                if (nbits == 6'd39 && !cmd[7]) begin
                    case (cmd[6:0])
                        7'h02: ch_enable <= {wsh[N-2:0], mosi};
                        7'h08: gpio_out  <= {wsh[6:0], mosi};
                        7'h09: scratch   <= {wsh[30:0], mosi};
                        default: ;
                    endcase
                end
            end
        end
    end
endmodule
