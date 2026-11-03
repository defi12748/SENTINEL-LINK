"use client";

import { useMemo } from "react";
import type { ClockLine, Frame, InterferenceView, Spectrogram, Tracks, TwinMatch, TwinTrace } from "@/lib/api";
import { decisionColor } from "./ui";

const W = 1000;
const PAD = { l: 64, r: 16, t: 14, b: 34 };

function scale(d0: number, d1: number, r0: number, r1: number) {
  const k = (r1 - r0) / (d1 - d0 || 1);
  return (v: number) => r0 + (v - d0) * k;
}

function ticks(lo: number, hi: number, n = 5) {
  const step = Math.pow(10, Math.floor(Math.log10((hi - lo) / n || 1)));
  const m = [1, 2, 5, 10].find(s => (hi - lo) / (s * step) <= n) ?? 10;
  const s = m * step;
  const out: number[] = [];
  for (let v = Math.ceil(lo / s) * s; v <= hi + 1e-9; v += s) out.push(+v.toFixed(6));
  return out;
}

export interface Band { start: number; end: number; color: string; label: string }

function Axes({ x, y, xt, yt, h, xLabel, yLabel, fmtY = (v: number) => String(v) }: {
  x: (v: number) => number; y: (v: number) => number; xt: number[]; yt: number[]; h: number;
  xLabel: string; yLabel: string; fmtY?: (v: number) => string;
}) {
  return (
    <g fontFamily="var(--font-label)" fontSize="11" fill="var(--carbon-40)">
      {yt.map(v => (
        <g key={`y${v}`}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="var(--carbon-80)" strokeWidth="1" />
          <text x={PAD.l - 8} y={y(v) + 4} textAnchor="end">{fmtY(v)}</text>
        </g>
      ))}
      {xt.map(v => (
        <text key={`x${v}`} x={x(v)} y={h - 12} textAnchor="middle">{v}</text>
      ))}
      <text x={W - PAD.r} y={h - 0} textAnchor="end" fontSize="10" letterSpacing="2">{xLabel}</text>
      <text x={8} y={PAD.t + 4} fontSize="10" letterSpacing="2">{yLabel}</text>
    </g>
  );
}

function Bands({ bands, x, h }: { bands: Band[]; x: (v: number) => number; h: number }) {
  return (
    <g>
      {bands.map((b, i) => (
        <g key={i}>
          <rect x={x(b.start)} y={PAD.t} width={Math.max(2, x(b.end) - x(b.start))} height={h - PAD.t - PAD.b}
            fill={b.color} opacity="0.16" />
          <text x={x(b.start) + 4} y={PAD.t + 12} fontFamily="var(--font-label)" fontSize="10" letterSpacing="1.5"
            fill={b.color}>{b.label}</text>
        </g>
      ))}
    </g>
  );
}

/** On-board frame counter vs reception time, against the archive clock model. */
export function ClockChart({ frames, clock, bands = [], onSelect, selected }: {
  frames: Frame[]; clock: ClockLine; bands?: Band[]; onSelect?: (i: number) => void; selected?: number | null;
}) {
  const H = 300;
  const pts = frames.filter(f => f.position !== null);
  const p0 = clock.position[0];
  const dur = clock.t_rec[1];
  const rel = (p: number) => p - p0;
  const ys = pts.map(f => rel(f.position as number));
  const yLo = Math.min(0, ...ys) - 2;
  const yHi = Math.max(rel(clock.position[1]), ...ys) + 2;
  const x = scale(0, dur, PAD.l, W - PAD.r);
  const y = scale(yLo, yHi, H - PAD.b, PAD.t);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
      aria-label="Frame counter versus reception time with the clock model line">
      <Bands bands={bands} x={x} h={H} />
      <Axes x={x} y={y} xt={ticks(0, dur, 8)} yt={ticks(yLo, yHi, 5)} h={H} xLabel="SECONDS INTO RECORDING"
        yLabel="FRAME COUNTER (REL.)" />
      <line x1={x(0)} y1={y(0)} x2={x(dur)} y2={y(rel(clock.position[1]))} stroke="#fff" strokeWidth="1.5"
        strokeDasharray="6 5" opacity="0.8" />
      {pts.map(f => {
        const cx = x(f.t_rec), cy = y(rel(f.position as number));
        const r = selected === f.index ? 7 : 5;
        const common = {
          fill: decisionColor[f.decision], stroke: selected === f.index ? "#fff" : "#000", strokeWidth: 1.5,
          style: { cursor: onSelect ? "pointer" : "default" }, onClick: () => onSelect?.(f.index),
        };
        const tip = <title>{`frame ${f.index} · type ${f.frame_type} · seq ${f.sequence} · p=${f.probability.toFixed(3)} · ${f.decision}`}</title>;
        // Shape doubles the colour: circle = accept, diamond = verify, square = quarantine.
        if (f.decision === "QUARANTINE") return <rect key={f.index} x={cx - r} y={cy - r} width={2 * r} height={2 * r} {...common}>{tip}</rect>;
        if (f.decision === "VERIFY") return <path key={f.index} d={`M${cx},${cy - r - 1}L${cx + r + 1},${cy}L${cx},${cy + r + 1}L${cx - r - 1},${cy}Z`} {...common}>{tip}</path>;
        return <circle key={f.index} cx={cx} cy={cy} r={r - 0.5} {...common}>{tip}</circle>;
      })}
    </svg>
  );
}

