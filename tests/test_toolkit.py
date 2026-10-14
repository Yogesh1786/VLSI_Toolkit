"""Unit tests.  Run from the project folder:   python -m unittest -v"""

import json
import py_compile
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from vlsi_toolkit import (
    common,
    regmap_gen,
    tb_generator,
    timing_report,
    vcd_analyzer,
    verilog_parser,
)
from vlsi_toolkit.cli import main


def run_cli(argv):
    """Run the CLI with its printed output hidden; return the exit code."""
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        return main(argv)


EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class TestCommon(unittest.TestCase):
    def test_eval_expr(self):
        env = {"WIDTH": 8, "DEPTH": 32}
        self.assertEqual(common.eval_expr("WIDTH-1", env), 7)
        self.assertEqual(common.eval_expr("$clog2(DEPTH)", env), 5)
        self.assertEqual(common.eval_expr("8'hFF + 4'b0001", env), 256)
        self.assertEqual(
            common.eval_expr("DEPTH/3", env), 10
        )  # integer division like Verilog
        self.assertIsNone(common.try_eval("UNKNOWN+1", env))

    def test_clog2(self):
        self.assertEqual(
            [common.clog2(n) for n in (1, 2, 3, 4, 5, 1024)], [0, 1, 2, 2, 3, 10]
        )

    def test_strip_comments_keeps_strings(self):
        src = 'a = 1; // note\n/* block\ncomment */ $display("http://x");'
        out = common.strip_comments(src)
        self.assertNotIn("note", out)
        self.assertNotIn("block", out)
        self.assertIn('"http://x"', out)
        self.assertEqual(out.count("\n"), src.count("\n"))


class TestVerilogParser(unittest.TestCase):
    def test_ansi_counter(self):
        m = verilog_parser.parse_file(EXAMPLES / "counter.v")[0]
        self.assertEqual(m.name, "counter")
        self.assertTrue(m.ansi)
        self.assertEqual([p.name for p in m.parameters], ["WIDTH", "STEP"])
        ports = {p.name: p for p in m.ports}
        self.assertEqual(ports["load_val"].width, 8)
        self.assertEqual(ports["count"].net_type, "reg")
        self.assertEqual(ports["count"].direction, "output")
        self.assertEqual(len(m.inputs), 6)

    def test_non_ansi_fifo(self):
        m = verilog_parser.parse_file(EXAMPLES / "fifo.v")[0]
        self.assertFalse(m.ansi)
        params = {p.name: p for p in m.parameters}
        self.assertEqual(params["ADDR_W"].value, 5)
        self.assertTrue(params["ADDR_W"].local)
        ports = {p.name: p for p in m.ports}
        self.assertEqual(ports["count"].width, 6)
        self.assertEqual(ports["dout"].net_type, "reg")
        self.assertEqual(ports["full"].direction, "output")
        self.assertEqual([p.name for p in m.ports][:2], ["clk", "rst"])

    def test_inherited_port_attributes(self):
        m = verilog_parser.parse_file(EXAMPLES / "alu.v")[0]
        ports = {p.name: p for p in m.ports}
        self.assertTrue(ports["b"].signed)  # "input signed [N-1:0] a, b"
        self.assertEqual(ports["b"].width, 32)
        self.assertEqual(ports["carry_out"].direction, "output")

    def test_multiple_modules_and_functions(self):
        src = """
        module leaf(input a, output y); assign y = ~a; endmodule
        module top #(parameter W = 4, parameter D = W*2) (
            input  logic [W-1:0][1:0] bus,
            output logic [D-1:0]      q
        );
            function automatic [3:0] f(input [3:0] x); f = x; endfunction
        endmodule
        """
        mods = verilog_parser.parse_text(src)
        self.assertEqual([m.name for m in mods], ["leaf", "top"])
        top = verilog_parser.pick_module(mods)
        self.assertEqual(top.name, "top")
        ports = {p.name: p for p in top.ports}
        self.assertEqual(ports["bus"].width, 8)  # [3:0][1:0] -> 4*2
        self.assertEqual(ports["q"].width, 8)
        self.assertEqual(len(top.ports), 2)  # function input not treated as a port


