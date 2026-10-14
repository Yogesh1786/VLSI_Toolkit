# Timing constraints for uart_top (corrected version of uart_top.sdc)

create_clock -name core_clk -period 20.0 -waveform {0 10} [get_ports clk]
set_clock_uncertainty 0.25 [get_clocks core_clk]
set_clock_transition  0.10 [get_clocks core_clk]

set_input_delay  -clock core_clk 4.0 [get_ports {wr_en wr_data[*] rd_en rx}]
set_output_delay -clock core_clk 5.0 [get_ports {rd_data* tx irq}]

set_multicycle_path 2 -setup -from [get_cells u_baud/*] -to [get_cells u_tx/*]
set_multicycle_path 1 -hold  -from [get_cells u_baud/*] -to [get_cells u_tx/*]
set_false_path -through [get_pins u_scratch/*]