export function SpectrogramView({ spec, interference, bands = [], fOffset }: {
  spec: Spectrogram; interference?: InterferenceView; bands?: Band[]; fOffset: number;
}) {
  const H = 260, PH = 70;
  const x = scale(0, spec.duration_s, PAD.l, W - PAD.r);
  const fy = scale(spec.f_min, spec.f_max, H - PAD.b, PAD.t);
  const py = scale(0, 1, H + PH - 12, H + 6);
  const probPath = useMemo(() => {
    if (!interference || !interference.prob.length) return "";
    return interference.prob.map((p, i) => `${i ? "L" : "M"}${x(interference.centres_s[i]).toFixed(1)},${py(p).toFixed(1)}`).join("");
  }, [interference, x, py]);
  return (
    <svg viewBox={`0 0 ${W} ${H + PH}`} width="100%" role="img" aria-label="Spectrogram around the downlink with interference probability">
      <image href={`data:image/png;base64,${spec.png}`} x={PAD.l} y={PAD.t} width={W - PAD.l - PAD.r}
        height={H - PAD.t - PAD.b} preserveAspectRatio="none" />
      <Bands bands={bands} x={x} h={H} />
      <Axes x={x} y={fy} xt={ticks(0, spec.duration_s, 8)} yt={ticks(spec.f_min, spec.f_max, 4)} h={H}
        xLabel="SECONDS" yLabel="AUDIO Hz" fmtY={v => `${(v / 1000).toFixed(1)}k`} />
      <line x1={PAD.l} x2={W - PAD.r} y1={fy(fOffset)} y2={fy(fOffset)} stroke="#fff" strokeDasharray="2 6" opacity="0.5" />
      {interference && (
        <g>
          <rect x={PAD.l} y={H + 6} width={W - PAD.l - PAD.r} height={PH - 18} fill="var(--carbon-90)" />
          <line x1={PAD.l} x2={W - PAD.r} y1={py(interference.threshold)} y2={py(interference.threshold)}
            stroke="var(--nasa-red)" strokeDasharray="4 4" />
          <path d={probPath} stroke="#fff" strokeWidth="1.6" fill="none" />
          {interference.alarms.map((a, i) => (
            <g key={i}>
              <rect x={x(a.start_s)} y={H + 6} width={Math.max(2, x(a.end_s) - x(a.start_s))} height={PH - 18}
                fill="var(--nasa-red)" opacity="0.25" />
              <line x1={x(a.start_s)} x2={x(a.end_s)} y1={fy(a.freq_hz)} y2={fy(a.freq_hz)} stroke="var(--nasa-red)" strokeWidth="2.5" />
            </g>
          ))}
          <text x={PAD.l - 8} y={H + 22} textAnchor="end" fontFamily="var(--font-label)" fontSize="10" fill="var(--carbon-40)">P(jam)</text>
        </g>
      )}
    </svg>
  );
}

