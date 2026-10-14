`timescale 1ns/1ps
// Deliberately buggy RTL to demonstrate:  python vlsi.py lint examples/lint_demo.v
module lint_demo (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [1:0] sel,
    input  wire [7:0] a, b, c,
    input  wire       en,
    output reg  [7:0] y,
    output reg  [7:0] q,
    output reg  [7:0] z,
    output wire [7:0] w
);
    // BUG 1: blocking assignment in a clocked block
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) q = 8'd0;
        else        q = y;
    end

    // BUG 2: case without default + no default assignment -> latch on y
    always @(*) begin
        case (sel)
            2'd0: y = a;
            2'd1: y = b;
            2'd2: y = c;
        endcase
    end

    // BUG 3: if without else -> latch on z; non-blocking in comb logic;
    //        incomplete sensitivity list
    always @(en or a) begin
        if (en)
            z <= a;
    end

    // BUG 4: w driven twice
    assign w = a & b;
    assign w = a | c;

    // OK: separate bit-selects are not a multi-driver problem
    wire [1:0] bits;
    assign bits[0] = en;
    assign bits[1] = ~en;
endmodule
