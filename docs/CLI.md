# Command reference

Every tool is also a command: `python vlsi.py <command> -h` shows its options.
Back to the [README](../README.md).

## Contents

- [parse](#parse-understand-a-module)
- [inst](#inst-instantiation-template)
- [tb](#tb-testbench-generator)
- [timing](#timing-sta-report-analyzer)
- [regmap](#regmap-register-generator)
- [vcd](#vcd-waveform-analyzer)
- [lint](#lint-rtl-lint-checks)
- [regress](#regress-regression-log-summary)
- [pd](#pd-deflef-analysis)
- [hier](#hier-design-hierarchy-and-state-machines)
- [axi](#axi-axi-protocol-checker-and-transaction-viewer)
- [sva](#sva-assertion-generator)
- [synth, power, sdc](#synth-power-sdc-sign-off-reports)
- [workspace and history](#workspace-and-history-the-whole-project-at-once)
- [lib](#lib-liberty-library-explorer)
- [compare](#compare-what-changed-between-two-runs)
- [spice](#spice-analog-helpers)

## `parse`: understand a module

```text
python vlsi.py parse <file.v> [--json]
```

This handles both ANSI ports (`input [7:0] a, b`) and the older non-ANSI style. It also handles parameters that depend on other parameters, multi-dimensional packed ports, and several modules in one file. Use `--json` to feed the result into other scripts.

## `inst`: instantiation template

```text
python vlsi.py inst <file.v> [-m module] [-n instance_name]
```

## `tb`: testbench generator

```text
python vlsi.py tb <file.v> [-m module] [-o output] [--cycles 100] [--period 10] [--cocotb]
```

- **Clocks** are detected from names such as `clk`, `clock`, `clk_i` and `sys_clk`.
- **Resets** are detected from names containing `rst` or `reset`. Names ending in `n`, `_n` or `_b` are treated as active-low.
- Modules without a clock (combinational logic) get delay-based stimulus.
- The testbench is a **starting point**. Fill in the `TODO` check sections with expected values.

## `timing`: STA report analyzer

```text
python vlsi.py timing <report> [--top 10] [--csv file] [--plot file.png] [--json] [--fail-on-violation]
```

`--fail-on-violation` makes the command exit with code 2 when timing fails, which is useful in regression scripts.

Generate a report with OpenSTA:

```tcl
report_checks -path_delay min_max -group_count 1000 > sta_report.rpt
```

## `regmap`: register generator

```text
python vlsi.py regmap <spec.json|spec.yaml> [-o output]
```

Access types:

| Type  | Meaning                                        |
| ----- | ---------------------------------------------- |
| `RW`  | Read/write                                     |
| `RO`  | Read-only, with the value supplied by hardware |
| `WO`  | Write-only                                     |
| `W1C` | Write-1-to-clear status bits, set by hardware  |

The spec is validated before anything is generated. Overlapping fields, duplicate or misaligned offsets, and reset values that don't fit are reported as errors. See `examples/uart_regmap.json` for the format.

Besides the simple-bus RTL (`<block>_regs.v`), it writes **`<block>_axil.v`**, a complete AXI4-Lite slave (`s_axil_*` ports, independent AW/W capture, byte-lane `WSTRB` writes, `SLVERR` for unmapped addresses), and **`tb_<block>_axil.v`**, a self-checking testbench that checks reset values, read-back of writable bits, `WSTRB` byte lanes, W1C clearing and `SLVERR`, then prints `TEST PASSED` or `TEST FAILED` and dumps a VCD you can open in the AXI checker.

## `vcd`: waveform analyzer

```text
python vlsi.py vcd <dump.vcd> [--glitch 2] [--x-after T] [--filter name]
```

## `lint`: RTL lint checks

```text
python vlsi.py lint <files and/or folders> [--severity error|warning|info]
```

| Rule                                                      | Severity | Catches                                                                                              |
| --------------------------------------------------------- | -------- | ---------------------------------------------------------------------------------------------------- |
| `MULTI_DRIVER`                                            | ERROR    | The same signal is driven by several `always`/`assign` statements. Separate bit-selects are allowed. |
| `BLOCKING_IN_SEQ`                                         | WARNING  | `=` used in a clocked block. Use `<=`.                                                               |
| `NONBLOCKING_IN_COMB`                                     | WARNING  | `<=` used in combinational logic. Use `=`.                                                           |
| `LATCH_RISK`                                              | WARNING  | A signal is not assigned on every path (an `if` without `else`, or a `case` without `default`)       |
| `CASE_NO_DEFAULT`                                         | WARNING  | A `case` has no `default`. `unique case` and `priority case` are allowed.                            |
| `SENS_LIST` / `CASEX` / `INITIAL_IN_RTL` / `DELAY_IN_RTL` | INFO     | Style and synthesis hints                                                                            |
| `CDC_UNSYNC`                                              | ERROR    | A signal from another clock domain is used directly in logic (metastability)                         |
| `CDC_SINGLE_FLOP`                                         | WARNING  | A crossing goes through only one flip-flop. Use a 2-flop synchronizer.                               |
| `CDC_MULTIBIT`                                            | WARNING  | A multi-bit bus is synchronized bit by bit. Use Gray code, a handshake or an async FIFO.             |

Clock domains are inferred from the `always @(posedge …)` blocks, and a register belongs to the domain of the block that assigns it. `examples/cdc_demo.v` has one bug for each CDC rule plus one correct 2-flop synchronizer.

The exit code is 1 when there are errors, so you can run it before every check-in. It is a fast, heuristic checker, not a replacement for SpyGlass-class lint.

## `regress`: regression log summary

```text
python vlsi.py regress <log folder> [--pattern "*.log"] [--csv file] [--html file]
```

For each test, it reports PASS, FAIL, or INCOMPLETE (no end-of-simulation marker, which usually means a crash, kill or timeout). It also reports the test name and seed, error counts, and the first error. **Failure signatures** remove the numbers, times and paths from the first error, so the same bug hitting 50 tests shows up as one row. The exit code is 2 if anything did not pass.

## `pd`: DEF/LEF analysis

```text
python vlsi.py pd <file.def> [--lef tech.lef cells.lef ...] [--top 10]
```

Without LEF you get the cell mix and the density map by instance count. With LEF you also get areas and utilization, calculated as std-cell area / (core area − macro area). Export DEF from your P&R tool, for example with `write_def` (OpenROAD) or `defOut` (Innovus).

## `hier`: design hierarchy and state machines

```text
python vlsi.py hier <files and/or folders>
```

Prints the instance tree of the top module, then lists modules that are instantiated but never defined (black boxes, library cells or missing files) and modules that are defined but never used. FSMs are found from `case (state)` blocks that assign the next state. For each one it prints the transition table with its conditions, the reset state, **unreachable states** and **states with no way out**.

## `axi`: AXI protocol checker and transaction viewer

```text
python vlsi.py axi <dump.vcd> [--timeout 16] [--no-transactions]
```

Interfaces are found from the signal names (`<prefix>awvalid`, `<prefix>wdata`, `<prefix>rresp`, …, with any prefix such as `s_axi_`, `m_axi_` or `m_axil_`). The clock (`aclk`/`clk`) and reset (`aresetn`) are found nearby. Every signal is sampled on the rising clock edge.

| Rule                                                               | Severity | Catches                                                                |
| ------------------------------------------------------------------ | -------- | ---------------------------------------------------------------------- |
| `VALID_DROPPED`                                                    | ERROR    | VALID fell before READY: the classic handshake bug                     |
| `PAYLOAD_CHANGED`                                                  | ERROR    | Address, data or control changed while waiting for READY               |
| `X_ON_VALID` / `X_ON_PAYLOAD`                                      | ERROR    | Unknown (X/Z) values on the bus                                        |
| `WLAST_MISMATCH` / `RLAST_MISMATCH`                                | ERROR    | LAST not on beat LEN+1                                                 |
| `BOUNDARY_4KB`                                                     | ERROR    | An INCR burst crosses a 4 KB boundary                                  |
| `UNEXPECTED_B` / `UNEXPECTED_R`                                    | ERROR    | A response with no matching request                                    |
| `VALID_IN_RESET`, `ERROR_RESPONSE`, `NO_RESPONSE`, `READY_TIMEOUT` | WARNING  | VALID during reset, SLVERR/DECERR responses, hangs, long back-pressure |

The exit code is 2 for errors, 1 for warnings only, and 0 when the traffic is clean. The examples `examples/axi/axi_clean.vcd` (passes) and `axi_buggy.vcd` (9 planted bugs) show each rule.

## `sva`: assertion generator

```text
python vlsi.py sva <file.v> [-m module] [-o folder]
```

Writes `<module>_sva.svh`. Include it just before `endmodule` inside `` `ifdef ASSERT_ON `` and simulate with `+define+ASSERT_ON`, so the properties can see every internal signal and state name. It generates:

- **AXI**: VALID stays high until READY, payload stable while waiting, no X on VALID, plus a cover point for each handshake
- **FSM**: the state is always a legal value, only the transitions found in the RTL happen, and every state is reachable (cover)
- **One-hot** and **X-free outputs** after reset

Properties on input ports describe what the environment must do; in formal verification, turn those `assert`s into `assume`s.

## `synth`, `power`, `sdc`: sign-off reports

```text
python vlsi.py synth <area report> [--top 15]
python vlsi.py power <power report>
python vlsi.py sdc   <file.sdc> [--rtl top.v] [-m top_module]
```

- `synth` reads Yosys `stat` (with `-liberty` for areas) or Design Compiler `report_area -hierarchy`. A module instantiated twice is counted twice.
- `power` reads PrimePower / PrimeTime-PX / DC / Innovus `report_power` output and converts every value to mW (the leakage unit is often nW).
- `sdc` exits with 2 when there are errors. With `--rtl` it also finds misspelled port names and ports with no input/output delay.

| SDC rule                                                           | Severity | Catches                                                     |
| ------------------------------------------------------------------ | -------- | ----------------------------------------------------------- |
| `NO_CLOCK`, `DUPLICATE_CLOCK`, `BAD_PERIOD`, `GENERATED_NO_SOURCE` | ERROR    | Missing, redefined or malformed clocks                      |
| `UNKNOWN_CLOCK` / `UNKNOWN_PORT`                                   | ERROR    | A name that matches nothing, so the constraint is dropped   |
| `NO_UNCERTAINTY`                                                   | WARNING  | No jitter/skew margin on a clock                            |
| `MISSING_INPUT_DELAY` / `MISSING_OUTPUT_DELAY`                     | WARNING  | Unconstrained I/O paths (needs `--rtl`)                     |
| `IO_DELAY_TOO_LARGE`                                               | WARNING  | I/O delay above 80 % of the clock period                    |
| `MCP_WITHOUT_HOLD`                                                 | WARNING  | `set_multicycle_path N -setup` without the `-hold N-1` pair |
| `BROAD_FALSE_PATH`                                                 | WARNING  | `set_false_path` with no `-from/-to/-through`               |
| `UNRELATED_CLOCKS`                                                 | INFO     | Two clocks with no `set_clock_groups`: timed as synchronous |

The examples are in `examples/signoff/`: `uart_top.sdc` has planted mistakes and `uart_top_fixed.sdc` is clean.

## `workspace` and `history`: the whole project at once

```text
python vlsi.py workspace <folder> [--save] [--label "after ECO 3"]
python vlsi.py history   <folder>
```

`workspace` runs lint and hierarchy on the RTL, regression triage on the logs, the newest timing, synthesis and power reports, the AXI checker on every VCD, the SDC checker (against the RTL top), floorplan analysis and SPICE checks. It prints one PASS/WARN/FAIL row per check and a health score; the exit code is 2 if any check fails. `--save` stores the metrics in the history database.

## `lib`: Liberty library explorer

```text
python vlsi.py lib <file.lib> [--cell NAME]
```

Without `--cell`, it lists every cell (area, leakage, function, typical delay). With `--cell`, it shows that cell's pins and every NLDM table (delay and transition vs input slew and output load).

## `compare`: what changed between two runs

```text
python vlsi.py compare regress <old log folder> <new log folder>
python vlsi.py compare timing  <old report> <new report>
```

Tests are matched by name, since seeds usually differ between runs. Timing endpoints are matched by check and endpoint, using the worst slack of each. The exit code is 2 when things got worse, so you can use it in a nightly script.

## `spice`: analog helpers

```text
python vlsi.py spice info    <netlist.sp>
python vlsi.py spice sweep   <netlist.sp> --param NAME=start:stop:step [-o folder] [--run]
python vlsi.py spice measure <waves.csv|wrdata.txt> -s out [more signals] [--ref in] [--vdd 1.8]
```

- `info` flags nodes connected to only one terminal and **gate-only nodes** (nothing drives them). Both are classic reasons for convergence failures or wrong bias points.
- `sweep` replaces the `.param` value in each copy of the netlist. With `--run`, it runs ngspice on every copy and writes `sweep_<NAME>.csv` with all the `.meas` results.
- `measure` reads CSV with a header, or ngspice `wrdata` output. To export waveforms from ngspice, use `wrdata file.txt v(in) v(out)` inside `.control`.

---

## Installing free EDA tools on Windows

| Tool                             | Purpose                                                            | How to get it                                                            |
| -------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| **Icarus Verilog** + **GTKWave** | Simulate testbenches and view waveforms                            | Windows installer from bleyer.org/icarus (includes GTKWave)              |
| **OSS CAD Suite**                | Yosys, Verilator, Icarus, GTKWave, OpenSTA and more in one package | Windows build from github.com/YosysHQ/oss-cad-suite-build/releases       |
| **OpenLane / OpenROAD**          | Full RTL-to-GDS flow                                               | Use WSL2 (Ubuntu) or Docker                                              |
| **ngspice**                      | Analog simulation, needed for `spice sweep --run`                  | Windows build from ngspice.sourceforge.io. Add its `bin` folder to PATH. |

Once Icarus is installed, run the generated testbench:

```bash
iverilog -g2012 -o sim.out output/tb_counter.v examples/counter.v
```

```bash
vvp sim.out
```

```bash
gtkwave tb_counter.vcd
```

You can then analyze that waveform with this toolkit:

```bash
python vlsi.py vcd tb_counter.vcd
```
