"use client";

import { useEffect, useRef, useState } from "react";
import { api, type ObservationSummary, type Overrides, type ScenarioResult } from "@/lib/api";
import { RunWorkspace, type SavedRun } from "./observatory/RunWorkspace";
import { ButtonPrimary, Label } from "./ui";

/* Opening run: a held-out pass and draw that exercises every stage (replay,
   sequence anomaly and a weak hidden jammer). "New random draw" explores the rest;
   the benchmark reports the full held-out distribution, misses included. */
export const DEMO = { observation: 15261075, seed: 4 };

type PresetKey = "standard" | "replay" | "cross" | "jam" | "clean";

const PRESETS: Record<PresetKey, { title: string; text: string; variant: string; overrides?: Overrides }> = {
  standard: { title: "Standard Test", text: "Replay 5–20 frames, inject one anomaly, add a hidden jammer.", variant: "standard" },
  replay: { title: "Replay", text: "Re-send a stretch of earlier frames over live ones.", variant: "standard",
    overrides: { sequence: false, interference: false } },
  cross: { title: "Replay From Another Day", text: "Splice in frames recorded on a different pass.", variant: "cross_pass_replay" },
  jam: { title: "Jammer", text: "Add narrowband interference at a hidden strength.", variant: "standard",
    overrides: { replay: false, sequence: false } },
  clean: { title: "No Attack", text: "Check that genuine frames are left alone.", variant: "clean" },
};

