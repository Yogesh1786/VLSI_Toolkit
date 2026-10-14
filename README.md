# VLSI Toolkit

Python tools that automate common tasks in a chip-design (VLSI) flow.
The core runs on **plain Python 3.10+, with no extra installs**.

**New to Python?** Start with [LEARN_PYTHON.md](LEARN_PYTHON.md), an 8-week plan built around this toolkit's own code.

**Put it online?** [DEPLOY.md](DEPLOY.md) explains GitHub + Vercel step by step.

| Area                | Command           | What it does                                                                                                                                                                                          |
| ------------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Workspace**       | `workspace`       | **Opens a whole project folder**: finds and classifies every design file, runs every relevant tool at once and gives a health score. `--save` records a snapshot for trends                      |
|                     | `history`         | Lists the saved snapshots of a project (health, lint, pass rate, WNS, area, power …) so you can see the trend over time                                                                            |
| **RTL design**      | `parse`           | Lists the modules, parameters and ports in a Verilog/SystemVerilog file, with widths evaluated (`[WIDTH-1:0]` becomes 8, and `$clog2` is supported)                                                   |
|                     | `inst`            | Prints a ready-to-paste instantiation template                                                                                                                                                        |
|                     | `lint`            | Finds RTL bugs: multiple drivers, latches, blocking `=` in flops, `case` without `default`, and **clock-domain crossings** without a proper synchronizer                                            |
|                     | `hier`            | **Design hierarchy and FSMs** of a whole project: instance tree, black boxes, unused modules, state machines with transitions, plus unreachable and stuck states                                      |
|                     | `regmap`          | Turns one JSON/YAML register spec into **Verilog RTL, an AXI4-Lite slave with a self-checking testbench, a C header and HTML docs**                                                                  |
| **Verification**    | `tb`              | Generates a Verilog testbench (clock, reset, random stimulus, VCD dump) and, optionally, a **cocotb** test                                                                                            |
|                     | `regress`         | Summarizes a folder of simulation logs (UVM, VCS, Questa, Xcelium) and groups failures by **signature**                                                                                               |
|                     | `vcd`             | Analyzes waveform dumps: toggles, clock frequency and duty cycle, glitches, X/Z values, idle signals                                                                                                  |
|                     | `axi`             | **AXI protocol checker and transaction viewer**: finds AXI4/AXI4-Lite interfaces in a VCD, checks 13 protocol rules, and rebuilds every read and write with its data, response, latency and bandwidth |
|                     | `sva`             | Generates **SystemVerilog assertions** and cover points from RTL: AXI handshake rules, legal FSM states and transitions, one-hot signals, X-free outputs                                             |
| **Physical design** | `timing`          | Parses OpenSTA, PrimeTime or Vivado timing reports and shows WNS/TNS, the worst paths, the endpoints with the most violations, and a slack histogram                                                  |
|                     | `pd`              | Analyzes DEF (+LEF): die and core area, **utilization**, cell mix, unplaced cells, a **placement density map**                                                                                        |
|                     | `lib`             | **Liberty (.lib) explorer**: cells, area, leakage, pins and functions, NLDM delay tables                                                                                                              |
|                     | `synth`           | **Synthesis area report** (Yosys `stat`, Design Compiler `report_area -hierarchy`): total area, comb/seq split, area per module, most-used cells                                                     |
|                     | `power`           | **Power report** (`report_power`, with or without `-hierarchy`): dynamic vs leakage, power groups, power per instance                                                                                |
|                     | `sdc`             | **SDC checker**: unknown clocks/ports, missing I/O delays, multicycle without hold, broad false paths, unrelated clocks (13 rules, optional check against the RTL top)                               |
| **Analog**          | `spice info`      | Netlist summary, MOSFET W/L table, **floating node and floating gate checks**                                                                                                                         |
|                     | `spice sweep`     | Generates (and, with ngspice installed, runs) `.param` sweeps and collects the `.meas` results                                                                                                        |
|                     | `spice measure`   | Rise/fall time, propagation delay, frequency, duty cycle and overshoot from waveform data                                                                                                             |
| **Tracking**        | `compare regress` | Compares two regression runs: new failures, fixed tests, new bug signatures                                                                                                                           |
|                     | `compare timing`  | Compares two timing reports (e.g. before and after an ECO): WNS/TNS change, and which endpoints were fixed, degraded or newly violating                                                               |

