`timescale 1ns/1ps
// Generates one tick per bit (oversampling not modelled)
module baud_gen #(parameter CLK_HZ = 50_000_000, parameter BAUD = 115200) (
    input  wire clk,
    input  wire rst_n,
    output reg  tick
);
    localparam DIV = CLK_HZ / BAUD;
    reg [$clog2(DIV)-1:0] cnt;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt  <= 0;
            tick <= 1'b0;
        end else if (cnt == DIV - 1) begin
            cnt  <= 0;
            tick <= 1'b1;
        end else begin
            cnt  <= cnt + 1'b1;
            tick <= 1'b0;
        end
    end
endmodule
