import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import Overview from "./pages/Overview";
import ModuleExplorer from "./pages/ModuleExplorer";
import Lint from "./pages/Lint";
import RegisterMap from "./pages/RegisterMap";
import Testbench from "./pages/Testbench";
import Regression from "./pages/Regression";
import Waveform from "./pages/Waveform";
import Timing from "./pages/Timing";
import Floorplan from "./pages/Floorplan";
import NetlistCheck from "./pages/NetlistCheck";
import Sweep from "./pages/Sweep";
import Measure from "./pages/Measure";
import Hierarchy from "./pages/Hierarchy";
import Liberty from "./pages/Liberty";
import Compare from "./pages/Compare";
import AxiChecker from "./pages/AxiChecker";
import Workspace from "./pages/Workspace";
import Trends from "./pages/Trends";
import AssertionGen from "./pages/AssertionGen";
import SynthesisReport from "./pages/SynthesisReport";
import PowerReport from "./pages/PowerReport";
import SdcChecker from "./pages/SdcChecker";
import { EmptyState } from "./components/ui";
import { SearchX } from "lucide-react";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/workspace" element={<Workspace />} />
        <Route path="/trends" element={<Trends />} />
        <Route path="/modules" element={<ModuleExplorer />} />
        <Route path="/hierarchy" element={<Hierarchy />} />
        <Route path="/lint" element={<Lint />} />
        <Route path="/regmap" element={<RegisterMap />} />
        <Route path="/testbench" element={<Testbench />} />
        <Route path="/regression" element={<Regression />} />
        <Route path="/vcd" element={<Waveform />} />
        <Route path="/axi" element={<AxiChecker />} />
        <Route path="/sva" element={<AssertionGen />} />
        <Route path="/timing" element={<Timing />} />
        <Route path="/floorplan" element={<Floorplan />} />
        <Route path="/netlist" element={<NetlistCheck />} />
        <Route path="/sweep" element={<Sweep />} />
        <Route path="/measure" element={<Measure />} />
        <Route path="/liberty" element={<Liberty />} />
        <Route path="/synthesis" element={<SynthesisReport />} />
        <Route path="/power" element={<PowerReport />} />
        <Route path="/sdc" element={<SdcChecker />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="*" element={<EmptyState icon={SearchX} title="Page not found" text="Pick a tool from the sidebar." />} />
      </Routes>
    </Layout>
  );
}
