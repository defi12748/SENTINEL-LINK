"use client";

import { useState } from "react";
import { Background, Controls, Handle, MarkerType, Position, ReactFlow, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { ScenarioResult } from "@/lib/api";
import { reasonCodes } from "./reasons";

type Tone = "ok" | "alert" | "bad" | "info";
interface Stage {
  id: string; title: string; gate: string; tone: Tone; summary: string;
  input: [string, string][]; check: [string, string][]; result: [string, string][];
}

const PER_ROW = 5;
const short = (h?: string) => (h ? `${h.slice(0, 10)}…${h.slice(-6)}` : "—");

export function buildStages(r: ScenarioResult, station?: string): Stage[] {
  const q = r.frames.filter(f => f.decision === "QUARANTINE").length;
  const v = r.frames.filter(f => f.decision === "VERIFY").length;
  const behind = r.frames.filter(f => (f.evidence.u_behind ?? 0) > 4 || (f.evidence.u_ahead ?? 0) > 4).length;
  const physics = r.frames.filter(f => reasonCodes(f).some(c => ["TELEMETRY_OUTLIER", "CARRIER_STEP", "DOPPLER_OFF_TRACK"].includes(c.code))).length;
  const oa = r.onair.frames ?? [];
  const oaRed = oa.filter(x => x.clock.status === "RED").length;
  const oaLimitsGreen = oa.filter(x => x.status === "GREEN").length;
  const alarms = r.interference.alarms;
  const dups = r.duplicates ?? [];
  const attacked = r.score.tp + r.score.fn;
  const prevented = r.score.fn === 0 && (!r.truth.interference || !!r.interference.detected_truth);
  return [
    {
      id: "rec", title: "Recording", gate: r.manifest.authentic ? "INTACT" : "EDITED", tone: r.manifest.authentic ? "ok" : "bad",
      summary: r.manifest.authentic ? "Matches the signed capture" : `${r.manifest.tampered_intervals.length} edited span(s) found`,
      input: [["Source", `SatNOGS · ${station ?? r.truth.observation_id}`], ["Length", `${r.duration_s.toFixed(0)} s, 48 kHz audio`]],
      check: [["Method", "Per-second SHA-256 Merkle tree, Ed25519 signature from capture"], ["Signed root", short(r.manifest_root)]],
      result: r.manifest.tampered_intervals.length
        ? r.manifest.tampered_intervals.slice(0, 4).map(([a, b], i) => [`Edit ${i + 1}`, `${a.toFixed(0)}–${b.toFixed(0)} s`] as [string, string])
        : [["Verdict", "No second differs from the capture"]],
    },
    {
      id: "spec", title: "Spectrum", gate: alarms.length ? "JAMMER" : "CLEAR", tone: alarms.length ? "alert" : "ok",
      summary: alarms.length ? `Interference near ${(alarms[0].freq_hz / 1000).toFixed(2)} kHz` : "No added interference seen",
      input: [["Band", `${(r.spectrogram.f_min / 1000).toFixed(1)}–${(r.spectrogram.f_max / 1000).toFixed(1)} kHz around the downlink`]],
      check: [["Method", "Spectral kurtosis, prominence, persistence, BPSK symmetry → calibrated classifier"], ["Alarm threshold", r.interference.threshold.toFixed(3)]],
      result: alarms.length
        ? alarms.slice(0, 4).map(a => [`${a.start_s.toFixed(0)}–${a.end_s.toFixed(0)} s`, `${(a.freq_hz / 1000).toFixed(2)} kHz, p=${a.peak_prob.toFixed(3)}`] as [string, string])
        : [["Verdict", r.truth.interference ? "Jammer too weak to see" : "Clean spectrum"]],
    },
    {
      id: "twin", title: "Audio Twin", gate: dups.length ? `${dups.length} COPIED` : "NO COPIES", tone: dups.length ? "bad" : "ok",
      summary: dups.length ? `${dups[0].start_s.toFixed(0)}–${dups[0].end_s.toFixed(0)} s repeats ${dups[0].src_start_s.toFixed(0)} s` : "No stretch of audio occurs twice",
      input: [["Signal", "Downlink mixed to 1 kHz complex baseband, whitened"]],
      check: [["Method", "2 s blocks cross-correlated against the whole file (no decoder)"], ["Threshold", `r ≥ ${r.duplicate_trace?.threshold ?? 0.5}, fixed a priori`]],
      result: dups.length
        ? dups.slice(0, 4).map(m => [`${m.start_s.toFixed(0)}–${m.end_s.toFixed(0)} s`, `copy of ${m.src_start_s.toFixed(0)} s, r=${m.ncc.toFixed(3)}`] as [string, string])
        : [["Verdict", "No copied audio"], ["Best r", `${Math.max(0, ...(r.duplicate_trace?.block_ncc ?? [0])).toFixed(3)}`]],
    },
    {
      id: "dec", title: "Decode", gate: `${r.frames.length} FRAMES`, tone: "info",
      summary: "gr-satellites + AO-40 FEC, exact frame timing",
      input: [["Modulation", "DBPSK 1200 Bd, AO-73 (FUNcube-1)"]],
      check: [["Chain", "FLL → clock recovery → differential detection → per-block AO-40 FEC"], ["Integrity", "Two Reed–Solomon codes per frame"]],
      result: [["Frames decoded", `${r.frames.length}`], ["Timing", "Each frame bound to its sync position"]],
    },
    {
      id: "onair", title: "NASA OnAIR", gate: r.onair.available ? (oaRed ? `${oaRed} RED` : "GREEN") : "N/A", tone: !r.onair.available ? "info" : oaRed ? "bad" : "ok",
      summary: r.onair.available ? `Limits: ${oaLimitsGreen}/${oa.length} GREEN · clock plugin: ${oaRed} RED` : "OnAIR not installed",
      input: [["Framework", "NASA OnAIR (GSFC), from NOS3"], ["Telemetry", "12 housekeeping channels + frame counter"]],
      check: [["OnAIR test suite", "FEASIBILITY limits learned from training passes"], ["Our OnAIR plugin", "Frame counter vs. spacecraft clock"]],
      result: [["Limit checks", `${oaLimitsGreen} GREEN: replayed data looks plausible`], ["Clock plugin", `${oaRed} frames RED`], ["Run time", `${r.onair.ms ?? "—"} ms`]],
    },
    {
      id: "clock", title: "Clock Check", gate: behind ? `${behind} OFF CLOCK` : "CONSISTENT", tone: behind ? "bad" : "ok",
      summary: "On-board counter vs. reception time",
      input: [["Model", `One frame every ${r.clock.period_s.toFixed(4)} s, fitted on the public archive`]],
      check: [["Rule", "Counter must sit on the clock line (within 1 frame)"]],
      result: [["Frames off the clock", `${behind}`]],
    },
    {
      id: "phys", title: "Physics & Telemetry", gate: physics ? `${physics} ODD` : "CONSISTENT", tone: physics ? "alert" : "ok",
      summary: "Doppler continuity, telemetry neighbours",
      input: [["Tracks", "Carrier frequency and level at 10 Hz"]],
      check: [["Splice", "Doppler/level steps at frame boundaries"], ["Content", "PyOD ECOD on neighbour-relative telemetry"]],
      result: [["Frames with physical evidence", `${physics}`]],
    },
    {
      id: "fusion", title: "Decision", gate: q ? `${q} QUARANTINED` : v ? `${v} TO VERIFY` : "ALL ACCEPTED", tone: q ? "bad" : v ? "alert" : "ok",
      summary: `${q} quarantined · ${v} to verify · ${r.frames.length - q - v} accepted`,
      input: [["Evidence", "11 calibrated inputs per frame"]],
      check: [["Rule", "p ≥ 0.9 quarantine · p ≥ 0.5 verify"]],
      result: [["Quarantined", `${q}`], ["Verify", `${v}`], ["Accepted", `${r.frames.length - q - v}`]],
    },
    {
      id: "ledger", title: "Ledger", gate: "SIGNED", tone: "info",
      summary: `${Object.keys(r.ledger_refs ?? {}).length + 1} entries appended`,
      input: [["Records", "Run summary + every non-accepted frame"]],
      check: [["Chain", "SHA-256 hash chain, Ed25519 checkpoints"]],
      result: [["Head", short(r.ledger_head)]],
    },
    {
      id: "out", title: "Outcome", gate: attacked ? (prevented ? "DETECTED" : "PARTIAL") : r.score.fp ? "FALSE ALARM" : "CLEAN", tone: prevented && !r.score.fp ? "ok" : "bad",
      summary: attacked ? `${r.score.tp}/${attacked} attacked frames caught, ${r.score.fp} false alarm(s)` : `${r.score.fp} false alarm(s)`,
      input: [["Attack", r.truth.variant]],
      check: [["Scored against", "Hidden attack intervals"]],
      result: [["Caught", `${r.score.tp}/${attacked}`], ["False alarms", `${r.score.fp}`], ["Jammer", r.truth.interference ? (r.interference.detected_truth ? "found at its frequency" : "missed") : "none"],
        ["Copied audio", r.duplicate_trace?.expected ? (r.duplicate_trace.detected_truth ? "found" : "missed") : `${dups.length} match(es)`]],
    },
  ];
}

type StageNode = Node<{ stage: Stage; order: number; active: boolean; select: () => void }, "stage">;

function StageCard({ data }: NodeProps<StageNode>) {
  const st = data.stage;
  return <button type="button" className={`wf-node ${st.tone} ${data.active ? "selected" : ""}`} onClick={data.select} aria-pressed={data.active}>
    <Handle type="target" position={Position.Top} id="top" />
    <Handle type="target" position={Position.Left} id="left" />
    <Handle type="target" position={Position.Right} id="right" />
    <span className="wf-num">{String(data.order + 1).padStart(2, "0")}</span>
    <span className="wf-title">{st.title}</span>
    <span className={`wf-gate ${st.tone}`}>{st.gate}</span>
    <span className="wf-sum">{st.summary}</span>
    <Handle type="source" position={Position.Bottom} id="bottom" />
    <Handle type="source" position={Position.Left} id="left" />
    <Handle type="source" position={Position.Right} id="right" />
  </button>;
}
const nodeTypes = { stage: StageCard };

export function PipelinePath({ result, station }: { result: ScenarioResult; station?: string }) {
  const stages = buildStages(result, station);
  const [sel, setSel] = useState("out");
  const s = stages.find(x => x.id === sel) ?? stages[0];
  return (
    <section className="obs-card">
      <div className="obs-head"><h3 className="heading-22 margin-0">Pipeline</h3><span className="label">Click a stage to inspect it</span></div>
      <div className="pipeline-mobile wf-scroll" aria-label="Pipeline stages">
        <div className="wf-graph">{stages.map((st, i) => <div className="wf-unit" key={st.id}>
          <button type="button" className={`wf-node ${st.tone} ${sel === st.id ? "selected" : ""}`} onClick={() => setSel(st.id)} aria-pressed={sel === st.id}>
            <span className="wf-num">{String(i + 1).padStart(2, "0")}</span><span className="wf-title">{st.title}</span>
            <span className={`wf-gate ${st.tone}`}>{st.gate}</span><span className="wf-sum">{st.summary}</span>
          </button>{i < stages.length - 1 && <span className="wf-edge" aria-hidden="true" />}
        </div>)}</div>
      </div>
      <div className="pipeline-canvas" aria-label="Analysis workflow graph">
        <ReactFlow<StageNode>
          nodes={stages.map((stage, i) => {
            const row = Math.floor(i / PER_ROW);
            const col = row % 2 === 0 ? i % PER_ROW : PER_ROW - 1 - i % PER_ROW;
            return { id: stage.id, type: "stage", position: { x: col * 270, y: row * 180 },
              data: { stage, order: i, active: sel === stage.id, select: () => setSel(stage.id) } };
          })}
          edges={stages.slice(0, -1).map((stage, i) => {
            const row = Math.floor(i / PER_ROW);
            const turn = i % PER_ROW === PER_ROW - 1;
            const colour = stage.tone === "bad" ? "#f64137" : stage.tone === "alert" ? "#ffc83d" : "#959599";
            return { id: `${stage.id}-${stages[i + 1].id}`, source: stage.id, target: stages[i + 1].id,
              sourceHandle: turn ? "bottom" : row % 2 === 0 ? "right" : "left",
              targetHandle: turn ? "top" : row % 2 === 0 ? "left" : "right",
              type: "smoothstep", style: { stroke: colour, strokeWidth: 2 }, markerEnd: { type: MarkerType.ArrowClosed, color: colour } };
          })}
          nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: .18, maxZoom: 1 }} minZoom={.25} maxZoom={1.5}
          nodesDraggable={false} nodesConnectable={false} colorMode="dark" preventScrolling={false}
          onNodeClick={(_, node) => setSel(node.id)}>
          <Background gap={22} size={1} color="#444447" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <div className="flow3">
        {([["INPUT", s.input], ["CHECK", s.check], ["RESULT", s.result]] as const).map(([h, rows]) => (
          <div key={h} className={`flow-panel ${h === "RESULT" ? s.tone : ""}`}>
            <div className="flow-panel-head">{h}</div>
            <dl>{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
          </div>
        ))}
      </div>
    </section>
  );
}