---

## 1. Quick start

Open a terminal in this folder and run:

```bash
python vlsi.py -h
```

Try every tool on the bundled examples:

```bash
python vlsi.py parse examples/fifo.v
python vlsi.py inst examples/counter.v
python vlsi.py lint examples/lint_demo.v
python vlsi.py regmap examples/uart_regmap.json
python vlsi.py tb examples/counter.v --cocotb
python vlsi.py regress examples/regression_logs --html output/regression.html
python vlsi.py vcd examples/sample.vcd
python vlsi.py timing examples/sta_report.rpt --csv output/paths.csv
python vlsi.py pd examples/pd/demo.def --lef examples/pd/demo.lef
python vlsi.py spice info examples/analog/buggy_bias.sp
python vlsi.py hier examples/rtl_project
python vlsi.py axi examples/axi/axi_buggy.vcd
python vlsi.py lib examples/lib/vt_demo.lib --cell NAND2_X1
python vlsi.py compare regress examples/regression_logs_prev examples/regression_logs
python vlsi.py compare timing examples/sta_report.rpt examples/sta_report_eco.rpt
python vlsi.py spice sweep examples/analog/inverter_chain.sp --param VDD=1.2:1.8:0.2
python vlsi.py spice measure examples/analog/inverter_tran.csv -s out --ref in --vdd 1.8
python vlsi.py lint examples/cdc_demo.v
python vlsi.py sva examples/axi/uart_axil.v -o output
python vlsi.py synth examples/signoff/synth_yosys.rpt
python vlsi.py power examples/signoff/power.rpt
python vlsi.py sdc examples/signoff/uart_top.sdc --rtl examples/rtl_project/uart_top.v
python vlsi.py workspace examples --save --label "first run"
python vlsi.py history examples
```

Generated files go to the `output/` folder. Open `output/uart_regs.html` and `output/regression.html` in a browser.

Run the tests after any change you make:

```bash
python -m unittest -v
```

## Web app (React frontend)

A full web interface for every tool, with a dark/light theme, Ctrl+K tool search, drag-and-drop upload,
sortable tables, a zoomable waveform viewer and a floorplan heatmap.

**Start it** by double-clicking `start_app.bat`. The first run builds the frontend. Or run:

```bash
python -m uvicorn api.main:app --port 8000
```

Then open **http://localhost:8000**.

### How it is built

```text
Browser ── React app (web/) ──HTTP/JSON──► FastAPI server (api/) ──calls──► vlsi_toolkit/ (backend)
```

| Part         | Folder                | Role                                                                                    |
| ------------ | --------------------- | --------------------------------------------------------------------------------------- |
| **Frontend** | `web/src/pages/`      | One React page per tool                                                                 |
|              | `web/src/components/` | Shared UI: cards, KPIs, tabs, tables, code viewer, charts, layout                       |
|              | `web/src/lib/api.ts`  | All calls to the API, the health and version check, friendly error messages             |
| **API**      | `api/main.py`         | Builds the app: routers, error handling, 404 for unknown endpoints, serving the web app |
|              | `api/routers/`        | One file per area: `general`, `workspace`, `rtl`, `verification`, `physical`, `analog`, `compare` |
|              | `api/models.py`       | Request formats, validated automatically                                                |
|              | `api/errors.py`       | Turns bad input (422) and crashes (500) into short JSON messages                        |
| **Backend**  | `vlsi_toolkit/`       | All parsing and analysis. The command line uses it too.                                 |

**Project workspace.** On the *Project Workspace* page, type the path of your project folder. The app finds every RTL file, log, report, VCD, DEF/LEF, SDC and netlist in it, and every tool page gets a **Workspace** tab to pick those files directly (no uploading). *Analyze* runs everything at once; *Save* stores the metrics, and the *Trends* page charts them over time. Saved runs and settings live in `~/.vlsi_toolkit/` (`history.db`, `settings.json`); set the `VT_DATA_DIR` environment variable to keep them somewhere else.

**Version check.** `/api/health` reports `api_version` (currently 5). If the web app is newer than the running API server (for example, the server was started before an update), every page shows a banner telling you to restart it. Unknown `/api/...` addresses return a clear JSON 404.

