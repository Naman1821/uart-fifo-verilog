// -----------------------------------------------------------------------------
// uart_rx.v
// 8N1 UART receiver with 16x oversampling.
//
//  1. rx is asynchronous to clk, so it first passes a 2-flop synchronizer.
//  2. A high->low edge starts a frame. 8 ticks later (middle of the start
//     bit) the line must still be low, otherwise it was a glitch.
//  3. Every 16 ticks after that we are in the middle of the next bit:
//     8 data bits (LSB first), then the stop bit.
//  4. Stop bit = 1 -> rx_valid pulse with the byte.
//     Stop bit = 0 -> frame_err pulse, byte is dropped.
// -----------------------------------------------------------------------------
module uart_rx (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       tick16,      // 16x baud tick
    input  wire       rx,          // asynchronous serial input
    output reg  [7:0] rx_data,     // valid when rx_valid pulses
    output reg        rx_valid,    // 1-cycle pulse: new byte in rx_data
    output reg        frame_err    // 1-cycle pulse: stop bit was 0
);

    localparam [1:0] IDLE  = 2'd0,
                     START = 2'd1,
                     DATA  = 2'd2,
                     STOP  = 2'd3;

    // ---------------- 2-flop synchronizer + edge detect ----------------
    // rx_meta may go metastable; rx_sync has a full clock period to settle.
    reg rx_meta, rx_sync, rx_prev;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rx_meta <= 1'b1;
            rx_sync <= 1'b1;
            rx_prev <= 1'b1;
        end else begin
            rx_meta <= rx;
            rx_sync <= rx_meta;
            rx_prev <= rx_sync;
        end
    end

    // A start bit is an EDGE, not a level: after a framing error the line
    // may still be low, and we must not mistake that for a new start bit.
    wire start_edge = rx_prev & ~rx_sync;

    // ---------------- receive state machine ----------------
    reg [1:0] state;
    reg [3:0] tick_cnt;   // ticks counted inside the current bit
    reg [2:0] bit_idx;    // which data bit we are receiving
    reg [7:0] shift;      // bits arrive LSB first, so shift right

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state     <= IDLE;
            tick_cnt  <= 4'd0;
            bit_idx   <= 3'd0;
            shift     <= 8'd0;
            rx_data   <= 8'd0;
            rx_valid  <= 1'b0;
            frame_err <= 1'b0;
        end else begin
            rx_valid  <= 1'b0;   // default: pulses last one cycle
            frame_err <= 1'b0;

            case (state)
                IDLE: begin
                    if (start_edge) begin
                        tick_cnt <= 4'd0;
                        state    <= START;
                    end
                end

                // Wait half a bit (8 ticks) to reach the middle of the start bit
                START: begin
                    if (tick16) begin
                        if (tick_cnt == 4'd7) begin
                            tick_cnt <= 4'd0;
                            if (!rx_sync) begin   // still low: real start bit
                                bit_idx <= 3'd0;
                                state   <= DATA;
                            end else begin        // short glitch: ignore it
                                state   <= IDLE;
                            end
                        end else begin
                            tick_cnt <= tick_cnt + 4'd1;
                        end
                    end
                end

                // Sample each data bit 16 ticks apart (mid-bit)
                DATA: begin
                    if (tick16) begin
                        if (tick_cnt == 4'd15) begin
                            tick_cnt <= 4'd0;
                            shift    <= {rx_sync, shift[7:1]};
                            if (bit_idx == 3'd7)
                                state <= STOP;
                            else
                                bit_idx <= bit_idx + 3'd1;
                        end else begin
                            tick_cnt <= tick_cnt + 4'd1;
                        end
                    end
                end

                // Sample the stop bit, then go back to looking for a start edge
                STOP: begin
                    if (tick16) begin
                        if (tick_cnt == 4'd15) begin
                            tick_cnt <= 4'd0;
                            state    <= IDLE;
                            if (rx_sync) begin
                                rx_data  <= shift;
                                rx_valid <= 1'b1;
                            end else begin
                                frame_err <= 1'b1;
                            end
                        end else begin
                            tick_cnt <= tick_cnt + 4'd1;
                        end
                    end
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule
