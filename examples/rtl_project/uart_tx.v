`timescale 1ns/1ps
// UART transmitter: start bit, 8 data bits, even parity, stop bit
module uart_tx (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       tick,
    input  wire       start,
    input  wire [7:0] data,
    output reg        tx,
    output wire       busy
);
    localparam IDLE = 3'd0, START = 3'd1, DATA = 3'd2, PARITY = 3'd3, STOP = 3'd4;
    reg [2:0] state, next_state;
    reg [2:0] bit_idx;
    reg [7:0] shreg;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) state <= IDLE;
        else        state <= next_state;
    end

    always @(*) begin
        next_state = state;
        case (state)
            IDLE:   if (start) next_state = START;
            START:  if (tick) next_state = DATA;
            DATA:   if (tick && bit_idx == 3'd7) next_state = PARITY;
            PARITY: if (tick) next_state = STOP;
            STOP:   if (tick) next_state = IDLE;
            default: next_state = IDLE;
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            bit_idx <= 3'd0;
            shreg   <= 8'd0;
            tx      <= 1'b1;
        end else begin
            case (state)
                IDLE:   begin tx <= 1'b1; if (start) shreg <= data; end
                START:  tx <= 1'b0;
                DATA:   if (tick) begin tx <= shreg[0]; shreg <= shreg >> 1; bit_idx <= bit_idx + 1'b1; end
                PARITY: tx <= ^data;
                default: tx <= 1'b1;
            endcase
        end
    end
    assign busy = (state != IDLE);
endmodule
