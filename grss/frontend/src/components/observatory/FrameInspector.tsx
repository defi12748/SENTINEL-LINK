"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { Frame, ScenarioResult } from "@/lib/api";
import { reasonCodes } from "./reasons";

const tone = (d: string) => (d === "QUARANTINE" ? "bad" : d === "VERIFY" ? "alert" : "ok");

export function FrameInspector({ result, selected, onSelect }: { result: ScenarioResult; selected: number | null; onSelect: (i: number) => void }) {
  const [scope, setScope] = useState<"flagged" | "all">("flagged");
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    const frame = result.frames.find(f => f.index === selected);
    if (frame && frame.decision === "ACCEPT" && !result.labels[frame.index]) setScope("all");
  }, [result, selected]);
  const list = useMemo(() => {
    const flagged = result.frames.filter(f => f.decision !== "ACCEPT" || result.labels[f.index]);
    return scope === "flagged" && flagged.length ? flagged : result.frames;
  }, [result, scope]);
  const cur = list.find(f => f.index === selected) ?? list[0];
  const pos = list.findIndex(f => f.index === cur?.index);
  const move = useCallback((d: number) => { const n = list[pos + d]; if (n) onSelect(n.index); }, [list, pos, onSelect]);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      if (pos >= list.length - 1) { setPlaying(false); return; }
      move(1);
    }, 1600);
    return () => window.clearInterval(id);
  }, [playing, pos, list.length, move]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (["INPUT", "SELECT", "TEXTAREA", "BUTTON", "SUMMARY"].includes((e.target as HTMLElement).tagName)) return;
      if (e.key === "ArrowRight") { e.preventDefault(); move(1); }
      if (e.key === "ArrowLeft") { e.preventDefault(); move(-1); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [move]);

  if (!cur) return null;
  const reasons = reasonCodes(cur);
  const oa = result.onair.frames?.find(x => Math.abs(x.t_rec - cur.t_rec) < 0.01);
  const ref = result.ledger_refs?.[String(cur.index)];
  const truth = result.label_kind[cur.index] || (result.labels[cur.index] ? "attacked" : "");
  const original = cur.position !== null
    ? result.frames.find((f: Frame) => f.position === cur.position && f.t_rec < cur.t_rec - 1)
    : undefined;
  const happened = cur.decision === "QUARANTINE" ? "Withheld from the analyst." : cur.decision === "VERIFY" ? "Held for verification (e.g. a second station's copy of the pass)." : "Delivered to the analyst.";

  return (
    <section className="obs-card">
      <div className="obs-head">
        <h3 className="heading-22 margin-0">Frame Inspector</h3>
        <div className="display-flex flex-align-center" style={{ gap: ".5rem" }}>
          <div className="seg">
            <button aria-pressed={scope === "flagged"} className={scope === "flagged" ? "on" : ""} onClick={() => { const first = result.frames.find(f => f.decision !== "ACCEPT" || result.labels[f.index]); if (first) onSelect(first.index); setScope("flagged"); setPlaying(false); }}>Flagged & attacked</button>
            <button aria-pressed={scope === "all"} className={scope === "all" ? "on" : ""} onClick={() => { setScope("all"); setPlaying(false); }}>All {result.frames.length}</button>
          </div>
          <div className="steps">
            <button aria-label="Previous frame" disabled={pos <= 0} onClick={() => move(-1)}>‹</button>
            <button aria-label={playing ? "Pause" : "Play"} disabled={!list.length} onClick={() => { if (!playing && pos === list.length - 1) onSelect(list[0].index); setPlaying(!playing); }}>{playing ? "❚❚" : "▶"}</button>
            <button aria-label="Next frame" disabled={pos >= list.length - 1} onClick={() => move(1)}>›</button>
          </div>
        </div>
      </div>
      <div className="insp-head">
        <div>
          <span className="label">Frame {String(cur.index).padStart(2, "0")} · {pos + 1} of {list.length}</span>
          <h2 className="heading-29 margin-0">t = {cur.t_rec.toFixed(1)} s · type {cur.frame_type ?? "—"}</h2>
        </div>
        <div className="display-flex" style={{ gap: ".5rem", alignItems: "center" }}>
          {truth && <span className="badge neutral">TRUTH: {truth.toUpperCase()}</span>}
          <span className={`badge ${tone(cur.decision)}`}>{cur.decision}</span>
        </div>
      </div>

      {original && (
        <div className="boundary">
          <div><span>FIRST RECEIVED</span><strong>t = {original.t_rec.toFixed(1)} s (frame {original.index})</strong></div><b>→</b>
          <div><span>SAME FRAME AGAIN</span><strong>t = {cur.t_rec.toFixed(1)} s, counter unchanged</strong></div><b>→</b>
          <div><span>SENTINEL</span><strong>{cur.decision === "ACCEPT" ? "Accepted" : `${cur.decision === "QUARANTINE" ? "Quarantined" : "Held"} before delivery`}</strong></div>
        </div>
      )}

      <div className="flow3">
        <div className="flow-panel">
          <div className="flow-panel-head">FRAME AS RECEIVED</div>
          <dl>
            <div><dt>Sequence</dt><dd>{cur.sequence ?? "—"}</dd></div>
            <div><dt>On-board position</dt><dd>{cur.position ?? "—"}</dd></div>
            <div><dt>Battery</dt><dd>{cur.battery_v?.toFixed(3) ?? "—"} V · {cur.battery_temp_c ?? "—"} °C</dd></div>
            <div><dt>SHA-256</dt><dd className="mono">{cur.sha256.slice(0, 24)}…</dd></div>
          </dl>
        </div>
        <div className={`flow-panel decision ${tone(cur.decision)}`}>
          <div className="flow-panel-head">SENTINEL DECISION</div>
          <div className="decision-main">{cur.decision}</div>
          <div className="chips">{reasons.length ? reasons.map(r => <span key={r.code} title={r.detail}>{r.code}</span>) : <span>NO_EVIDENCE_OF_ATTACK</span>}</div>
          <div className="dstats">
            <div><span>P(NOT AUTHENTIC)</span><strong>{cur.probability.toFixed(4)}</strong></div>
            <div><span>CONFIDENCE</span><strong>{(Math.max(cur.probability, 1 - cur.probability) * 100).toFixed(1)}%</strong></div>
          </div>
          {reasons.length > 0 && <ul className="why">{reasons.map(r => <li key={r.code}>{r.detail}</li>)}</ul>}
        </div>
        <div className="flow-panel">
          <div className="flow-panel-head">WHAT HAPPENED</div>
          <p className="p-sm" style={{ margin: "0 0 .75rem" }}>{happened}</p>
          <dl>
            {ref && <div><dt>Ledger entry</dt><dd>#{ref.entry} · <span className="mono">{ref.hash.slice(0, 16)}…</span></dd></div>}
            {oa && <div><dt>NASA OnAIR limits</dt><dd>{oa.status}{oa.faulting.length ? ` (${oa.faulting.join(", ")})` : ""}</dd></div>}
            {oa && <div><dt>OnAIR clock plugin</dt><dd>{oa.clock.status} · {oa.clock.residual_frames?.toFixed(2)} frames</dd></div>}
          </dl>
        </div>
      </div>
    </section>
  );
}
