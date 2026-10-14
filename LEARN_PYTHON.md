# Learn Python for VLSI: an 8-week plan for working engineers

This plan is for engineers who know chip design but are new to Python. It needs
about **45 minutes a day, 5 days a week**. Every lesson uses VLSI examples, and
each one points to real code in this toolkit, so you learn by reading and
changing tools you actually use at work.

**How to practice:** keep a folder `practice/` next to this file. Type every
example yourself (don't copy-paste) and run it with `python file.py`.
Use VS Code with the "Python" extension. It shows errors as you type.

---

## Week 1: Python basics with chip data

### Variables, numbers, strings
```python
clock_period_ns = 2.5
freq_mhz = 1000 / clock_period_ns          # 400.0
cell = "sky130_fd_sc_hd__dfrtp_1"
print(f"Clock {freq_mhz:.1f} MHz, cell {cell}")   # f-string: formatted text
print(cell.split("__")[1])                 # "dfrtp_1"
print(cell.upper(), len(cell), cell.endswith("_1"))
```

### Lists: ordered collections
```python
slacks = [-0.52, -0.31, 0.79, 1.45, -0.08]
print(min(slacks))                         # WNS = -0.52
print(sum(s for s in slacks if s < 0))     # TNS = -0.91
print(sorted(slacks)[:3])                  # 3 worst paths
violations = [s for s in slacks if s < 0]  # "list comprehension": filter in one line
```

### Dictionaries: name → value lookup
```python
port_width = {"clk": 1, "rst_n": 1, "data_in": 32, "addr": 16}
print(port_width["data_in"])               # 32
port_width["valid"] = 1                    # add a new entry
for name, width in port_width.items():
    print(f"{name:10s} {width:3d} bits")
total_bits = sum(port_width.values())
```

### if / for / while
```python
for slack in slacks:
    if slack < 0:
        print("VIOLATED", slack)
    elif slack < 0.1:
        print("marginal", slack)
    else:
        print("MET", slack)
```

**Exercise 1.** Make a dict of 5 cells with their area (e.g. `{"inv_1": 3.75, ...}`)
and a dict of instance counts. Print the total area and the largest contributor.

---

## Week 2: Functions and reading files

### Functions: reusable blocks
```python
def utilization(cell_area, core_area):
    """Return utilization as a fraction (0..1)."""
    return cell_area / core_area

print(f"{utilization(8140, 13378):.1%}")   # 60.8%
```
**In the toolkit:** `clog2()` and `format_table()` in `vlsi_toolkit/common.py`.

### Reading and writing files
```python
with open("examples/counter.v") as f:      # "with" closes the file automatically
    for line_no, line in enumerate(f, start=1):
        if "always" in line:
            print(line_no, line.strip())

with open("output/notes.txt", "w") as f:
    f.write("lint done\n")
```

### pathlib: working with folders
```python
from pathlib import Path
for log in Path("examples/regression_logs").glob("*.log"):
    text = log.read_text()
    print(log.name, "FAIL" if "UVM_ERROR /" in text else "ok")
```
Run this and compare with `python vlsi.py regress examples/regression_logs`. The simple
check above **misses** `fifo_directed_test` (a Questa `# ** Error`) and `uart_timeout_test`
(a `UVM_FATAL`). Real logs have many formats, so the real tool needs a list of patterns.
**In the toolkit:** `analyze_log()` and `_ERROR_RES` in `vlsi_toolkit/regress.py`.

**Exercise 2.** Write `count_lines.py` that prints, for every `.v` file in `examples/`,
the number of lines, `always` blocks and `assign` statements.

---

## Week 3: Regular expressions (the most important skill)

Every EDA report is text. Regular expressions ("regex") pull numbers and names out of it.

| Pattern | Means | Example match |
|---|---|---|
| `\d+` | one or more digits | `1500` |
| `-?\d+\.\d+` | decimal number, maybe negative | `-0.52` |
| `\w+` | word: letters, digits, `_` | `u_alu` |
| `\s*` | any amount of spaces | |
| `(...)` | capture group: the part you want | |
| `^` / `$` | start / end of line | |

```python
import re
line = "           -0.52   slack (VIOLATED)"
m = re.search(r"(-?\d+\.\d+)\s+slack\s+\((MET|VIOLATED)\)", line)
if m:
    print(float(m.group(1)), m.group(2))   # -0.52 VIOLATED

text = open("examples/counter.v").read()
print(re.findall(r"\b(input|output)\b", text))      # all directions
print(re.findall(r"parameter\s+(\w+)\s*=\s*(\w+)", text))   # [('WIDTH','8'), ('STEP','1')]
```
Practice regex interactively at **regex101.com** (choose the "Python" flavor).
Don't paste company data into websites, though. Use made-up lines.

**In the toolkit:** `_parse_sta_style()` in `vlsi_toolkit/timing_report.py`, and `_ERROR_RES` in `regress.py`.

**Exercise 3.** From `examples/sta_report.rpt`, print every `Startpoint` and `Endpoint` pair.
Then do the same using the toolkit: `from vlsi_toolkit import timing_report`.

---

## Week 4: Organising data with dataclasses and modules

```python
from dataclasses import dataclass

@dataclass
class TimingPath:
    startpoint: str
    endpoint: str
    slack: float

    @property
    def violated(self):
        return self.slack < 0

p = TimingPath("a_reg", "b_reg", -0.2)
print(p, p.violated)
```
A **module** is just a `.py` file, and a **package** is a folder of modules
(`vlsi_toolkit/`). `from vlsi_toolkit import spice` loads `vlsi_toolkit/spice.py`.

**In the toolkit:** the `Port` and `Module` classes in `verilog_parser.py`, and `Component` in `pd_analyzer.py`.

**Exercise 4.** Create a `Register` dataclass (name, offset, access) and a list of 4
registers. Print them sorted by offset. Then compare with `regmap_gen.py`.

---

## Week 5: CSV, JSON and Excel, the formats your team shares

```python
import csv, json

# write CSV (opens in Excel)
with open("output/paths.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["start", "end", "slack"])
    w.writerow(["a_reg", "b_reg", -0.2])

# JSON: config files and specs
spec = json.load(open("examples/uart_regmap.json"))
for reg in spec["registers"]:
    print(reg["name"], reg["offset"], reg["access"])
```
To use Excel files directly, run `pip install openpyxl pandas`, then call `pandas.read_excel("regs.xlsx")`.

**Exercise 5.** Run `python vlsi.py timing examples/sta_report.rpt --csv output/t.csv`,
then write a script that reads `t.csv` and prints only the hold violations.

---

## Week 6: Running EDA tools from Python (automation)

```python
import subprocess
result = subprocess.run(["iverilog", "-o", "sim.out", "tb.v", "dut.v"],
                        capture_output=True, text=True)
print("return code:", result.returncode)
print(result.stdout, result.stderr)
```
This is how you automate a flow: generate files, run the tool, parse the log, and decide what to do next.

**In the toolkit:** `run_ngspice()` in `spice.py` runs ngspice and parses the `.meas` results.

**Exercise 6.** Write `run_all.py`. For every `tb_*.v` in `output/`, run Icarus Verilog and
save the log to `logs/<name>.log`. Then run `python vlsi.py regress logs`.

---

## Week 7: Command-line tools with argparse

```python
import argparse
parser = argparse.ArgumentParser(description="Check slack")
parser.add_argument("report")
parser.add_argument("--limit", type=float, default=0.0)
args = parser.parse_args()
print(args.report, args.limit)
```
**In the toolkit:** `build_parser()` in `vlsi_toolkit/cli.py`. Every command is wired up there.

**Exercise 7.** Add your own command to the toolkit, for example
`python vlsi.py count <file.v>`, which prints the number of always blocks.
1. Write `cmd_count(args)` in `cli.py`.
2. Add a sub-parser in `build_parser()`.
3. Add a test in `tests/` and run `python -m unittest`.

---

## Week 8: Plots and data analysis

```bash
pip install matplotlib pandas
```
```python
import matplotlib.pyplot as plt
vdd   = [1.2, 1.4, 1.6, 1.8]
delay = [78, 55, 45, 41]          # ps, e.g. from 'spice sweep --run'
plt.plot(vdd, delay, marker="o")
plt.xlabel("VDD (V)"); plt.ylabel("tpd (ps)"); plt.grid(True)
plt.savefig("output/delay_vs_vdd.png")
```
**In the toolkit:** `plot_histogram()` in `timing_report.py`. Try `python vlsi.py timing examples/sta_report.rpt --plot output/slack.png`.

**Exercise 8.** Plot slack against path index, colored red when violated and green when met.

---

## Debugging tips

- **Read the error from the bottom up.** The last line says *what* went wrong, and the lines above say *where*.
- Use `print(type(x), x)` everywhere when confused.
- Put `breakpoint()` in your code to pause and inspect variables (type `c` to continue and `q` to quit).
- Run the tests after every change: `python -m unittest`.

## Using this at work

- **Company data stays inside the company.** Don't paste netlists, logs, or reports into
  websites or public AI tools unless your company allows it.
- Check your company's rules before installing Python packages on work machines. The core
  of this toolkit needs **no extra packages**, which is why it was written that way.
- Commit your scripts to your team's git repository. Teammates will reuse them.
- Start small. One script that saves you 10 minutes a day saves about 40 hours a year.

## Where to go next

| Area | Learn |
|---|---|
| Verification | **cocotb** (Python testbenches), **pyuvm** (UVM in Python) |
| RTL | **pyslang** (a real SystemVerilog compiler in Python), **Amaranth** (hardware in Python) |
| Physical design | **OpenROAD** Python API, **KLayout** Python scripting (GDS), the Tcl scripting of your P&R tool |
| Analog | **PySpice**, **ngspice**, numpy and scipy for waveform math |
| General | the book *Automate the Boring Stuff with Python* (free online) |