class TestTbGenerator(unittest.TestCase):
    def setUp(self):
        self.counter = verilog_parser.parse_file(EXAMPLES / "counter.v")[0]
        self.fifo = verilog_parser.parse_file(EXAMPLES / "fifo.v")[0]
        self.alu = verilog_parser.parse_file(EXAMPLES / "alu.v")[0]

    def test_clock_reset_detection(self):
        clocks, resets, data = tb_generator.classify(self.counter)
        self.assertEqual([c.name for c in clocks], ["clk"])
        self.assertEqual([r.name for r in resets], ["rst_n"])
        self.assertTrue(tb_generator.reset_active_low(resets[0]))
        _, fifo_resets, _ = tb_generator.classify(self.fifo)
        self.assertFalse(tb_generator.reset_active_low(fifo_resets[0]))

    def test_verilog_tb(self):
        tb = tb_generator.verilog_tb(self.counter)
        self.assertIn("module tb_counter;", tb)
        self.assertIn(".load_val (load_val)", tb)
        self.assertIn("always #(CLK_PERIOD/2) clk = ~clk;", tb)
        self.assertIn("rst_n = 1'b0;", tb)
        self.assertTrue(tb.rstrip().endswith("endmodule"))

    def test_tb_declares_localparams_used_in_ports(self):
        tb = tb_generator.verilog_tb(self.fifo)
        self.assertIn("localparam ADDR_W = $clog2(DEPTH);", tb)
        self.assertIn("rst = 1'b1;  // assert (active-high)", tb)

    def test_combinational_tb_uses_delays(self):
        tb = tb_generator.verilog_tb(self.alu)
        self.assertNotIn("posedge", tb)
        self.assertIn("#(CLK_PERIOD);", tb)

    def test_cocotb_is_valid_python(self):
        code = tb_generator.cocotb_test(self.counter, EXAMPLES / "counter.v")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "test_counter.py"
            path.write_text(code, encoding="utf-8")
            py_compile.compile(str(path), doraise=True)


class TestTimingReport(unittest.TestCase):
    def test_sample_report(self):
        paths = timing_report.parse_file(EXAMPLES / "sta_report.rpt")
        self.assertEqual(len(paths), 10)
        s = timing_report.summarize(paths)
        self.assertEqual(s["setup"]["violations"], 3)
        self.assertAlmostEqual(s["setup"]["wns"], -0.52)
        self.assertAlmostEqual(s["setup"]["tns"], -0.91)
        self.assertEqual(s["hold"]["violations"], 1)
        self.assertAlmostEqual(paths[0].arrival, 5.41)
        self.assertAlmostEqual(paths[0].required, 4.89)

    def test_primetime_style(self):
        rpt = """
  Startpoint: a_reg (rising edge-triggered flip-flop clocked by clk)
  Endpoint: b_reg (rising edge-triggered flip-flop clocked by clk)
  Path Group: clk
  Path Type: max
  data arrival time                                  2.30
  data required time                                 2.10
  slack (VIOLATED)                                  -0.20
"""
        p = timing_report.parse_report(rpt)[0]
        self.assertEqual(
            (p.startpoint, p.endpoint, p.check), ("a_reg", "b_reg", "setup")
        )
        self.assertAlmostEqual(p.slack, -0.20)

    def test_vivado_style(self):
        rpt = """
Slack (VIOLATED) :        -0.123ns  (required time - arrival time)
  Source:                 core/x_reg/C
  Destination:            core/y_reg/D
  Path Group:             sys_clk
  Path Type:              Setup (Max at Slow Process Corner)

Slack (MET) :             0.045ns  (arrival time - required time)
  Source:                 core/p_reg/C
  Destination:            core/q_reg/D
  Path Group:             sys_clk
  Path Type:              Hold (Min at Fast Process Corner)
"""
        paths = timing_report.parse_report(rpt)
        self.assertEqual([p.check for p in paths], ["setup", "hold"])
        self.assertAlmostEqual(paths[0].slack, -0.123)
        self.assertEqual(paths[1].endpoint, "core/q_reg/D")


