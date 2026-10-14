`timescale 1ns/1ps
// Two clock domains with one correct and three incorrect crossings.
// Try:  python vlsi.py lint examples/cdc_demo.v
module cdc_demo (
    input  wire       clk_a,
    input  wire       clk_b,
    input  wire       rst_n,
    input  wire [7:0] din,
    input  wire       go,
    output reg  [7:0] dout,
    output reg        busy_b,
    output reg  [7:0] count_b
);
    // ---------------- clk_a domain ----------------
    reg       flag_a;
    reg       req_a;
    reg [7:0] data_a;
    always @(posedge clk_a or negedge rst_n) begin
        if (!rst_n) begin
            flag_a <= 1'b0;
            req_a  <= 1'b0;
            data_a <= 8'd0;
        end else begin
            flag_a <= go;
            req_a  <= go & ~req_a;
            data_a <= din;
        end
    end

    // ---------------- clk_b domain ----------------
    reg       flag_s1, flag_s2;      // OK: classic 2-flop synchronizer for a single bit
    reg       req_b;                 // BUG: only one flop
    reg [7:0] data_s1, data_s2;      // BUG: multi-bit bus through a 2-flop synchronizer
    always @(posedge clk_b or negedge rst_n) begin
        if (!rst_n) begin
            flag_s1 <= 1'b0;
            flag_s2 <= 1'b0;
            req_b   <= 1'b0;
            data_s1 <= 8'd0;
            data_s2 <= 8'd0;
            busy_b  <= 1'b0;
            dout    <= 8'd0;
            count_b <= 8'd0;
        end else begin
            flag_s1 <= flag_a;
            flag_s2 <= flag_s1;
            req_b   <= req_a;
            busy_b  <= req_b & ~flag_s2;    // req_b had only one flop before use
            data_s1 <= data_a;
            data_s2 <= data_s1;
            dout    <= data_s2;
            count_b <= data_a + count_b;   // BUG: clk_a data used directly in clk_b logic
        end
    end
endmodule