export function AttackLab({ observations, selectedId, onResult, autoRun = false }: {
  observations: ObservationSummary[]; selectedId: number | null; onResult: (r: ScenarioResult | null) => void; autoRun?: boolean;
}) {
  const [obsId, setObsId] = useState<number | null>(null);
  const id = obsId ?? selectedId ?? (observations.find(o => o.id === DEMO.observation) ?? observations.find(o => o.split === "held-out" && o.frames >= 40))?.id ?? null;
  const [preset, setPreset] = useState<PresetKey>("standard");
  const [seed, setSeed] = useState(DEMO.seed);
  const [custom, setCustom] = useState(false);
  const [ov, setOv] = useState<Overrides>({ n_replay: 10, seq_variant: "duplicate", jam_kind: "cw", js_db: -12, jam_freq_hz: 11300 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [runs, setRuns] = useState<SavedRun[]>([]);
  const [active, setActive] = useState<SavedRun | null>(null);
  const [configOpen, setConfigOpen] = useState(true);
  const pending = useRef(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("preset");
    if (q && q in PRESETS) setPreset(q as PresetKey);
    const obs = Number(params.get("obs"));
    if (obs) setObsId(obs);
  }, []);

  const run = async () => {
    if (id === null || pending.current) return;
    pending.current = true;
    setBusy(true); setErr(null);
    try {
      const p = PRESETS[preset];
      const extra = custom && preset === "standard" ? ov : {};
      const overrides = p.overrides || custom ? { ...(p.overrides ?? {}), ...extra } : undefined;
      const r = await api.scenario(id, seed, p.variant, overrides);
      onResult(r);
      const saved = { result: r, title: p.title, station: observations.find(o => o.id === id)?.station ?? `Pass ${id}` };
      setActive(saved);
      setRuns(previous => [saved, ...previous.filter(x => x.result.run_id !== r.run_id)].slice(0, 8));
    } catch (e) {
      setErr(String(e));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };

  const [autoDone, setAutoDone] = useState(false);
  useEffect(() => {
    if (!autoRun || autoDone || id === null) return;
    setAutoDone(true);
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun, autoDone, id]);


  return (
    <div style={{ display: "grid", gap: "2rem" }}>
      <details className="run-config" open={configOpen} onToggle={e => setConfigOpen(e.currentTarget.open)}>
        <summary><span className="heading-22">Configure run</span><span className="label">Recording · attack · parameters</span></summary>
      <div className="card" style={{ display: "grid", gap: "1.75rem" }}>
        <div>
          <Label>1 · Choose an attack</Label>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: ".75rem", marginTop: ".75rem" }}>
            {(Object.keys(PRESETS) as PresetKey[]).map(k => (
              <button key={k} type="button" onClick={() => setPreset(k)} aria-pressed={preset === k}
                style={{ textAlign: "left", padding: "1rem", cursor: "pointer", color: "#fff", background: preset === k ? "#2e2e32" : "transparent",
                  border: preset === k ? "2px solid var(--nasa-red)" : "1px solid var(--carbon-70)" }}>
                <div className="heading-16">{PRESETS[k].title}</div>
                <div className="p-sm" style={{ color: "var(--carbon-30)", marginTop: ".35rem" }}>{PRESETS[k].text}</div>
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: "grid", gap: "1.25rem", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", alignItems: "end" }}>
          <div className="field">
            <Label>2 · Choose a real recording</Label>
            <select aria-label="Recording" value={id ?? ""} onChange={e => setObsId(Number(e.target.value))}>
              {observations.map(o => (
                <option key={o.id} value={o.id}>{o.station.slice(0, 22)} · {o.start.slice(0, 10)} · {o.frames} frames</option>
              ))}
            </select>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "1.5rem", flexWrap: "wrap" }}>
            <ButtonPrimary onClick={run} disabled={busy || id === null}>{busy ? "Attacking, decoding, judging…" : "3 · Run"}</ButtonPrimary>
            {busy && <span className="spinner" />}
            {!busy && (
              <button type="button" className="mono p-sm" onClick={() => setSeed(Math.floor(Math.random() * 100000))}
                style={{ background: "none", border: 0, color: "var(--carbon-30)", cursor: "pointer", textDecoration: "underline" }}>
                new random draw
              </button>
            )}
          </div>
        </div>
        {preset === "standard" && (
          <details open={custom} onToggle={e => setCustom((e.target as HTMLDetailsElement).open)}>
            <summary className="label" style={{ cursor: "pointer", color: "var(--carbon-30)" }}>Advanced: set the hidden parameters yourself</summary>
            <div style={{ display: "grid", gap: "1.25rem", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", marginTop: "1rem" }}>
              <div className="field">
                <Label>Replay length: {ov.n_replay} frames</Label>
                <input type="range" min={5} max={20} value={ov.n_replay} onChange={e => setOv({ ...ov, n_replay: Number(e.target.value) })} />
              </div>
              <div className="field">
                <Label>Sequence anomaly</Label>
                <select value={ov.seq_variant} onChange={e => setOv({ ...ov, seq_variant: e.target.value as Overrides["seq_variant"] })}>
                  <option value="duplicate">Duplicate frame</option>
                  <option value="swap">Swap two frames</option>
                </select>
              </div>
              <div className="field">
                <Label>Jammer</Label>
                <select value={ov.jam_kind} onChange={e => setOv({ ...ov, jam_kind: e.target.value as Overrides["jam_kind"] })}>
                  <option value="cw">Tone</option><option value="nbnoise">Narrowband noise</option>
                  <option value="chirp">Swept tone</option><option value="pulsed">Pulsed tone</option>
                </select>
              </div>
              <div className="field">
                <Label>Jammer strength: {ov.js_db} dB vs. signal</Label>
                <input type="range" min={-35} max={10} value={ov.js_db} onChange={e => setOv({ ...ov, js_db: Number(e.target.value) })} />
              </div>
              <div className="field">
                <Label>Jammer frequency: {ov.jam_freq_hz} Hz</Label>
                <input type="range" min={2000} max={18000} step={50} value={ov.jam_freq_hz} onChange={e => setOv({ ...ov, jam_freq_hz: Number(e.target.value) })} />
              </div>
            </div>
          </details>
        )}
      </div>
      </details>
      {busy && <p className="mono muted" role="status">Processing recording through the decoder and detectors…</p>}
      {err && <div role="alert" className="card" style={{ borderColor: "var(--nasa-red)" }}><span className="mono red">{err}</span></div>}

      {active && <RunWorkspace key={active.result.run_id} active={active} runs={runs} observations={observations}
        onChoose={saved => { setActive(saved); onResult(saved.result); }} />}

    </div>
  );
}

export function Panel({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section style={{ display: "grid", gap: ".9rem" }}>
      <div>
        <h3 className="heading-22">{title}</h3>
        {sub && <p className="label muted" style={{ margin: ".5rem 0 0" }}>{sub}</p>}
      </div>
      {children}
    </section>
  );
}
