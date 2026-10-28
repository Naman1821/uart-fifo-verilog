// -----------------------------------------------------------------------------
// uart_top.v
// UART controller with FIFO buffering on both directions.
//
//            +-----------+     +---------+
//  host ---->|  TX FIFO  |---->| uart_tx |------------------+--> uart_txd
//            +-----------+     +---------+                  |
//                                                 loopback  |
//            +-----------+     +---------+     +-------+    |
//  host <----|  RX FIFO  |<----| uart_rx |<----|  mux  |<---+
//            +-----------+     +---------+     +-------+<------- uart_rxd
//                 ^                 ^
//                 +---- tick16 -----+---- baud_gen (baud_div)
//
// Errors are sticky until the host pulses err_clr:
//   rx_overflow : a byte arrived while the RX FIFO was full (byte dropped)
//   frame_err   : a frame had stop bit = 0 (byte dropped)
// -----------------------------------------------------------------------------
module uart_top #(
    parameter FIFO_DEPTH = 16          // power of 2
) (
    input  wire        clk,
    input  wire        rst_n,

    // configuration
    input  wire [15:0] baud_div,       // baud = f_clk / (16 * baud_div)
    input  wire        loopback_en,    // 1: RX listens to our own TX (self-test)

    // host -> UART (transmit)
    input  wire        tx_wr_en,
    input  wire [7:0]  tx_wr_data,
    output wire        tx_full,
    output wire        tx_idle,        // TX FIFO empty and nothing on the line

    // UART -> host (receive)
    input  wire        rx_rd_en,
    output wire [7:0]  rx_rd_data,     // FWFT: valid whenever rx_empty == 0
    output wire        rx_empty,

    // sticky error flags
    input  wire        err_clr,
    output reg         rx_overflow,
    output reg         frame_err,

    // serial pins
    output wire        uart_txd,
    input  wire        uart_rxd
);

    localparam CW = $clog2(FIFO_DEPTH) + 1;   // FIFO count width

    // ---------------- baud tick ----------------
    wire tick16;

    baud_gen u_baud (
        .clk      (clk),
        .rst_n    (rst_n),
        .baud_div (baud_div),
        .tick16   (tick16)
    );

    // ---------------- transmit path ----------------
    wire [7:0] tx_fifo_data;
    wire       tx_fifo_empty;
    wire       tx_ready;
    wire       tx_pop = tx_ready && !tx_fifo_empty;   // hand next byte to uart_tx
    wire [CW-1:0] tx_count_unused;

    sync_fifo #(.WIDTH(8), .DEPTH(FIFO_DEPTH)) u_tx_fifo (
        .clk     (clk),
        .rst_n   (rst_n),
        .wr_en   (tx_wr_en),
        .wr_data (tx_wr_data),
        .rd_en   (tx_pop),
        .rd_data (tx_fifo_data),
        .full    (tx_full),
        .empty   (tx_fifo_empty),
        .count   (tx_count_unused)
    );

    uart_tx u_tx (
        .clk      (clk),
        .rst_n    (rst_n),
        .tick16   (tick16),
        .tx_valid (!tx_fifo_empty),
        .tx_data  (tx_fifo_data),
        .tx_ready (tx_ready),
        .tx       (uart_txd)
    );

    assign tx_idle = tx_fifo_empty && tx_ready;

    // ---------------- receive path ----------------
    wire       rx_in = loopback_en ? uart_txd : uart_rxd;
    wire [7:0] rx_byte;
    wire       rx_byte_valid;
    wire       rx_frame_err;
    wire       rx_fifo_full;
    wire [CW-1:0] rx_count_unused;

    uart_rx u_rx (
        .clk       (clk),
        .rst_n     (rst_n),
        .tick16    (tick16),
        .rx        (rx_in),
        .rx_data   (rx_byte),
        .rx_valid  (rx_byte_valid),
        .frame_err (rx_frame_err)
    );

    sync_fifo #(.WIDTH(8), .DEPTH(FIFO_DEPTH)) u_rx_fifo (
        .clk     (clk),
        .rst_n   (rst_n),
        .wr_en   (rx_byte_valid),     // dropped by the FIFO itself if full
        .wr_data (rx_byte),
        .rd_en   (rx_rd_en),
        .rd_data (rx_rd_data),
        .full    (rx_fifo_full),
        .empty   (rx_empty),
        .count   (rx_count_unused)
    );

    // ---------------- sticky error flags ----------------
    // A new error in the same cycle as err_clr wins, so no error is ever lost.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rx_overflow <= 1'b0;
            frame_err   <= 1'b0;
        end else begin
            if (rx_byte_valid && rx_fifo_full) rx_overflow <= 1'b1;
            else if (err_clr)                  rx_overflow <= 1'b0;

            if (rx_frame_err)                  frame_err   <= 1'b1;
            else if (err_clr)                  frame_err   <= 1'b0;
        end
    end

endmodule
