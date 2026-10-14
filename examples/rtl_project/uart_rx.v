`timescale 1ns/1ps
// UART receiver with framing-error detection
module uart_rx (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       tick,
    input  wire       rx,
    output reg  [7:0] data,
    output reg        valid
);
    typedef enum logic [2:0] { WAIT_START, RECV, CHECK_STOP, DONE, FRAME_ERR, BREAK_DET } rx_state_t;
    rx_state_t state;
    reg [2:0] n;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= WAIT_START;
            n     <= 3'd0;
            valid <= 1'b0;
        end else begin
            valid <= 1'b0;
            case (state)
                WAIT_START: if (tick && !rx) state <= RECV;
                RECV: begin
                    if (tick) begin
                        data <= {rx, data[7:1]};
                        n    <= n + 1'b1;
                        if (n == 3'd7) state <= CHECK_STOP;
                    end
                end
                CHECK_STOP: begin
                    if (tick && rx)       state <= DONE;
                    else if (tick && !rx) state <= FRAME_ERR;
                end
                DONE: begin
                    valid <= 1'b1;
                    state <= WAIT_START;
                end
                FRAME_ERR: if (rx) state <= WAIT_START;
                // BREAK_DET is declared but nothing ever enters it (unreachable)
                BREAK_DET: state <= WAIT_START;
                default: state <= WAIT_START;
            endcase
        end
    end
endmodule
