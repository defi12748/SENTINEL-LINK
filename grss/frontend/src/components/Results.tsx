"use client";

import type { Benchmark } from "@/lib/api";
import { Stat, pct } from "./ui";

export function PdChart({ curve }: { curve: { js_db: string; n: number; pd: number | null }[] }) {
  const W = 640, H = 240, L = 52, B = 40, T = 12;
  const bw = (W - L - 12) / curve.length;
  const y = (v: number) => T + (1 - v) * (H - T - B);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Interference detection probability by jammer-to-signal ratio">
      {[0, 0.25, 0.5, 0.75, 1].map(v => (
        <g key={v} fontFamily="var(--font-label)" fontSize="11" fill="var(--carbon-40)">
          <line x1={L} x2={W - 12} y1={y(v)} y2={y(v)} stroke="var(--carbon-80)" />
          <text x={L - 8} y={y(v) + 4} textAnchor="end">{v * 100}%</text>
        </g>
      ))}
      {curve.map((c, i) => {
        const v = c.pd ?? 0;
        const x = L + i * bw + 3;
        const h = H - B - y(v);
        return (
          <g key={c.js_db}>
            <path d={`M${x},${H - B}V${y(v) + Math.min(4, h)}q0,-4 4,-4h${bw - 14}q4,0 4,4V${H - B}Z`} fill="var(--nasa-blue-light)">
              <title>{`J/S ${c.js_db} dB: Pd ${c.pd === null ? "n/a" : (v * 100).toFixed(1) + "%"} (n=${c.n})`}</title>
            </path>
            <text x={x + (bw - 6) / 2} y={H - B + 16} textAnchor="middle" fontFamily="var(--font-label)" fontSize="10" fill="var(--carbon-40)">{c.js_db}</text>
            {c.n > 0 && <text x={x + (bw - 6) / 2} y={y(v) - 6} textAnchor="middle" fontFamily="var(--font-label)" fontSize="11" fill="currentColor">{(v * 100).toFixed(0)}%</text>}
          </g>
        );
      })}
      <text x={W - 12} y={H - 4} textAnchor="end" fontFamily="var(--font-label)" fontSize="10" letterSpacing="2" fill="var(--carbon-40)">JAMMER-TO-SIGNAL (dB)</text>
    </svg>
  );
}

export function Results({ bench }: { bench: Benchmark | null }) {
  if (!bench) {
    return <p className="p-lg muted">No benchmark yet. Run <span className="mono">py -m sentinel.bench.run</span> on the backend.</p>;
  }
  const fd = bench.frame_detection;
  const intf = bench.interference;
  const ev = bench.evasion ?? {};
  return (
    <div style={{ display: "grid", gap: "3.5rem" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "2rem" }}>
        <Stat label="Attacked frames detected" value={pct(fd.attacked_passes.detection_rate)}
          note={`${fd.attacked_passes.tp} of ${fd.attacked_passes.attacked} replayed / anomalous frames, held-out passes`} />
        <Stat label="False-alarm rate" value={pct(fd.combined.false_alarm_rate, 2)}
          note={`${fd.attacked_passes.fp + fd.clean_passes.false_alarms} of ${fd.attacked_passes.fp + fd.attacked_passes.tn + fd.clean_passes.frames} authentic frames`} />
        <Stat label="Jammers detected" value={pct(intf.detection_rate)}
          note={`${intf.recordings_attacked} hidden-J/S jammers · ${intf.clean_recordings_with_alarm}/${intf.clean_recordings} clean recordings alarmed`} />
        <Stat label="Decision latency" value={`${fd.latency_ms_per_frame.mean.toFixed(2)} ms`}
          note={`per frame, after decode · peak RSS ${bench.resources.peak_rss_mb} MB`} />
      </div>

      <div style={{ display: "grid", gap: "3rem", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 460px), 1fr))" }}>
        <div style={{ display: "grid", gap: "1rem", alignContent: "start" }}>
          <h3 className="heading-22">Jammer Detection vs. J/S</h3>
          <PdChart curve={intf.pd_vs_js} />
        </div>
        <div style={{ display: "grid", gap: "1rem", alignContent: "start" }}>
          <h3 className="heading-22">Attacks Caught</h3>
          <div className="scroll-x">
            <table className="data">
              <thead><tr><th>Attack</th><th>Detected</th><th>Rate</th></tr></thead>
              <tbody>
                {Object.entries(fd.events as Record<string, { n: number; detected: number }>).filter(([, v]) => v.n > 0).map(([k, v]) => (
                  <tr key={k}><td>{k.replace("/", " · ").replaceAll("_", " ")}</td><td>{v.detected}/{v.n}</td><td>{pct(v.detected / v.n)}</td></tr>
                ))}
                {Object.entries(ev as Record<string, { n: number; detected: number; rate: number }>).map(([k, v]) => (
                  <tr key={k}><td>evasion · {k.replaceAll("_", " ")}</td><td>{v.detected}/{v.n}</td><td>{pct(v.rate)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {bench.twin && <TwinResults t={bench.twin} />}
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function TwinResults({ t }: { t: any }) {
  const names: Record<string, string> = {
    vorbis_reencode: "Re-encoded to Vorbis", "inband_noise_-6db": "In-band noise, −6 dB", inband_noise_0db: "In-band noise, 0 dB",
    "stretch_1e-5": "Time-stretched 10⁻⁵", "stretch_1e-4": "Time-stretched 10⁻⁴",
  };
  return (
    <div style={{ display: "grid", gap: "2rem" }}>
      <h3 className="heading-22 margin-0">Duplicate-Audio Head (No Decoder)</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "2rem" }}>
        <Stat label="In-pass replays found" value={`${t.replay.detected}/${t.replay.n}`} note="copied runs of frame slots, held-out recordings" />
        <Stat label="Duplicated slots found" value={`${t.sequence_duplicate.detected}/${t.sequence_duplicate.n}`} note="swaps copy nothing and are left to the clock head" />
        <Stat label="Clean recordings matched" value={`${t.clean.with_match}/${t.clean.recordings}`} note={`best genuine correlation ${t.clean.max_ncc} vs threshold ${t.threshold}`} />
        <Stat label="Time per recording" value={`${(t.latency_ms_per_recording_mean / 1000).toFixed(1)} s`} note={`${t.block_s} s blocks at ${t.baseband_hz} Hz baseband`} />
      </div>
      <div className="scroll-x">
        <table className="data">
          <thead><tr><th>Evasion attempt</th><th>Copies still found</th><th>Rate</th></tr></thead>
          <tbody>
            {Object.entries(t.evasion as Record<string, { n: number; detected: number; rate: number }>).map(([k, v]) => (
              <tr key={k}><td>{names[k] ?? k}</td><td>{v.detected}/{v.n}</td><td>{pct(v.rate)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
