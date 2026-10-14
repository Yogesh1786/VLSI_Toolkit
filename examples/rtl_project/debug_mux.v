`timescale 1ns/1ps
// Leftover debug module: defined but never instantiated
module debug_mux (input wire [1:0] sel, input wire [7:0] a, b, c, output reg [7:0] y);
    always @(*) begin
        case (sel)
            2'd0: y = a;
            2'd1: y = b;
            default: y = c;
        endcase
    end
endmodule
