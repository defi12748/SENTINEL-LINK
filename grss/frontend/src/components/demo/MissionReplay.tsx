"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ObservationDetail, ScenarioResult } from "@/lib/api";
import { reasonCodes } from "../observatory/reasons";
import { decisionColor } from "../ui";

const Globe = dynamic(() => import("../Globe"), { ssr: false });
const PLAY_S = 32; // the whole pass replays in about half a minute at 1×

interface Event { t: number; cls: string; text: string }

const stamp = (t: number) => `[${t.toFixed(1).padStart(5, "0")} s]`;

/** The analysed pass, replayed in compressed time: frames arrive, verdicts land,
    alarms fire. The detector's output is fixed; only the clock is animated. */
export function MissionReplay({ run, detail, station }: { run: ScenarioResult; detail: ObservationDetail | null; station: string }) {
  const dur = run.duration_s;
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [truth, setTruth] = useState(false);
  const tRef = useRef(0);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const next = Math.min(dur, tRef.current + ((now - last) / 1000) * speed * (dur / PLAY_S));
      last = now;
      tRef.current = next;
      setT(next);
      if (next >= dur) { setPlaying(false); setTruth(true); return; }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, dur]);

  const seek = (v: number) => { tRef.current = v; setT(v); };
  const restart = () => { seek(0); setTruth(false); setPlaying(true); };

  const events = useMemo<Event[]>(() => {
    const link = detail ? `, ${(detail.record.frequency_hz / 1e6).toFixed(3)} MHz ${detail.record.mode}` : "";
    const ev: Event[] = [{ t: 0, cls: "sys", text: `Signal acquired: AO-73 over ${station}${link}` }];
    run.frames.forEach(f => {
      const why = f.decision !== "ACCEPT" ? reasonCodes(f)[0]?.code ?? "" : "";
      ev.push({ t: f.t_rec, cls: f.decision === "QUARANTINE" ? "q" : f.decision === "VERIFY" ? "v" : "a",
        text: `Frame ${String(f.index).padStart(2, "0")}  p=${f.probability.toFixed(3)}  ${f.decision}${why ? `  ${why}` : ""}` });
    });
    run.interference.alarms.forEach(a => ev.push({ t: a.start_s, cls: "v",
      text: `Spectrum alarm at ${(a.freq_hz / 1000).toFixed(2)} kHz, p=${a.peak_prob.toFixed(3)}` }));
    (run.duplicates ?? []).forEach(m => ev.push({ t: m.end_s, cls: "q",
      text: `Audio twin: ${m.start_s.toFixed(0)}–${m.end_s.toFixed(0)} s is a copy of ${m.src_start_s.toFixed(0)} s, r=${m.ncc.toFixed(3)}` }));
    ev.push({ t: dur, cls: "sys", text: `Signal lost: ${run.frames.length} frames judged and logged` });
    return ev.sort((a, b) => a.t - b.t);
  }, [run, station, dur, detail]);

  const seen = run.frames.filter(f => f.t_rec <= t);
  const counts = { ACCEPT: 0, VERIFY: 0, QUARANTINE: 0 };
  seen.forEach(f => counts[f.decision]++);
  const current = seen[seen.length - 1];
  const feed = events.filter(e => e.t <= t).slice(-11);
  const geo = detail?.geometry ?? [];
  const g = geo.length ? geo[Math.min(geo.length - 1, Math.round((t / dur) * (geo.length - 1)))] : null;
  const pctOf = (s: number) => `${(Math.min(Math.max(s / dur, 0), 1) * 100).toFixed(2)}%`;
  const tr = run.truth;
  const bands = [
    ...(tr.interference ? [{ a: tr.interference.start_s, b: tr.interference.start_s + tr.interference.dur_s, c: "#ffc83d", l: `JAMMER ${tr.interference.js_db.toFixed(0)} dB` }] : []),
    ...(tr.replay ? [{ a: tr.replay.dst_start_s, b: tr.replay.dst_end_s, c: "#f64137", l: `REPLAY ×${tr.replay.n_frames}` }] : []),
    ...(tr.sequence ? [{ a: tr.sequence.dst_start_s, b: tr.sequence.dst_end_s, c: "#ea6f24", l: "ANOMALY" }] : []),
  ];
  const done = t >= dur;
  const attacked = run.score.tp + run.score.fn;

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <div className="mission">
        <div className="mission-globe">
          <div className="hud">
            <span className="label">AO-73 over {station}</span>
            <strong>T+{t.toFixed(0).padStart(3, "0")} s</strong>
            {g && <span className="p-sm" style={{ color: "#fff" }}>Elevation {g.el.toFixed(0)}°, range {g.range_km.toFixed(0)} km</span>}
          </div>
          {detail && <Globe orbit={detail.orbit} pass={detail.geometry} station={{ lat: detail.record.station_lat, lon: detail.record.station_lng }}
            playhead={t / dur} alert={!!current && current.decision !== "ACCEPT"} unix={Date.parse(detail.record.start) / 1000} shift={false} />}
        </div>
        <div className="mission-side">
          <div className="counters">
            {([["DECODED", seen.length, ""], ["ACCEPTED", counts.ACCEPT, "info"], ["VERIFY", counts.VERIFY, "alert"], ["QUARANTINED", counts.QUARANTINE, "bad"]] as const)
              .map(([k, v, c]) => <div key={k} className={c}><span className="label">{k}</span><strong>{v}</strong></div>)}
          </div>
          <div className="feed" aria-live="polite">
            {feed.map((e, i) => <div key={`${e.t}-${i}-${e.text.slice(0, 8)}`} className={e.cls}>{stamp(e.t)} {e.text}</div>)}
          </div>
        </div>
      </div>

      <div className="timeline" role="slider" aria-label="Pass time" aria-valuemin={0} aria-valuemax={Math.round(dur)} aria-valuenow={Math.round(t)} tabIndex={0}
        onClick={e => { const r = e.currentTarget.getBoundingClientRect(); seek(((e.clientX - r.left) / r.width) * dur); }}
        onKeyDown={e => { if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.stopPropagation(); e.preventDefault(); seek(Math.min(dur, Math.max(0, t + (e.key === "ArrowRight" ? 10 : -10)))); } }}>
        {bands.map(b => (
          <div key={b.l} className="band" style={{ left: pctOf(b.a), width: `calc(${pctOf(b.b)} - ${pctOf(b.a)})`, background: `${b.c}33`, borderTop: `2px solid ${b.c}`, opacity: truth ? 1 : 0 }}>
            <span style={{ color: b.c }}>{b.l}</span>
          </div>
        ))}
        {seen.map(f => <div key={f.index} className="tick" style={{ left: pctOf(f.t_rec), background: decisionColor[f.decision] }} />)}
        <div className="head" style={{ left: pctOf(t) }} />
      </div>

      <div className="controls">
        <button type="button" className="usa-button bg-nasa-red margin-0" onClick={() => (done ? restart() : setPlaying(!playing))}>{done ? "Replay the Pass" : playing ? "Pause" : "Play"}</button>
        <button type="button" className="usa-button btn-ghost margin-0" onClick={restart}>Restart</button>
        {[1, 2, 4].map(s => <button key={s} type="button" className={`usa-button margin-0 ${speed === s ? "bg-white text-black" : "btn-ghost"}`} style={speed === s ? { background: "#fff", color: "#000" } : undefined} onClick={() => setSpeed(s)}>{s}×</button>)}
        <button type="button" className="usa-button btn-ghost margin-0" onClick={() => setTruth(!truth)}>{truth ? "Hide the Truth" : "Reveal the Hidden Truth"}</button>
        <span className="p-sm" style={{ color: "#fff" }}>Verdicts from the real pipeline, run on the attacked audio.</span>
      </div>

      {done && (
        <div className="verdict">
          <div><span className="label">Attacked frames caught</span><strong style={{ color: run.score.fn ? "#ffc83d" : "var(--ok)" }}>{run.score.tp} / {attacked}</strong></div>
          <div><span className="label">False alarms</span><strong style={{ color: run.score.fp ? "#ffc83d" : "var(--ok)" }}>{run.score.fp}</strong></div>
          <div><span className="label">Copied audio</span><strong>{run.duplicate_trace?.expected ? (run.duplicate_trace.detected_truth ? `${run.duplicates?.length ?? 0} found` : "Missed") : "None"}</strong></div>
          <div><span className="label">Jammer at its frequency</span><strong style={{ color: tr.interference && !run.interference.detected_truth ? "#ffc83d" : undefined }}>
            {tr.interference ? (run.interference.detected_truth ? "Found" : `Missed (${tr.interference.js_db.toFixed(0)} dB)`) : "None"}</strong></div>
        </div>
      )}
    </div>
  );
}