export function DopplerChart({ tracks, frames, bands = [] }: { tracks: Tracks; frames: Frame[]; bands?: Band[] }) {
  const H = 220;
  const dur = tracks.t[tracks.t.length - 1] ?? 1;
  const lv = tracks.level_db;
  const lvThresh = [...lv].sort((a, b) => a - b)[Math.floor(lv.length * 0.2)] ?? -999;
  const cs = tracks.carrier_hz.filter((_, i) => lv[i] > lvThresh);
  const sorted = [...cs].sort((a, b) => a - b);
  const lo = sorted[Math.floor(sorted.length * 0.02)] ?? 0;
  const hi = sorted[Math.floor(sorted.length * 0.98)] ?? 1;
  const pad = (hi - lo) * 0.25 + 5;
  const x = scale(0, dur, PAD.l, W - PAD.r);
  const y = scale(lo - pad, hi + pad, H - PAD.b, PAD.t);
  const path = tracks.t.map((t, i) => (lv[i] > lvThresh ? `${i && lv[i - 1] > lvThresh ? "L" : "M"}${x(t).toFixed(1)},${y(tracks.carrier_hz[i]).toFixed(1)}` : "")).join("");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Recovered carrier frequency (residual Doppler) over the pass">
      <Bands bands={bands} x={x} h={H} />
      <Axes x={x} y={y} xt={ticks(0, dur, 8)} yt={ticks(lo - pad, hi + pad, 4)} h={H} xLabel="SECONDS"
        yLabel="CARRIER Hz" fmtY={v => v.toFixed(0)} />
      <path d={path} stroke="var(--nasa-blue-light)" strokeWidth="1.4" fill="none" />
      {frames.map(f => {
        const s = (f.evidence.splice_carrier_step ?? 0) + (f.evidence.carrier_offset ?? 0);
        return s > 6 ? (
          <line key={f.index} x1={x(f.t_rec - 0.3)} x2={x(f.t_rec - 0.3)} y1={PAD.t} y2={H - PAD.b}
            stroke="var(--nasa-red)" strokeWidth="1.5" opacity={Math.min(1, s / 10)}>
            <title>{`frame ${f.index}: carrier step ${f.evidence.splice_carrier_step?.toFixed(1)}σ, offset ${f.evidence.carrier_offset?.toFixed(1)}σ`}</title>
          </line>
        ) : null;
      })}
    </svg>
  );
}

export function FrameRibbon({ frames, labels, selected, onSelect }: {
  frames: Frame[]; labels?: boolean[]; selected?: number | null; onSelect?: (i: number) => void;
}) {
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.max(1, frames.length)}, minmax(6px, 1fr))`, gap: 2 }}>
        {frames.map(f => (
          <button key={f.index} onClick={() => onSelect?.(f.index)} title={`frame ${f.index}: ${f.decision} (p=${f.probability.toFixed(3)})`}
            aria-label={`frame ${f.index} ${f.decision}`}
            style={{ height: 30, border: selected === f.index ? "2px solid #fff" : 0, padding: 0, cursor: "pointer",
              background: decisionColor[f.decision], opacity: 0.35 + 0.65 * Math.max(f.probability, f.decision === "ACCEPT" ? 0.6 : 0) }} />
        ))}
      </div>
      {labels && (
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.max(1, frames.length)}, minmax(6px, 1fr))`, gap: 2, marginTop: 4 }}>
          {labels.map((l, i) => <div key={i} style={{ height: 5, background: l ? "#fff" : "var(--carbon-80)" }} />)}
        </div>
      )}
    </div>
  );
}

/** Duplicate-audio head: ribbons join each copied stretch to the earlier audio it repeats;
    bars are each 2 s block's best correlation with any other part of the file. */
