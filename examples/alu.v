`timescale 1ns/1ps
// Purely combinational ALU (no clock) - the generated testbench uses time delays
module alu #(parameter N = 32) (
    input  signed [N-1:0] a, b,
    input         [2:0]   op,
    output reg signed [N-1:0] y,
    output                zero, carry_out
);
    reg [N:0] tmp;
    always @(*) begin
        tmp = {(N+1){1'b0}};
        case (op)
            3'd0: begin tmp = a + b; y = tmp[N-1:0]; end
            3'd1: begin tmp = a - b; y = tmp[N-1:0]; end
            3'd2: y = a & b;
            3'd3: y = a | b;
            3'd4: y = a ^ b;
            3'd5: y = (a < b) ? 1 : 0;
            3'd6: y = a <<< b[4:0];
            default: y = a >>> b[4:0];
        endcase
    end
    assign zero      = (y == 0);
    assign carry_out = tmp[N];
endmodule
