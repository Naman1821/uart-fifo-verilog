// -----------------------------------------------------------------------------
// sync_fifo.v
// Synchronous FIFO, first-word-fall-through (FWFT / "show-ahead"):
// rd_data always shows the oldest entry whenever empty == 0, and rd_en
// removes it on the next clock edge.
//
// Writes while full and reads while empty are ignored, so the FIFO can
// never be corrupted by a misbehaving producer or consumer.
// -----------------------------------------------------------------------------
module sync_fifo #(
    parameter WIDTH = 8,
    parameter DEPTH = 16              // must be a power of 2
) (
    input  wire                   clk,
    input  wire                   rst_n,
    input  wire                   wr_en,
    input  wire [WIDTH-1:0]       wr_data,
    input  wire                   rd_en,
    output wire [WIDTH-1:0]       rd_data,
    output wire                   full,
    output wire                   empty,
    output wire [$clog2(DEPTH):0] count     // entries stored, 0..DEPTH
);

    localparam AW = $clog2(DEPTH);

    reg [WIDTH-1:0] mem [0:DEPTH-1];

    // Pointers carry ONE EXTRA BIT above the address.
    //   same address, same extra bit      -> FIFO is empty
    //   same address, different extra bit -> writer has lapped reader: full
    reg [AW:0] wr_ptr;
    reg [AW:0] rd_ptr;

    wire do_wr = wr_en && !full;
    wire do_rd = rd_en && !empty;

    assign empty   = (wr_ptr == rd_ptr);
    assign full    = (wr_ptr[AW] != rd_ptr[AW]) &&
                     (wr_ptr[AW-1:0] == rd_ptr[AW-1:0]);
    assign count   = wr_ptr - rd_ptr;           // modulo 2^(AW+1)
    assign rd_data = mem[rd_ptr[AW-1:0]];       // FWFT: head is always visible

    // Storage: no reset needed, the pointers decide what is valid
    always @(posedge clk) begin
        if (do_wr)
            mem[wr_ptr[AW-1:0]] <= wr_data;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr <= {(AW+1){1'b0}};
            rd_ptr <= {(AW+1){1'b0}};
        end else begin
            if (do_wr) wr_ptr <= wr_ptr + 1'b1;
            if (do_rd) rd_ptr <= rd_ptr + 1'b1;
        end
    end

endmodule
