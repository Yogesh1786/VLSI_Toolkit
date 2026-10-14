// The list of tools: used by the sidebar, the overview page and the Ctrl+K switcher.
import {
  Activity,
  ArrowLeftRight,
  BookMarked,
  ChartSpline,
  FolderGit2,
  ChartLine,
  CircuitBoard,
  ClipboardCheck,
  Cpu,
  FlaskConical,
  GitCompareArrows,
  Grid3x3,
  ListChecks,
  Network,
  ShieldCheck,
  SlidersHorizontal,
  Table2,
  Timer,
  Cpu as Chip,
  Zap,
  FileCheck2,
  type LucideIcon,
} from "lucide-react";

export type Tool = {
  path: string;
  title: string;
  area: Area;
  icon: LucideIcon;
  description: string;
};

export type Area =
  | "Workspace"
  | "RTL design"
  | "Verification"
  | "Physical design"
  | "Analog"
  | "Tracking";

export const AREAS: { name: Area; blurb: string }[] = [
  {
    name: "Workspace",
    blurb:
      "Your project folder: every file found, analyzed and tracked over time.",
  },
  {
    name: "RTL design",
    blurb: "Understand and check RTL before it reaches simulation.",
  },
  {
    name: "Verification",
    blurb: "Generate testbenches and triage regression results fast.",
  },
  {
    name: "Physical design",
    blurb: "Read sign-off reports and placement databases.",
  },
  {
    name: "Analog",
    blurb: "Sanity-check netlists and measure transient results.",
  },
  {
    name: "Tracking",
    blurb: "See what changed between two runs: regressions, timing, ECOs.",
  },
];

export const TOOLS: Tool[] = [
  {
    path: "/workspace",
    title: "Project Workspace",
    area: "Workspace",
    icon: FolderGit2,
    description: "Open a folder, analyze everything at once",
  },
  {
    path: "/trends",
    title: "Trends",
    area: "Workspace",
    icon: ChartSpline,
    description: "Health metrics of saved runs over time",
  },
  {
    path: "/modules",
    title: "Module Explorer",
    area: "RTL design",
    icon: Cpu,
    description: "Ports, parameters and widths; instantiation template",
  },
  {
    path: "/hierarchy",
    title: "Hierarchy & FSM",
    area: "RTL design",
    icon: Network,
    description: "Instance tree, black boxes, auto-drawn state diagrams",
  },
  {
    path: "/lint",
    title: "RTL Lint",
    area: "RTL design",
    icon: ListChecks,
    description: "Multi-drivers, latches, blocking in flops, missing defaults",
  },
  {
    path: "/regmap",
    title: "Register Map",
    area: "RTL design",
    icon: Table2,
    description: "One spec → Verilog RTL, C header and HTML docs",
  },
  {
    path: "/testbench",
    title: "Testbench Generator",
    area: "Verification",
    icon: FlaskConical,
    description: "Verilog and cocotb testbenches with clock and reset",
  },
  {
    path: "/regression",
    title: "Regression Triage",
    area: "Verification",
    icon: ClipboardCheck,
    description: "PASS/FAIL per log, failures grouped by signature",
  },
  {
    path: "/vcd",
    title: "Waveform Viewer",
    area: "Verification",
    icon: Activity,
    description: "VCD waveforms, clocks, glitches and X values",
  },
  {
    path: "/sva",
    title: "Assertion Generator",
    area: "Verification",
    icon: ShieldCheck,
    description: "SVA for AXI rules, FSM states/transitions, one-hot",
  },
  {
    path: "/axi",
    title: "AXI Protocol Checker",
    area: "Verification",
    icon: ArrowLeftRight,
    description: "AXI rule checks and transactions from a VCD",
  },
  {
    path: "/timing",
    title: "Timing (STA)",
    area: "Physical design",
    icon: Timer,
    description: "WNS/TNS, slack histogram, worst paths",
  },
  {
    path: "/floorplan",
    title: "Floorplan",
    area: "Physical design",
    icon: Grid3x3,
    description: "Utilization, cell mix, placement density heatmap",
  },
  {
    path: "/liberty",
    title: "Liberty Explorer",
    area: "Physical design",
    icon: BookMarked,
    description: "Cells, area, leakage and NLDM delay tables of a .lib",
  },
  {
    path: "/synthesis",
    title: "Synthesis Report",
    area: "Physical design",
    icon: Chip,
    description: "Area per module and cell usage (Yosys / DC)",
  },
  {
    path: "/power",
    title: "Power Report",
    area: "Physical design",
    icon: Zap,
    description: "Dynamic vs leakage, power groups, per-instance power",
  },
  {
    path: "/sdc",
    title: "SDC Checker",
    area: "Physical design",
    icon: FileCheck2,
    description: "Find mistakes in timing constraints",
  },
  {
    path: "/netlist",
    title: "Netlist Check",
    area: "Analog",
    icon: CircuitBoard,
    description: "Devices, MOSFET W/L, floating nodes and gates",
  },
  {
    path: "/sweep",
    title: "Parameter Sweep",
    area: "Analog",
    icon: SlidersHorizontal,
    description: "Netlists for a .param sweep, optional ngspice run",
  },
  {
    path: "/measure",
    title: "Waveform Measure",
    area: "Analog",
    icon: ChartLine,
    description: "Rise/fall time, delay, frequency, duty cycle",
  },
  {
    path: "/compare",
    title: "Compare Runs",
    area: "Tracking",
    icon: GitCompareArrows,
    description: "New failures & fixes, timing before/after ECO",
  },
];

export const toolByPath = (path: string) => TOOLS.find((t) => t.path === path);
