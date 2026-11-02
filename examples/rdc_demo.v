`timescale 1ns/1ps
// Reset-domain crossing demo:  python vlsi.py lint examples/rdc_demo.v
// One clock, two asynchronous resets. A soft reset clears the 'cfg' register on its own;
// 'state' is reset only by the global reset, so it can capture a changing 'cfg'.
module rdc_demo (
    input  wire       clk,
    input  wire       rst_n,        // global (power-on) reset
    input  wire       soft_rst_n,   // software reset of the config block only
    input  wire [3:0] cfg_in,
    input  wire       cfg_we,
    output reg  [3:0] state,
    output reg  [3:0] cfg_copy
);
    reg [3:0] cfg;

    // config register: soft reset domain
    always @(posedge clk or negedge soft_rst_n)
        if (!soft_rst_n)  cfg <= 4'd0;
        else if (cfg_we)  cfg <= cfg_in;

    // BUG: global reset domain captures 'cfg' while soft_rst_n may be asserting
    always @(posedge clk or negedge rst_n)
        if (!rst_n) state <= 4'd0;
        else        state <= state + cfg;

    // OK: same reset as the source
    always @(posedge clk or negedge soft_rst_n)
        if (!soft_rst_n) cfg_copy <= 4'd0;
        else             cfg_copy <= cfg;
endmodule
