`timescale 1ns/1ps
// Up/down counter with enable and synchronous load (ANSI port style)
module counter #(
    parameter WIDTH = 8,
    parameter STEP  = 1
) (
    input  wire             clk,
    input  wire             rst_n,     // active-low asynchronous reset
    input  wire             en,
    input  wire             up_down,   // 1 = count up, 0 = count down
    input  wire             load,
    input  wire [WIDTH-1:0] load_val,
    output reg  [WIDTH-1:0] count,
    output wire             wrap
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count <= {WIDTH{1'b0}};
        else if (load)
            count <= load_val;
        else if (en)
            count <= up_down ? count + STEP : count - STEP;
    end

    assign wrap = en & (up_down ? (&count) : (count == 0));
endmodule