### Developing (live reload)

Double-click **`start_dev.bat`**. It opens two windows: the API with auto-reload on port 8000, and the React dev server on port 5173. Then open http://localhost:5173. Any change to Python or React code shows up without a restart.

To do the same by hand, use two terminals:

```bash
python -m uvicorn api.main:app --port 8000 --reload
```

```bash
npm --prefix web run dev
```

Without `--reload`, the API server keeps running the code it started with. After an update it won't know the new endpoints, and the web app will show the "API server is outdated" banner. After changing the frontend, rebuild it so that `start_app.bat` and port 8000 serve the new version:

```bash
npm --prefix web run build
```

The API documentation is generated automatically at http://localhost:8000/docs.

### Optional extras

```bash
pip install -r requirements-extras.txt
```

- `matplotlib` lets you save a slack histogram PNG with `python vlsi.py timing report.rpt --plot slack.png`
- `pyyaml` lets you write register specs as `.yaml` instead of `.json`
- `cocotb` runs the generated Python testbenches. It also needs a simulator (see section 4).

---

## 2. Command reference

### `parse`: understand a module

```text
python vlsi.py parse <file.v> [--json]
```

This handles both ANSI ports (`input [7:0] a, b`) and the older non-ANSI style. It also handles parameters that depend on other parameters, multi-dimensional packed ports, and several modules in one file. Use `--json` to feed the result into other scripts.

### `inst`: instantiation template

```text
python vlsi.py inst <file.v> [-m module] [-n instance_name]
```

### `tb`: testbench generator

```text
python vlsi.py tb <file.v> [-m module] [-o output] [--cycles 100] [--period 10] [--cocotb]
```

- **Clocks** are detected from names such as `clk`, `clock`, `clk_i` and `sys_clk`.
- **Resets** are detected from names containing `rst` or `reset`. Names ending in `n`, `_n` or `_b` are treated as active-low.
- Modules without a clock (combinational logic) get delay-based stimulus.
- The testbench is a **starting point**. Fill in the `TODO` check sections with expected values.

### `timing`: STA report analyzer

```text
python vlsi.py timing <report> [--top 10] [--csv file] [--plot file.png] [--json] [--fail-on-violation]
```

`--fail-on-violation` makes the command exit with code 2 when timing fails, which is useful in regression scripts.

Generate a report with OpenSTA:

```tcl
report_checks -path_delay min_max -group_count 1000 > sta_report.rpt
```

### `regmap`: register generator

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

### `vcd`: waveform analyzer

```text
python vlsi.py vcd <dump.vcd> [--glitch 2] [--x-after T] [--filter name]
```

### `lint`: RTL lint checks

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

### `regress`: regression log summary

```text
python vlsi.py regress <log folder> [--pattern "*.log"] [--csv file] [--html file]
```

For each test, it reports PASS, FAIL, or INCOMPLETE (no end-of-simulation marker, which usually means a crash, kill or timeout). It also reports the test name and seed, error counts, and the first error. **Failure signatures** remove the numbers, times and paths from the first error, so the same bug hitting 50 tests shows up as one row. The exit code is 2 if anything did not pass.

### `pd`: DEF/LEF analysis

```text
python vlsi.py pd <file.def> [--lef tech.lef cells.lef ...] [--top 10]
```

Without LEF you get the cell mix and the density map by instance count. With LEF you also get areas and utilization, calculated as std-cell area / (core area − macro area). Export DEF from your P&R tool, for example with `write_def` (OpenROAD) or `defOut` (Innovus).

### `hier`: design hierarchy and state machines

```text
python vlsi.py hier <files and/or folders>
```

Prints the instance tree of the top module, then lists modules that are instantiated but never defined (black boxes, library cells or missing files) and modules that are defined but never used. FSMs are found from `case (state)` blocks that assign the next state. For each one it prints the transition table with its conditions, the reset state, **unreachable states** and **states with no way out**.

### `axi`: AXI protocol checker and transaction viewer

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

### `sva`: assertion generator

```text
python vlsi.py sva <file.v> [-m module] [-o folder]
```