export function TwinChart({ trace, matches, duration, bands = [] }: {
  trace: TwinTrace; matches: TwinMatch[]; duration: number; bands?: Band[];
}) {
  const H = 330, base = 168, barTop = 200, barBot = H - PAD.b;
  const x = scale(0, duration, PAD.l, W - PAD.r);
  const y = scale(0, 1, barBot, barTop);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
      aria-label="Copied audio stretches joined to their source, and per-block correlation against the rest of the recording">
      <defs>
        <linearGradient id="twin-ribbon" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.55" />
          <stop offset="1" stopColor="#f64137" stopOpacity="0.85" />
        </linearGradient>
      </defs>
      <Bands bands={bands} x={x} h={H} />
      {matches.map((m, i) => {
        const a0 = x(m.src_start_s), a1 = x(m.src_start_s + (m.end_s - m.start_s)), b0 = x(m.start_s), b1 = x(m.end_s);
        const hOut = Math.min(base - PAD.t - 18, 30 + (b1 - a0) * 0.45);
        const hIn = Math.max(6, Math.min(hOut - 14, (b0 - a1) * 0.45));
        return (
          <g key={i}>
            <path d={`M${a0},${base} C${a0},${base - hOut} ${b1},${base - hOut} ${b1},${base} L${b0},${base} C${b0},${base - hIn} ${a1},${base - hIn} ${a1},${base} Z`}
              fill="url(#twin-ribbon)" stroke="#f64137" strokeWidth="1" />
            <text x={(a0 + b1) / 2} y={base - hOut * 0.75 - 6} textAnchor="middle" fontFamily="var(--font-label)" fontSize="12" fill="#fff">
              {b1 - a0 > 220 ? `copy of ${m.src_start_s.toFixed(0)} s · r = ${m.ncc.toFixed(3)}` : `r = ${m.ncc.toFixed(2)}`}
            </text>
          </g>
        );
      })}
      <rect x={PAD.l} y={base} width={W - PAD.l - PAD.r} height={14} fill="var(--carbon-80)" />
      {matches.map((m, i) => (
        <g key={`s${i}`}>
          <rect x={x(m.src_start_s)} y={base} width={Math.max(2, x(m.src_start_s + m.end_s - m.start_s) - x(m.src_start_s))} height={14} fill="#fff" opacity="0.8" />
          <rect x={x(m.start_s)} y={base} width={Math.max(2, x(m.end_s) - x(m.start_s))} height={14} fill="#f64137" />
        </g>
      ))}
      <Axes x={x} y={y} xt={ticks(0, duration, 8)} yt={[0, 0.5, 1]} h={H} xLabel="SECONDS INTO RECORDING" yLabel="" fmtY={v => v.toFixed(1)} />
      <text x={8} y={barTop - 12} fontFamily="var(--font-label)" fontSize="10" letterSpacing="2" fill="var(--carbon-40)">BEST r</text>
      {trace.block_t.map((t, i) => {
        const v = trace.block_ncc[i];
        return (
          <rect key={i} x={x(t) + 0.5} y={y(v)} width={Math.max(1, x(t + trace.block_s) - x(t) - 1)} height={Math.max(0, barBot - y(v))}
            fill={v >= trace.threshold ? "#f64137" : "var(--carbon-60)"}>
            <title>{`${t.toFixed(0)}–${(t + trace.block_s).toFixed(0)} s: best correlation ${v.toFixed(3)}`}</title>
          </rect>
        );
      })}
      <line x1={PAD.l} x2={W - PAD.r} y1={y(trace.threshold)} y2={y(trace.threshold)} stroke="#fff" strokeDasharray="4 4" opacity="0.7" />
      <text x={W - PAD.r} y={y(trace.threshold) - 5} textAnchor="end" fontFamily="var(--font-label)" fontSize="10" fill="#fff">{`THRESHOLD ${trace.threshold}`}</text>
    </svg>
  );
}

/** Signed capture: one cell per second of audio, each a leaf of the station's Merkle tree. */
export function MerkleStrip({ duration, tampered, perRow = 60 }: { duration: number; tampered: [number, number][]; perRow?: number }) {
  const n = Math.ceil(duration);
  const rows = Math.ceil(n / perRow);
  const edited = (s: number) => tampered.some(([a, b]) => s + 1 > a && s < b);
  return (
    <div className="merkle" role="img" aria-label={`${n} one-second leaves; ${tampered.length} edited span(s)`}>
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="merkle-row">
          <span className="mono">{`${Math.floor((r * perRow) / 60)}:${String((r * perRow) % 60).padStart(2, "0")}`}</span>
          <div style={{ gridTemplateColumns: `repeat(${perRow}, 1fr)` }}>
            {Array.from({ length: Math.min(perRow, n - r * perRow) }, (_, c) => {
              const s = r * perRow + c;
              return <i key={c} className={edited(s) ? "bad" : "ok"} style={{ animationDelay: `${s * 4}ms` }} title={`second ${s}: ${edited(s) ? "differs from the signed capture" : "matches"}`} />;
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
