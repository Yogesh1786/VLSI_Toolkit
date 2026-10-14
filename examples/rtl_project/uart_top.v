`timescale 1ns/1ps
// UART subsystem top level - example project for the Design Hierarchy & FSM viewer
module uart_top #(
    parameter CLK_HZ = 50_000_000,
    parameter BAUD   = 115200
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       rx,
    output wire       tx,
    input  wire       wr_en,
    input  wire [7:0] wr_data,
    input  wire       rd_en,
    output wire [7:0] rd_data,
    output wire       irq
);
    wire tick, tx_busy, tx_start, rx_valid;
    wire [7:0] tx_byte, rx_byte;
    wire tx_empty, rx_full;

    baud_gen #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_baud (
        .clk(clk), .rst_n(rst_n), .tick(tick)
    );

    sync_fifo #(.DATA_W(8), .DEPTH(16)) u_tx_fifo (
        .clk(clk), .rst(~rst_n), .wr_en(wr_en), .rd_en(tx_start), .din(wr_data),
        .dout(tx_byte), .full(), .empty(tx_empty), .count()
    );

    uart_tx u_tx (
        .clk(clk), .rst_n(rst_n), .tick(tick), .start(tx_start), .data(tx_byte), .tx(tx), .busy(tx_busy)
    );

    uart_rx u_rx (
        .clk(clk), .rst_n(rst_n), .tick(tick), .rx(rx), .data(rx_byte), .valid(rx_valid)
    );

    sync_fifo #(.DATA_W(8), .DEPTH(16)) u_rx_fifo (
        .clk(clk), .rst(~rst_n), .wr_en(rx_valid), .rd_en(rd_en), .din(rx_byte),
        .dout(rd_data), .full(rx_full), .empty(), .count()
    );

    // vendor memory macro: delivered as a black box (no RTL in this project)
    sram_32x8 u_scratch (
        .clk(clk), .we(1'b0), .addr(5'd0), .din(8'd0), .dout()
    );

    assign tx_start = ~tx_empty & ~tx_busy;
    assign irq      = rx_full;
endmodule