Writes `<module>_sva.svh`. Include it just before `endmodule` inside `` `ifdef ASSERT_ON `` and simulate with `+define+ASSERT_ON`, so the properties can see every internal signal and state name. It generates:

- **AXI**: VALID stays high until READY, payload stable while waiting, no X on VALID, plus a cover point for each handshake
- **FSM**: the state is always a legal value, only the transitions found in the RTL happen, and every state is reachable (cover)
- **One-hot** and **X-free outputs** after reset

Properties on input ports describe what the environment must do; in formal verification, turn those `assert`s into `assume`s.

### `synth`, `power`, `sdc`: sign-off reports

```text
python vlsi.py synth <area report> [--top 15]
python vlsi.py power <power report>
python vlsi.py sdc   <file.sdc> [--rtl top.v] [-m top_module]
```

- `synth` reads Yosys `stat` (with `-liberty` for areas) or Design Compiler `report_area -hierarchy`. A module instantiated twice is counted twice.
- `power` reads PrimePower / PrimeTime-PX / DC / Innovus `report_power` output and converts every value to mW (the leakage unit is often nW).
- `sdc` exits with 2 when there are errors. With `--rtl` it also finds misspelled port names and ports with no input/output delay.

| SDC rule                                                                  | Severity | Catches                                                    |
| ------------------------------------------------------------------------- | -------- | ---------------------------------------------------------- |
| `NO_CLOCK`, `DUPLICATE_CLOCK`, `BAD_PERIOD`, `GENERATED_NO_SOURCE`        | ERROR    | Missing, redefined or malformed clocks                     |
| `UNKNOWN_CLOCK` / `UNKNOWN_PORT`                                          | ERROR    | A name that matches nothing, so the constraint is dropped  |
| `NO_UNCERTAINTY`                                                          | WARNING  | No jitter/skew margin on a clock                           |
| `MISSING_INPUT_DELAY` / `MISSING_OUTPUT_DELAY`                            | WARNING  | Unconstrained I/O paths (needs `--rtl`)                    |
| `IO_DELAY_TOO_LARGE`                                                      | WARNING  | I/O delay above 80 % of the clock period                   |
| `MCP_WITHOUT_HOLD`                                                        | WARNING  | `set_multicycle_path N -setup` without the `-hold N-1` pair |
| `BROAD_FALSE_PATH`                                                        | WARNING  | `set_false_path` with no `-from/-to/-through`              |
| `UNRELATED_CLOCKS`                                                        | INFO     | Two clocks with no `set_clock_groups`: timed as synchronous |

The examples are in `examples/signoff/`: `uart_top.sdc` has planted mistakes and `uart_top_fixed.sdc` is clean.

### `workspace` and `history`: the whole project at once

```text
python vlsi.py workspace <folder> [--save] [--label "after ECO 3"]
python vlsi.py history   <folder>
```

`workspace` runs lint and hierarchy on the RTL, regression triage on the logs, the newest timing, synthesis and power reports, the AXI checker on every VCD, the SDC checker (against the RTL top), floorplan analysis and SPICE checks. It prints one PASS/WARN/FAIL row per check and a health score; the exit code is 2 if any check fails. `--save` stores the metrics in the history database.

### `lib`: Liberty library explorer

```text
python vlsi.py lib <file.lib> [--cell NAME]
```

Without `--cell`, it lists every cell (area, leakage, function, typical delay). With `--cell`, it shows that cell's pins and every NLDM table (delay and transition vs input slew and output load).

### `compare`: what changed between two runs

```text
python vlsi.py compare regress <old log folder> <new log folder>
python vlsi.py compare timing  <old report> <new report>
```

Tests are matched by name, since seeds usually differ between runs. Timing endpoints are matched by check and endpoint, using the worst slack of each. The exit code is 2 when things got worse, so you can use it in a nightly script.

### `spice`: analog helpers

```text
python vlsi.py spice info    <netlist.sp>
python vlsi.py spice sweep   <netlist.sp> --param NAME=start:stop:step [-o folder] [--run]
python vlsi.py spice measure <waves.csv|wrdata.txt> -s out [more signals] [--ref in] [--vdd 1.8]
```

- `info` flags nodes connected to only one terminal and **gate-only nodes** (nothing drives them). Both are classic reasons for convergence failures or wrong bias points.
- `sweep` replaces the `.param` value in each copy of the netlist. With `--run`, it runs ngspice on every copy and writes `sweep_<NAME>.csv` with all the `.meas` results.
- `measure` reads CSV with a header, or ngspice `wrdata` output. To export waveforms from ngspice, use `wrdata file.txt v(in) v(out)` inside `.control`.

---

## 3. Project structure

```text
VLSI_Toolkit/
├── vlsi.py                    # entry point: python vlsi.py <command>
├── vlsi_toolkit/
│   ├── cli.py                 # command-line interface (argparse)
│   ├── common.py              # comment stripping, safe expression eval, tables
│   ├── verilog_parser.py      # RTL: module/port/parameter extraction
│   ├── lint.py                # RTL: lint rules
│   ├── regmap_gen.py          # RTL: register spec → RTL / C / HTML
│   ├── tb_generator.py        # verification: instantiation, Verilog TB, cocotb TB
│   ├── regress.py             # verification: regression log analysis
│   ├── vcd_analyzer.py        # verification: waveform analysis
│   ├── timing_report.py       # PD: STA report parsing and analysis
│   ├── pd_analyzer.py         # PD: DEF/LEF analysis
│   ├── liberty.py             # PD: Liberty (.lib) parser
│   ├── hierarchy.py           # RTL: instance tree + FSM extraction
│   ├── compare.py             # Tracking: regression and timing run comparison
│   ├── axi.py                 # Verification: AXI protocol checker + transactions
│   ├── sva.py                 # Verification: SystemVerilog assertion generator
│   ├── synth_report.py        # PD: synthesis area reports (Yosys, DC)
│   ├── power_report.py        # PD: report_power parser
│   ├── sdc_check.py           # PD: timing-constraint checker
│   ├── workspace.py           # Workspace: folder scan + analyze everything
│   ├── history.py             # Workspace: saved snapshots (SQLite) and trends
│   └── spice.py               # analog: netlist checks, sweeps, measurements
├── examples/                  # sample inputs for every tool
│   ├── signoff/               #   synthesis / power reports, SDC files
│   ├── axi/                   #   AXI VCDs + the generated AXI-Lite slave
│   ├── regression_logs/       #   simulation logs (UVM / Questa / Icarus)
│   ├── pd/                    #   demo.def + demo.lef
│   └── analog/                #   SPICE netlists + transient waveform
├── api/                       # HTTP API for the React app (FastAPI): main.py + routers/
├── web/                       # React frontend (Vite + TypeScript + Tailwind)
├── tests/                     # unit tests (python -m unittest)
├── LEARN_PYTHON.md            # beginner learning plan
└── output/                    # generated files
```

---

## 4. Installing free EDA tools on Windows (to run the generated files)

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

---

## 5. Ideas to extend it

1. **Share on your network**: run the API with `--host 0.0.0.0` so teammates can open the web app (check your company policy first).
2. **Synthesis runner**: call Yosys from Python and feed its `stat` output straight into `synth`.
3. **More lint rules**: width mismatches, unused signals, reset-domain crossings.
4. **Self-checking testbenches**: add Python reference models to the generated cocotb tests.
5. **Power estimation**: combine VCD toggle counts with capacitance to estimate dynamic power.
6. **UVM RAL generation**: add a SystemVerilog UVM register model output to `regmap`.
7. **PVT corners**: extend `spice sweep` to sweep several parameters (process, voltage, temperature) together.
8. **Nightly dashboard**: run `regress` and `timing` every night and publish the HTML reports.

## Limitations

- The Verilog parser reads **module headers** with regular expressions. It is not a full compiler. For heavy SystemVerilog (interfaces, packages, macros), use a real front end such as `pyslang`.
- The Vivado parser extracts slack, start/end points and path type only.
- `lint` (including the CDC rules), `regress`, `sdc` and `spice info` are pattern-based. They catch common problems quickly, but they are not sign-off tools (SpyGlass CDC, PrimeTime `check_timing`).
- `spice sweep --run`, the cocotb tests and the AXI-Lite testbench could not be run while building this toolkit, because ngspice and a simulator were not installed. The generated files were checked, but not simulated.
#   V L S I _ T o o l k i t  
 