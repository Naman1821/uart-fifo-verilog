// -----------------------------------------------------------------------------
// uart_tx.v
// 8N1 UART transmitter: 1 start bit (0), 8 data bits (LSB first),
// no parity, 1 stop bit (1). The line idles high.
//
// Every bit lasts 16 pulses of tick16 (see baud_gen.v).
// Handshake: a byte is accepted on any clock where tx_valid && tx_ready.
// -----------------------------------------------------------------------------
module uart_tx (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       tick16,     // 16x baud tick
    input  wire       tx_valid,   // a byte is waiting on tx_data
    input  wire [7:0] tx_data,
    output wire       tx_ready,   // transmitter is idle and can take a byte
    output reg        tx          // serial output (registered, glitch-free)
);

    localparam [1:0] IDLE  = 2'd0,
                     START = 2'd1,
                     DATA  = 2'd2,
                     STOP  = 2'd3;

    reg [1:0] state;
    reg [3:0] tick_cnt;   // 0..15: position inside the current bit
    reg [2:0] bit_idx;    // which data bit is on the line
    reg [7:0] shift;      // data bits still to send, LSB goes out first

    assign tx_ready = (state == IDLE);

    // Last tick of the current bit period
    wire bit_done = tick16 && (tick_cnt == 4'd15);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state    <= IDLE;
            tick_cnt <= 4'd0;
            bit_idx  <= 3'd0;
            shift    <= 8'd0;
        end else begin
            if (state != IDLE && tick16)
                tick_cnt <= tick_cnt + 4'd1;   // wraps 15 -> 0 by itself

            case (state)
                IDLE: begin
                    if (tx_valid) begin
                        shift    <= tx_data;
                        tick_cnt <= 4'd0;
                        state    <= START;
                    end
                end

                START: begin
                    if (bit_done) begin
                        bit_idx <= 3'd0;
                        state   <= DATA;
                    end
                end

                DATA: begin
                    if (bit_done) begin
                        shift <= {1'b0, shift[7:1]};   // next bit to shift[0]
                        if (bit_idx == 3'd7)
                            state <= STOP;
                        else
                            bit_idx <= bit_idx + 3'd1;
                    end
                end

                STOP: begin
                    if (bit_done)
                        state <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end

    // Output is a function of the state, then registered so the serial
    // line never glitches while the state machine changes.
    reg tx_next;
    always @(*) begin
        case (state)
            START:   tx_next = 1'b0;
            DATA:    tx_next = shift[0];
            default: tx_next = 1'b1;     // IDLE and STOP
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) tx <= 1'b1;
        else        tx <= tx_next;
    end

endmodule
