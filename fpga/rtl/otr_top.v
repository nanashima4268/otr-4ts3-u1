// SPDX-License-Identifier: GPL-2.0-only
// OTR-4TS3-U1 FPGA top (iCE40HX4K-TQ144, HX8K die): four serial TS inputs ->
// otr_ts_core -> FX3 slave FIFO writer, plus the control registers on the
// configuration SPI pins (spi_regs). Pin constraints: syn/otr_top.pcf,
// generated from the schematic pin plan (hw/gen/design.py).
module otr_top (
    input  wire        clk,            // 50 MHz oscillator, also PCLK (D-39)
    input  wire [3:0]  ts_clk, ts_valid, ts_sync, ts_data,
    output wire        slcs_n, slwr_n, slrd_n, sloe_n, pktend_n,
    output wire [1:0]  fifo_addr,
    output wire [15:0] dq,
    input  wire        flaga, flagb,
    input  wire        spi_sck, spi_ss_n, spi_mosi,
    output wire        spi_miso,       // tri-stated unless SS is low (shared with the boot flash, D-49)
    output wire [3:0]  gpio_out        // [0] status LED, [1..3] test pads (hw/gen pin plan)
);
    // power-on reset (iCE40 flip-flops start at 0 after configuration)
    reg [7:0] por = 8'd0;
    always @(posedge clk) if (!(&por)) por <= por + 8'd1;
    wire rst = !(&por);

    // reset synchronised into each TS clock domain (releases once the
    // demodulator's TS clock runs)
    wire [3:0] ts_rst;
    genvar i;
    generate for (i = 0; i < 4; i = i + 1) begin : trst
        reg [1:0] r = 2'b11;
        always @(posedge ts_clk[i] or posedge rst)
            if (rst) r <= 2'b11; else r <= {r[0], 1'b0};
        assign ts_rst[i] = r[1];
    end endgenerate

    wire         v, rdy;
    wire [7:0]   b;
    wire [3:0]   ch_enable;
    wire [63:0]  drop_cnt;
    wire [127:0] pkt_cnt;
    reg  [1:0]   flaga_s;
    always @(posedge clk) flaga_s <= {flaga_s[0], flaga};

    // Path reset (CTRL bit 0, D-50): with the FX3 stream stopped, the host
    // requests a reset of the FX3 writer so that its word count starts at a
    // DMA buffer boundary again. The mux is held, the reset waits until no
    // packet is in flight (only whole packets are ever in the writer), then
    // the writer is reset. STATUS bit 1 reads 1 while the reset is pending.
    wire       path_req, core_idle;
    reg        path_pending;
    reg [2:0]  path_cnt;
    reg        wr_rst;
    always @(posedge clk) begin
        wr_rst <= 1'b0;
        if (rst) begin
            path_pending <= 1'b0;
            path_cnt     <= 3'd0;
        end else if (path_req) begin
            path_pending <= 1'b1;
            path_cnt     <= 3'd0;
        end else if (path_pending) begin
            // idle for 8 consecutive clocks: the last byte has reached the writer
            path_cnt <= core_idle ? path_cnt + 3'd1 : 3'd0;
            if (core_idle && path_cnt == 3'd7) begin
                wr_rst       <= 1'b1;
                path_pending <= 1'b0;
            end
        end
    end

    otr_ts_core core (
        .clk(clk), .rst(rst), .ts_clk(ts_clk), .ts_valid(ts_valid), .ts_sync(ts_sync),
        .ts_data(ts_data), .ts_rst(ts_rst), .ch_enable(ch_enable),
        .out_valid(v), .out_byte(b), .out_ready(rdy), .drop_cnt(drop_cnt), .pkt_cnt(pkt_cnt),
        .hold(path_pending), .idle(core_idle)
    );
    gpif_sfifo_wr wr (
        .clk(clk), .rst(rst | wr_rst), .in_valid(v), .in_byte(b), .in_ready(rdy),
        .slcs_n(slcs_n), .slwr_n(slwr_n), .slrd_n(slrd_n), .sloe_n(sloe_n), .pktend_n(pktend_n),
        .fifo_addr(fifo_addr), .dq(dq), .flaga(flaga), .flagb(flagb)
    );
    wire [7:0] gpio_full;
    assign gpio_out = gpio_full[3:0];
    wire miso_d, miso_oe;
    assign spi_miso = miso_oe ? miso_d : 1'bz;
    spi_regs regs (
        .clk(clk), .rst(rst),
        .spi_sck(spi_sck), .spi_ss_n(spi_ss_n), .spi_mosi(spi_mosi),
        .spi_miso(miso_d), .spi_miso_oe(miso_oe),
        .ch_enable(ch_enable), .gpio_out(gpio_full), .path_reset(path_req),
        .drop_cnt(drop_cnt), .pkt_cnt(pkt_cnt), .status({30'd0, path_pending, flaga_s[1]})
    );
endmodule
