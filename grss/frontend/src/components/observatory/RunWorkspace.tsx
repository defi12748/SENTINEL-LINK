"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import type { ObservationSummary, ScenarioResult } from "@/lib/api";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ClockChart, DopplerChart, FrameRibbon, MerkleStrip, SpectrogramView, TwinChart } from "../Charts";
import { DecisionChip } from "../ui";
import { FrameInspector } from "./FrameInspector";
import { PipelinePath } from "./PipelinePath";

const Globe = dynamic(() => import("../Globe"), { ssr: false });
const TABS = ["Workflow", "Frames", "Signal", "Provenance", "Orbit", "Event stream"] as const;
type Tab = typeof TABS[number];
export interface SavedRun { result: ScenarioResult; title: string; station: string; }

function OrbitView({ result, observation, selected }: {
  result: ScenarioResult; observation?: ObservationSummary; selected: number | null;
}) {
  const { data, error } = useApi(() => api.observation(result.truth.observation_id), [result.truth.observation_id]);
  const frame = result.frames.find(f => f.index === selected) ?? result.frames[0];
  const [time, setTime] = useState(frame?.t_rec ?? 0);
  const current = result.frames.reduce((a, f) => f.t_rec <= time ? f : a, result.frames[0]);
  if (error) return <p role="alert" className="red">{error}</p>;
  if (!data) return <p className="mono muted" role="status">Loading pass geometry…</p>;
  return <div className="run-orbit">
    <div className="run-orbit-canvas"><Globe orbit={data.orbit} pass={data.geometry}
      station={{ lat: data.record.station_lat, lon: data.record.station_lng }}
      playhead={time / result.duration_s} alert={!!current && current.decision !== "ACCEPT"}
      unix={Date.parse(data.record.start) / 1000} /></div>
    <div className="run-orbit-controls">
      <span className="label">{observation?.station ?? data.record.station_name} · AO-73</span>
      <label htmlFor="orbit-time">Pass time · {time.toFixed(1)} s</label>
      <input id="orbit-time" type="range" min={0} max={result.duration_s} step={0.1} value={time}
        onChange={e => setTime(Number(e.target.value))} />
      {current && <DecisionChip d={current.decision} />}
      <p className="p-sm muted">Orbit from the recording’s TLE. Link colour follows the selected run’s frame decisions.</p>
    </div>
  </div>;
}

