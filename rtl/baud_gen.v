// -----------------------------------------------------------------------------
// baud_gen.v
// Generates a one-clock-wide pulse (tick16) at 16x the baud rate.
//
//   tick16 period = baud_div clock cycles
//   baud rate     = f_clk / (16 * baud_div)
//
// Example: 50 MHz clock, 115200 baud -> baud_div = 50e6 / (16 * 115200) ~= 27
//
// baud_div is a run-time input, so the baud rate can be changed without
// re-synthesizing. It must be >= 1.
// -----------------------------------------------------------------------------
module baud_gen (
    input  wire        clk,
    input  wire        rst_n,      // asynchronous, active-low reset
    input  wire [15:0] baud_div,   // clock cycles per tick, >= 1
    output reg         tick16      // 1-cycle pulse, 16 per bit period
);

    reg [15:0] cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt    <= 16'd0;
            tick16 <= 1'b0;
        // ">=" (not "==") so a smaller baud_div written at run time
        // can never leave the counter stuck above the new limit.
        end else if (cnt >= baud_div - 16'd1) begin
            cnt    <= 16'd0;
            tick16 <= 1'b1;
        end else begin
            cnt    <= cnt + 16'd1;
            tick16 <= 1'b0;
        end
    end

endmodule
