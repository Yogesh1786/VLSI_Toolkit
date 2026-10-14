# Timing constraints for uart_top (example with planted mistakes)
# Try:  python vlsi.py sdc examples/signoff/uart_top.sdc --rtl examples/rtl_project/uart_top.v

create_clock -name core_clk -period 20.0 -waveform {0 10} [get_ports clk]
create_clock -name uart_ref -period 104.0 [get_ports uart_clk]          ;# port does not exist

set_clock_uncertainty 0.25 [get_clocks core_clk]
set_clock_transition  0.10 [get_clocks core_clk]

# inputs
set_input_delay -clock core_clk 4.0 [get_ports {wr_en wr_data[*] rd_en}]
set_input_delay -clock core_clk 17.5 [get_ports rx]                     ;# 87.5% of the period

# outputs (tx and irq are missing)
set_output_delay -clock core_clk 5.0 [get_ports rd_data*]
set_output_delay -clock sys_clk 3.0 [get_ports tx_data]                ;# unknown clock and port

# exceptions
set_multicycle_path 2 -setup -from [get_cells u_baud/*] -to [get_cells u_tx/*]
set_false_path -through [get_pins u_scratch/*]
set_false_path -hold