export function RunWorkspace({ active, runs, observations, onChoose }: {
  active: SavedRun; runs: SavedRun[]; observations: ObservationSummary[]; onChoose: (run: SavedRun) => void;
}) {
  const [tab, setTab] = useState<Tab>("Workflow");
  const [selected, setSelected] = useState<number | null>(() => active.result.frames.find(f => f.decision !== "ACCEPT")?.index ?? null);
  const [filter, setFilter] = useState("ALL");
  const r = active.result;
  const observation = observations.find(o => o.id === r.truth.observation_id);
  const counts = { ACCEPT: 0, VERIFY: 0, QUARANTINE: 0 };
  r.frames.forEach(f => counts[f.decision]++);
  const bands = [
    ...(r.truth.replay ? [{ start: r.truth.replay.dst_start_s, end: r.truth.replay.dst_end_s, color: "#f64137", label: "REPLAY" }] : []),
    ...(r.truth.sequence ? [{ start: r.truth.sequence.dst_start_s, end: r.truth.sequence.dst_end_s, color: "#ea6f24", label: "SEQUENCE" }] : []),
  ];
  const events = r.frames.filter(f => filter === "ALL" || f.decision === filter);
  return <div className="run-workspace">
    <aside className="run-sidebar" aria-label="Run history">
      <div className="run-sidebar-head"><span className="label">Runs</span><span className="mono muted">{runs.length}</span></div>
      <p className="run-history-note">This session · last 8 runs</p>
      <div className="run-list">{runs.map(run => <button type="button" key={run.result.run_id}
        className={`run-link ${run.result.run_id === r.run_id ? "chosen" : ""}`}
        aria-current={run.result.run_id === r.run_id ? "true" : undefined} onClick={() => onChoose(run)}>
        <span className={`run-dot ${run.result.score.fn || run.result.score.fp ? "alert" : "ok"}`} />
        <span><strong>{run.title}</strong><small>{run.station} · #{run.result.truth.observation_id}</small><small>Seed {run.result.truth.seed} · {run.result.frames.length} frames</small></span>
      </button>)}</div>
      <div className="run-source"><span className="label">Recording</span><strong>{active.station}</strong>
        <span className="mono">#{r.truth.observation_id}</span><span>{observation?.start.slice(0, 10)} · {observation?.split}</span>
        <a href={`/passes/${r.truth.observation_id}`}>Inspect original pass ↗</a></div>
    </aside>
    <div className="run-main">
      <div className="run-breadcrumb"><span>Observatory / {active.title}{r.cache && r.cache.status !== "miss" ? " · Cached analysis" : ""}</span><span className="mono">{r.run_id.slice(-12)}</span></div>
      <div className="run-metrics">{([
        ["Decoded", r.frames.length, ""], ["Accepted", counts.ACCEPT, "info"],
        ["Verify", counts.VERIFY, "alert"], ["Quarantined", counts.QUARANTINE, "bad"],
      ] as const).map(([label, value, tone]) => <div key={label} className={tone}><span className="label">{label}</span><strong>{value}</strong></div>)}</div>
      <div className="run-case"><div><span className="label">{active.title}</span><p>AO-73 · {active.station} · seed {r.truth.seed}</p></div>
        <span className={`badge ${r.manifest.authentic ? "ok" : "bad"}`}>{r.manifest.authentic ? "CAPTURE INTACT" : "CAPTURE EDITED"}</span></div>
      <div className="run-tabs" role="tablist" aria-label="Run views">{TABS.map(t => <button key={t} type="button" role="tab"
        id={`tab-${t.replaceAll(" ", "-")}`} aria-controls="run-panel" aria-selected={tab === t} tabIndex={tab === t ? 0 : -1}
        onKeyDown={e => {
          const index = TABS.indexOf(t);
          const next = e.key === "ArrowRight" ? (index + 1) % TABS.length : e.key === "ArrowLeft" ? (index + TABS.length - 1) % TABS.length : e.key === "Home" ? 0 : e.key === "End" ? TABS.length - 1 : -1;
          if (next < 0) return;
          e.preventDefault(); setTab(TABS[next]);
          document.getElementById(`tab-${TABS[next].replaceAll(" ", "-")}`)?.focus();
        }} onClick={() => setTab(t)}>{t}{t === "Event stream" && <span>{r.frames.length}</span>}</button>)}</div>
      <div className="run-view" id="run-panel" role="tabpanel" aria-labelledby={`tab-${tab.replaceAll(" ", "-")}`}>
        {tab === "Workflow" && <><PipelinePath result={r} station={active.station} /><FrameInspector result={r} selected={selected} onSelect={setSelected} /></>}
        {tab === "Frames" && <><section className="obs-card"><div className="obs-head"><h3 className="heading-22 margin-0">Frame counter vs. clock</h3><span className="label">Select a frame to inspect</span></div><div className="run-chart"><ClockChart frames={r.frames} clock={r.clock} bands={bands} selected={selected} onSelect={setSelected} /><FrameRibbon frames={r.frames} labels={r.labels} selected={selected} onSelect={setSelected} /></div></section><FrameInspector result={r} selected={selected} onSelect={setSelected} /></>}
        {tab === "Signal" && <div className="run-signals"><section><h3 className="heading-22">Spectrum</h3><SpectrogramView spec={r.spectrogram} interference={r.interference} bands={bands} fOffset={(r.spectrogram.f_min + r.spectrogram.f_max) / 2} /></section><section><h3 className="heading-22">Doppler</h3><DopplerChart tracks={r.tracks} frames={r.frames} bands={bands} /></section></div>}
        {tab === "Provenance" && <div className="run-signals">
          <section><h3 className="heading-22">Signed capture · one leaf per second</h3>
            <p className="p-sm muted">The station signed a per-second Merkle tree of the clean recording (Ed25519). Red seconds no longer match it{r.manifest.tampered_intervals.length ? `: ${r.manifest.tampered_intervals.map(([a, b]) => `${a.toFixed(0)}–${b.toFixed(0)} s`).join(", ")}` : ""}.</p>
            <MerkleStrip duration={r.duration_s} tampered={r.manifest.tampered_intervals} /></section>
          {r.duplicate_trace && <section><h3 className="heading-22">Duplicate audio · no decoder</h3>
            <p className="p-sm muted">2 s blocks correlated against the whole file. Ribbons join a copied stretch to the earlier audio it repeats. Reported beside the fused decisions, not folded into them.</p>
            <TwinChart trace={r.duplicate_trace} matches={r.duplicates ?? []} duration={r.duration_s} bands={bands} /></section>}
        </div>}
        {tab === "Orbit" && <OrbitView result={r} observation={observation} selected={selected} />}
        {tab === "Event stream" && <div className="run-events"><label className="field">Decision<select value={filter} onChange={e => setFilter(e.target.value)} aria-label="Filter decisions">{["ALL", "ACCEPT", "VERIFY", "QUARANTINE"].map(d => <option key={d}>{d}</option>)}</select></label>
          <p className="mono muted">Ledger head · {r.ledger_head}</p>
          {events.map(f => <details key={f.index}><summary><span className="mono">{String(f.index).padStart(3, "0")}</span><strong>{f.t_rec.toFixed(1)} s</strong><DecisionChip d={f.decision} /><span className="mono">p = {f.probability.toFixed(4)}</span></summary>
            <pre>{JSON.stringify({ frame: f, ground_truth: r.label_kind[f.index] || "genuine", onair: r.onair.frames?.find(x => Math.abs(x.t_rec - f.t_rec) < 0.01), ledger: r.ledger_refs?.[String(f.index)] ?? null }, null, 2)}</pre></details>)}
        </div>}
      </div>
      <div className="run-outcome"><div><span className="label">Attacked frames caught</span><strong>{r.score.tp} / {r.score.tp + r.score.fn}</strong></div><div><span className="label">False alarms</span><strong>{r.score.fp}</strong></div><div><span className="label">Jammer</span><strong>{r.truth.interference ? r.interference.detected_truth ? "Detected" : "Missed" : "None added"}</strong></div><div><span className="label">Copied audio</span><strong>{r.duplicate_trace?.expected ? r.duplicate_trace.detected_truth ? "Found" : "Missed" : `${r.duplicates?.length ?? 0} match(es)`}</strong></div><div><span className="label">Capture signature</span><strong>{r.manifest.signature_valid ? "Valid" : "Invalid"}</strong></div></div>
    </div>
  </div>;
}
