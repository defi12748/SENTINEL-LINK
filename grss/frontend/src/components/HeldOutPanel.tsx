"use client";

import { useState } from "react";
import { api, type SampleResult, type UploadResult } from "@/lib/api";
import { Panel } from "./AttackLab";
import { ClockChart, DopplerChart, FrameRibbon, SpectrogramView, TwinChart } from "./Charts";
import { ButtonPrimary, Label } from "./ui";

/** Blind analysis of a recording supplied by someone else (the jury's held-out file). */
export function HeldOutPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [start, setStart] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<UploadResult | SampleResult | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [drag, setDrag] = useState(false);

  const run = async () => {
    if (!file) return;
    setBusy(true); setErr(null);
    try {
      setRes(await api.analyse(file, start || undefined));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const sample = async () => {
    setBusy(true); setErr(null);
    try {
      setRes(await api.sample(4242 + Math.floor(Math.random() * 3)));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };
  const truth = res && "truth" in res ? res.truth : null;

  const q = res?.frames.filter(f => f.decision === "QUARANTINE").length ?? 0;
  const v = res?.frames.filter(f => f.decision === "VERIFY").length ?? 0;
  const jamMissing = res?.missing.filter(m => m.under_interference).length ?? 0;

  return (
    <div style={{ display: "grid", gap: "1.5rem" }}>
      <div
        onDragOver={e => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) setFile(f); }}
        className="card"
        style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", alignItems: "end",
          borderStyle: "dashed", borderColor: drag ? "var(--nasa-red)" : undefined }}>
        <div className="field">
          <Label>Recording</Label>
          <input type="file" accept=".wav,.ogg,.flac,audio/*" onChange={e => setFile(e.target.files?.[0] ?? null)}
            style={{ color: "var(--carbon-20)" }} />
          <span className="p-sm muted">{file ? `${file.name} · ${(file.size / 2 ** 20).toFixed(1)} MB` : "or drop the file here"}</span>
        </div>
        <div className="field">
          <Label>Start UTC (optional)</Label>
          <input type="text" placeholder="2026-10-22T06:29:05Z" value={start} onChange={e => setStart(e.target.value)}
            style={{ background: "#000", color: "#fff", border: "1px solid var(--carbon-70)", padding: ".6rem .7rem", fontFamily: "var(--font-label)" }} />
        </div>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          <ButtonPrimary onClick={run} disabled={!file || busy}>{busy ? "Analysing…" : "Analyse"}</ButtonPrimary>
          {busy && <span className="spinner" />}
        </div>
        <div style={{ gridColumn: "1 / -1", display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
          <span className="p-sm" style={{ color: "var(--carbon-30)" }}>No recording at hand?</span>
          <ButtonPrimary onClick={sample} disabled={busy}>Analyse a held-out sample</ButtonPrimary>
          <span className="p-sm" style={{ color: "var(--carbon-40)" }}>A real pass, attacked with hidden parameters, analysed blind.</span>
        </div>
      </div>
      {err && <span className="mono red">{err}</span>}
      {truth && (
        <div style={{ borderLeft: "6px solid var(--carbon-60)", padding: "1rem 1.25rem", background: "#17171b" }}>
          <div className="label" style={{ color: "var(--carbon-30)" }}>Hidden truth (not seen by the analyser)</div>
          <p className="heading-18 margin-top-1 margin-bottom-0" style={{ color: "#fff" }}>
            {[
              truth.replay && `Replay of ${truth.replay.n_frames} frames at ${truth.replay.dst_start_s.toFixed(0)}–${truth.replay.dst_end_s.toFixed(0)} s`,
              truth.sequence && `${truth.sequence.variant} anomaly at ${truth.sequence.dst_start_s.toFixed(0)} s`,
              truth.interference && `${truth.interference.kind} jammer at ${(truth.interference.freq_hz / 1000).toFixed(2)} kHz, J/S ${truth.interference.js_db.toFixed(1)} dB, ${truth.interference.start_s.toFixed(0)}–${(truth.interference.start_s + truth.interference.dur_s).toFixed(0)} s`,
            ].filter(Boolean).join(" · ")}
          </p>
        </div>
      )}
      {res && (
        <div style={{ display: "grid", gap: "2rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "1.25rem" }}>
            <Fact k="Frames decoded" v={`${res.frames.length}`} note={`response: ${res.response.chosen}`} />
            <Fact k="Quarantined" v={`${q}`} accent={q > 0} />
            <Fact k="Verification requests" v={`${v + jamMissing}`} accent={v + jamMissing > 0}
              note={jamMissing ? `${jamMissing} transmitted frames lost under interference` : undefined} />
            <Fact k="Interference alarms" v={`${res.interference.alarms.length}`} accent={res.interference.alarms.length > 0}
              note={res.interference.alarms[0] ? `near ${res.interference.alarms[0].freq_hz.toFixed(0)} Hz` : undefined} />
            <Fact k="Copied audio" v={`${res.duplicates?.length ?? 0}`} accent={!!res.duplicates?.length}
              note={res.duplicates?.[0] ? `${res.duplicates[0].start_s.toFixed(0)}–${res.duplicates[0].end_s.toFixed(0)} s repeats ${res.duplicates[0].src_start_s.toFixed(0)} s` : "no stretch occurs twice"} />
            <Fact k="Absolute time" v={res.absolute_time === "given" ? "Given" : res.absolute_time === "inferred" ? "Inferred" : "Unavailable"}
              note={res.absolute_time === "inferred" ? "from the on-board clock" : res.absolute_time === "unknown" ? "No decoded counter to infer UTC" : undefined} />
          </div>
          <Panel title="Frame Counter vs. Clock" sub={`${res.file} · ${res.duration_s.toFixed(0)} s`}>
            <ClockChart frames={res.frames} clock={res.clock} selected={sel} onSelect={setSel} />
            <FrameRibbon frames={res.frames} selected={sel} onSelect={setSel} />
          </Panel>
          <div style={{ display: "grid", gap: "2rem", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 520px), 1fr))" }}>
            <Panel title="Spectrum">
              <SpectrogramView spec={res.spectrogram} interference={res.interference} fOffset={res.f_offset_hz} />
            </Panel>
            <Panel title="Doppler">
              <DopplerChart tracks={res.tracks} frames={res.frames} />
            </Panel>
          </div>
          {res.duplicate_trace && (
            <Panel title="Duplicate Audio" sub="No decoder: 2 s blocks correlated against the whole file">
              <TwinChart trace={res.duplicate_trace} matches={res.duplicates ?? []} duration={res.duration_s} />
            </Panel>
          )}
        </div>
      )}
    </div>
  );
}

function Fact({ k, v, note, accent = false }: { k: string; v: string; note?: string; accent?: boolean }) {
  return (
    <div style={{ borderTop: `3px solid ${accent ? "var(--nasa-red)" : "var(--carbon-60)"}`, paddingTop: ".9rem", display: "grid", gap: ".45rem" }}>
      <Label className="muted">{k}</Label>
      <div className="heading-36">{v}</div>
      {note && <div className="p-sm muted mono">{note}</div>}
    </div>
  );
}
