`timescale 1ns/1ps
/* Synchronous FIFO written in the older non-ANSI (Verilog-1995) port style.
   Shows parameters that depend on other parameters ($clog2). */
module sync_fifo (clk, rst, wr_en, rd_en, din, dout, full, empty, count);
    parameter DATA_W = 16;
    parameter DEPTH  = 32;
    localparam ADDR_W = $clog2(DEPTH);

    input                 clk, rst;
    input                 wr_en, rd_en;
    input  [DATA_W-1:0]   din;
    output [DATA_W-1:0]   dout;
    output                full, empty;
    output [ADDR_W:0]     count;

    reg    [DATA_W-1:0]   dout;
    reg    [DATA_W-1:0]   mem [0:DEPTH-1];
    reg    [ADDR_W:0]     count;
    reg    [ADDR_W-1:0]   wptr, rptr;

    assign full  = (count == DEPTH);
    assign empty = (count == 0);

    always @(posedge clk) begin
        if (rst) begin
            wptr <= 0; rptr <= 0; count <= 0;
        end else begin
            if (wr_en && !full) begin
                mem[wptr] <= din;
                wptr <= wptr + 1'b1;
            end
            if (rd_en && !empty) begin
                dout <= mem[rptr];
                rptr <= rptr + 1'b1;
            end
            count <= count + (wr_en && !full) - (rd_en && !empty);
        end
    end
endmodule