class TestRegmap(unittest.TestCase):
    def test_example_spec(self):
        rm = regmap_gen.load_spec(EXAMPLES / "uart_regmap.json")
        regs = {r.name: r for r in rm.registers}
        self.assertEqual(regs["CTRL"].reset, 0x1B0)
        self.assertEqual(regs["CTRL"].mask, 0xFFFFF)
        self.assertEqual(regs["SCRATCH"].reset, 0xDEADBEEF)
        self.assertEqual(rm.addr_width, 5)
        v = regmap_gen.gen_verilog(rm)
        self.assertIn("module uart_regs", v)
        self.assertIn("int_status_set_i", v)
        h = regmap_gen.gen_c_header(rm)
        self.assertIn("#define UART_CTRL_BAUD_DIV_MASK  0x000FFFF0U", h)

    def _spec(self, **reg_overrides):
        reg = {
            "name": "A",
            "offset": "0x0",
            "access": "RW",
            "fields": [{"name": "X", "bits": "3:0"}],
        }
        reg.update(reg_overrides)
        return {
            "block": "blk",
            "data_width": 32,
            "registers": [reg, {"name": "B", "offset": "0x4"}],
        }

    def test_validation_errors(self):
        bad_cases = [
            self._spec(offset="0x4"),  # duplicate offset with B
            self._spec(offset="0x2"),  # unaligned
            self._spec(access="RX"),  # bad access type
            self._spec(
                fields=[{"name": "X", "bits": "3:0"}, {"name": "Y", "bits": "2"}]
            ),  # overlap
            self._spec(fields=[{"name": "X", "bits": "40:33"}]),  # beyond data width
            self._spec(
                fields=[{"name": "X", "bits": "1:0", "reset": "0x7"}]
            ),  # reset too wide
        ]
        for spec in bad_cases:
            with self.assertRaises(regmap_gen.RegMapError, msg=json.dumps(spec)):
                regmap_gen.build_regmap(spec)


class TestVcd(unittest.TestCase):
    def test_sample(self):
        vcd = vcd_analyzer.parse_file(EXAMPLES / "sample.vcd")
        stats = {s.name: s for s in vcd_analyzer.analyze(vcd, glitch_threshold=2)}
        self.assertEqual(vcd.end_time, 400)
        self.assertEqual(stats["tb.clk"].period, 10)
        self.assertAlmostEqual(stats["tb.clk"].duty, 0.5)
        self.assertEqual(stats["tb.dut.ack"].glitches, 2)
        self.assertEqual(stats["tb.dut.irq"].toggles, 0)
        self.assertIsNotNone(stats["tb.dut.data_bus"].x_after)  # X until t=80
        self.assertIsNone(stats["tb.dut.count"].x_after)  # X only during reset
        self.assertEqual(stats["tb.dut.count"].width, 4)


class TestCli(unittest.TestCase):
    def test_all_commands_run(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run_cli(["parse", str(EXAMPLES / "fifo.v"), "--json"]), 0)
            self.assertEqual(
                run_cli(["tb", str(EXAMPLES / "counter.v"), "-o", d, "--cocotb"]), 0
            )
            self.assertTrue((Path(d) / "tb_counter.v").exists())
            self.assertEqual(
                run_cli(
                    [
                        "timing",
                        str(EXAMPLES / "sta_report.rpt"),
                        "--csv",
                        str(Path(d) / "t.csv"),
                    ]
                ),
                0,
            )
            self.assertEqual(
                run_cli(
                    ["timing", str(EXAMPLES / "sta_report.rpt"), "--fail-on-violation"]
                ),
                2,
            )
            self.assertEqual(
                run_cli(["regmap", str(EXAMPLES / "uart_regmap.json"), "-o", d]), 0
            )
            self.assertTrue((Path(d) / "uart_regs.html").exists())
            self.assertEqual(run_cli(["vcd", str(EXAMPLES / "sample.vcd")]), 0)
            self.assertEqual(run_cli(["parse", "does_not_exist.v"]), 1)


if __name__ == "__main__":
    unittest.main()
