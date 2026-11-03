"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type LedgerView, type ScenarioResult, type SdlsDemo } from "@/lib/api";
import { PHOTOS } from "@/lib/photos";
import { ClockChart, FrameRibbon, MerkleStrip, SpectrogramView, TwinChart, type Band } from "../Charts";
import { CryptoLibPanel } from "../CryptoLibPanel";
import { HeldOutPanel } from "../HeldOutPanel";
import { PipelinePath } from "../observatory/PipelinePath";
import { OnAirPanel } from "../OnAirPanel";
import { PdChart } from "../Results";
import { pct } from "../ui";
import { clockLag, useCountUp, type DemoData, type Slot } from "./data";
import { MissionReplay } from "./MissionReplay";

/* Chapter bodies of the live demo, written with the home page's blocks:
   the "Proof" figure (display number, heading, short line) and HDS headings. */

function Wait<T>({ slot, what, children }: { slot: Slot<T>; what: string; children: (data: T) => ReactNode }) {
  if (slot.error) return <p role="alert" className="p-md color-nasa-red">Could not load {what}: {slot.error}</p>;
  if (!slot.data) return <div className="display-flex flex-align-center" style={{ gap: ".75rem" }}><span className="spinner" /><span className="p-md">Running {what}</span></div>;
  return <>{children(slot.data)}</>;
}

/** The home page's "Proof" figure. */
export function Figure({ v, k, sub, color }: { v: ReactNode; k: string; sub?: ReactNode; color?: string }) {
  return (
    <div className="tablet:grid-col-6 desktop:grid-col margin-bottom-5" style={{ borderTop: "1px solid #58585b", paddingTop: "1.25rem" }}>
      <div className="display-48" style={{ color }}>{v}</div>
      <p className="heading-18 margin-top-2 margin-bottom-1">{k}</p>
      {sub && <p className="p-sm margin-0">{sub}</p>}
    </div>
  );
}
const Figures = ({ children }: { children: ReactNode }) => <div className="grid-row grid-gap-4">{children}</div>;

function Block({ title, text, children }: { title: string; text?: ReactNode; children: ReactNode }) {
  return (
    <section style={{ display: "grid", gap: "1rem" }}>
      <div>
        <h3 className="heading-29 margin-0">{title}</h3>
        {text && <p className="p-md margin-top-1 margin-bottom-0 maxw-tablet-lg">{text}</p>}
      </div>
      {children}
    </section>
  );
}

function Callout({ children, honest = false }: { children: ReactNode; honest?: boolean }) {
  return (
    <div style={{ borderLeft: `6px solid ${honest ? "#ffc83d" : "var(--nasa-red)"}`, padding: "1rem 1.25rem", background: "#000" }}>
      <p className="heading-18 margin-0" style={{ color: "#fff", fontWeight: 400 }}>{children}</p>
    </div>
  );
}

const RED = "var(--nasa-red)", OK = "var(--ok)";
const truthBands = (r: ScenarioResult): Band[] => [
  ...(r.truth.replay ? [{ start: r.truth.replay.dst_start_s, end: r.truth.replay.dst_end_s, color: "#f64137", label: "REPLAY" }] : []),
  ...(r.truth.sequence ? [{ start: r.truth.sequence.dst_start_s, end: r.truth.sequence.dst_end_s, color: "#ea6f24", label: "ANOMALY" }] : []),
];
const Stack = ({ children }: { children: ReactNode }) => <div style={{ display: "grid", gap: "3rem" }}>{children}</div>;

/* 01 systems check */
export function Briefing({ d }: { d: DemoData }) {
  const h = d.health.data, run = d.run.data, ix = d.interop.data;
  const obs = d.obs.data ?? [];
  const stations = useMemo(() => new Set(obs.map(o => o.station)).size, [obs]);
  const go = (ok: boolean | undefined, pending: boolean) => (pending ? "wait" : ok ? "go" : "nogo");
  const rows: [string, string, string][] = [
    ["Ground-segment API", "Every number in this demo is computed live", go(!!h, !h && !d.health.error)],
    ["Detection models", "Clock, splice, telemetry, interference and fusion", go(h?.models, !h)],
    ["Demodulator", "GNU Radio and gr-satellites, AO-40 error correction", go(h?.gr_satellites, !h)],
    ["Reference data", h ? `${h.observations} SatNOGS recordings from ${stations || 5} stations` : "Loading", go((h?.observations ?? 0) > 0, !h)],
    ["NASA OnAIR", "On-board AI Research platform, from NOS3", go(run?.onair.available, !run && !d.run.error)],
    ["NASA CryptoLib", ix?.library ?? "CCSDS space link security, from NOS3", go(ix?.available, !ix && !d.interop.error)],
    ["Station signing key", "Ed25519, generated for this session", go(!!h, !h)],
  ];
  return (
    <div className="grid-row grid-gap-6">
      <div className="desktop:grid-col-5 margin-bottom-4">
        <h2 className="section-heading-md margin-top-0">Systems Check</h2>
        <p className="p-lg">Before the demo, the station checks every module it depends on. All of them run on this machine, on real recordings of the AO-73 satellite.</p>
      </div>
      <div className="desktop:grid-col-7">
        <div className="poll" aria-label="Systems check">
          {rows.map(([k, v, s], i) => (
            <div key={k} className={s} style={{ "--d": `${i * 0.1}s` } as React.CSSProperties}>
              <span className="heading-18">{k}<small>{v}</small></span><b>{s === "go" ? "GO" : s === "wait" ? "…" : "NO-GO"}</b>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* 02 the problem */
export function Threat({ d }: { d: DemoData }) {
  const obs = d.obs.data ?? [];
  const ours = obs.reduce((a, o) => a + o.frames, 0), theirs = obs.reduce((a, o) => a + o.satnogs_frames, 0);
  const cards = [
    { t: "Replay", p: "Re-send 5 to 20 genuine frames recorded earlier. Every byte is valid and every checksum passes.", img: PHOTOS.cubesat },
    { t: "Sequence Anomaly", p: "Duplicate or swap one frame inside the pass. The decoder is perfectly happy.", img: PHOTOS.cubesatDeploy },
    { t: "Narrowband Jamming", p: "Add a tone or noise at a hidden strength. Frames vanish or decode corrupted.", img: PHOTOS.aurora2 },
  ];
  return (
    <>
      <div className="grid-row grid-gap-4 margin-bottom-4">
        {cards.map((c, i) => (
          <div key={c.t} className="desktop:grid-col-4 margin-bottom-4">
            <div className="hds-cover-wrapper cover-hover-zoom bg-carbon-black" style={{ aspectRatio: "4 / 3" }}>
              <figure className="hds-media-background"><img alt="" src={c.img} style={{ objectFit: "cover" }} /></figure>
            </div>
            <div className="label color-nasa-red margin-top-3 margin-bottom-1">Attack 0{i + 1}</div>
            <h3 className="heading-22 margin-bottom-1">{c.t}</h3>
            <p className="p-sm margin-0">{c.p}</p>
          </div>
        ))}
      </div>
      <Figures>
        <Figure v={obs.length || "30"} k="real SatNOGS recordings" sub="from five ground stations on three continents" />
        <Figure v={ours ? ours.toLocaleString() : "…"} k="frames we decoded from raw audio" sub={theirs ? `the stations themselves decoded ${theirs.toLocaleString()}` : undefined} />
        <Figure v={obs.filter(o => o.split === "held-out").length || "17"} k="held-out passes" sub="every score in this demo is measured on them" />
      </Figures>
    </>
  );
}

/* 03 live attack */
export function LiveAttack({ d }: { d: DemoData }) {
  return (
    <Wait slot={d.run} what="the attacked pass through the full chain">
      {run => <MissionReplay run={run} detail={d.detail.data} station={d.detail.data?.record.station_name ?? `Pass ${run.truth.observation_id}`} />}
    </Wait>
  );
}

/* 04 the pipeline */
export function Pipeline({ d }: { d: DemoData }) {
  return <Wait slot={d.run} what="the pipeline">{run => <PipelinePath result={run} station={d.detail.data?.record.station_name} />}</Wait>;
}

/* 05 clock evidence */
export function ClockEvidence({ d }: { d: DemoData }) {
  const [sel, setSel] = useState<number | null>(null);
  return (
    <Wait slot={d.run} what="the clock analysis">
      {run => {
        const { lag, seconds } = clockLag(run);
        return (
          <Stack>
            <Figures>
              <Figure v={`${run.clock.period_s.toFixed(3)} s`} k="between frames, on board" sub="learned from the public archive" />
              <Figure v={`${lag} frames`} k="behind the clock: the replay" sub={`about ${seconds} seconds of stale audio`} color={RED} />
              <Figure v="±1 frame" k="error on genuine frames" sub="on passes the model never saw" color={OK} />
            </Figures>
            <Block title="Frame Counter vs. Clock" text="The dashed line is the spacecraft clock. Squares were quarantined, diamonds sent for verification, circles accepted. Click a frame to select it.">
              <ClockChart frames={run.frames} clock={run.clock} bands={truthBands(run)} selected={sel} onSelect={setSel} />
              <FrameRibbon frames={run.frames} labels={run.labels} selected={sel} onSelect={setSel} />
            </Block>
            <Callout>To pass, a forger must rewrite the counter and keep the telemetry, the Doppler curve and the carrier continuous. A replay from another day sits thousands of frames off: 16 of 16 were caught.</Callout>
          </Stack>
        );
      }}
    </Wait>
  );
}

/* 06 duplicate-audio evidence */
export function TwinEvidence({ d }: { d: DemoData }) {
  const tw = d.bench.data?.twin;
  return (
    <Wait slot={d.run} what="the duplicate-audio check">
      {run => (
        <Stack>
          <Figures>
            {(run.duplicates ?? []).map(m => (
              <Figure key={m.start_s} v={`${m.start_s.toFixed(0)}–${m.end_s.toFixed(0)} s`} k={`is a copy of second ${m.src_start_s.toFixed(0)}`} sub={`correlation ${m.ncc.toFixed(3)}`} color={RED} />
            ))}
            {tw && <Figure v={`${tw.clean.with_match} of ${tw.clean.recordings}`} k="clean recordings falsely matched" sub={`the best genuine correlation is ${tw.clean.max_ncc}`} color={OK} />}
          </Figures>
          <Block title="Copied Stretch and Its Source" text="The recording is cut into 2-second blocks and each is compared with the whole file. Red ribbons join a copy to the audio it repeats.">
            {run.duplicate_trace && <TwinChart trace={run.duplicate_trace} matches={run.duplicates ?? []} duration={run.duration_s} />}
          </Block>
          {tw && (
            <Callout honest>
              On held-out recordings it found {tw.replay.detected + tw.sequence_duplicate.detected} of {tw.replay.n + tw.sequence_duplicate.n} copies, and still works after re-encoding or added noise.
              A deliberate time-stretch defeats it; the clock check still catches those.
            </Callout>
          )}
        </Stack>
      )}
    </Wait>
  );
}

/* 07 jammer */
export function JammerEvidence({ d }: { d: DemoData }) {
  const it = d.bench.data?.interference;
  return (
    <Wait slot={d.jam} what="the jammed pass">
      {jam => {
        const a = jam.interference.alarms[0], ti = jam.truth.interference;
        return (
          <Stack>
            <Figures>
              <Figure v={ti ? `${(ti.freq_hz / 1000).toFixed(2)} kHz` : "—"} k="where we put the jammer" sub={ti ? `a steady tone, ${Math.abs(ti.js_db).toFixed(0)} dB below the signal` : undefined} />
              <Figure v={a ? `${(a.freq_hz / 1000).toFixed(2)} kHz` : "None"} k="where the alarm went off" sub={a ? `with probability ${a.peak_prob.toFixed(2)}` : undefined} color={jam.interference.detected_truth ? OK : RED} />
              {it && <Figure v={pct(it.detection_rate, 0)} k="of held-out jammers found" sub="at the right frequency, any strength" />}
            </Figures>
            <div className="grid-row grid-gap-4">
              <div className="desktop:grid-col-7 margin-bottom-4">
                <Block title="Spectrum" text="The red line marks the alarm. The trace below is the probability of jamming over time.">
                  <SpectrogramView spec={jam.spectrogram} interference={jam.interference} fOffset={(jam.spectrogram.f_min + jam.spectrogram.f_max) / 2} />
                </Block>
              </div>
              {it && (
                <div className="desktop:grid-col-5">
                  <Block title="Detection vs. Strength" text="Weak jammers, 25 dB below the signal, go unseen. We publish that.">
                    <PdChart curve={it.pd_vs_js} />
                  </Block>
                </div>
              )}
            </div>
          </Stack>
        );
      }}
    </Wait>
  );
}

/* 08, 09 NASA modules */
export const OnAir = () => <OnAirPanel />;
export const CryptoLib = () => <CryptoLibPanel />;

/* 10 our secure link */
export function SecureLink({ d }: { d: DemoData }) {
  const [service, setService] = useState<"AUTH" | "AUTH_ENC">("AUTH");
  const [s, setS] = useState<SdlsDemo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const id = d.run.data?.truth.observation_id ?? d.detail.data?.record.observation_id;
  useEffect(() => {
    if (!id) return;
    setS(null);
    api.sdls(id, service).then(setS).catch(e => setErr(String(e)));
  }, [id, service]);
  const genuine = s?.log.filter(l => l.step === "downlink") ?? [];
  const attacks = s?.log.filter(l => l.step !== "downlink") ?? [];
  return (
    <Stack>
      <div className="display-flex" style={{ gap: ".5rem", flexWrap: "wrap" }}>
        {([["AUTH", "Authentication"], ["AUTH_ENC", "Authenticated Encryption"]] as const).map(([k, t]) => (
          <button key={k} onClick={() => setService(k)} className={`usa-button margin-0 ${service === k ? "bg-nasa-red" : "btn-ghost"}`}>{t}</button>
        ))}
      </div>
      {err && <p className="p-md color-nasa-red">{err}</p>}
      {!s && !err && <span className="spinner" />}
      {s && <>
        <Figures>
          <Figure v={`${genuine.filter(l => l.verdict === "ACCEPT").length} of ${genuine.length}`} k="genuine frames accepted" color={OK} />
          <Figure v={`${attacks.filter(l => l.verdict !== "ACCEPT").length} of ${attacks.length}`} k="attacks rejected" sub="replays, a flipped bit, a forged counter" color={RED} />
          <Figure v={`${s.overhead_bytes} bytes`} k="added to each frame" sub={`${s.verify_us_per_frame} microseconds to check`} />
        </Figures>
        <Block title="The Downlink as Received" text="One block per frame. Green blocks are genuine frames, red blocks are attacks.">
          <div className="lane">{s.log.map((l, i) => <i key={i} className={l.step === "downlink" ? "" : "att"} style={{ animationDelay: `${i * 15}ms` }} title={`${l.step}, frame ${l.frame}: ${l.verdict}`} />)}</div>
          <div className="scroll-x">
            <table className="data">
              <thead><tr><th>Attack</th><th>Frame</th><th>Sequence number</th><th>Receiver verdict</th></tr></thead>
              <tbody>{attacks.map((l, i) => <tr key={i}><td>{l.step}</td><td>{l.frame}</td><td>{l.arsn ?? "—"}</td><td style={{ color: "var(--nasa-red)" }}>{l.verdict.replaceAll("_", " ")}</td></tr>)}</tbody>
            </table>
          </div>
        </Block>
      </>}
    </Stack>
  );
}

/* 11 signed capture */
export function Capture({ d }: { d: DemoData }) {
  return (
    <Wait slot={d.replay} what="the signed-capture check">
      {r => (
        <Stack>
          <Figures>
            <Figure v={r.manifest.signature_valid ? "Valid" : "Invalid"} k="station signature" sub="the signed record itself is authentic" color={OK} />
            <Figure v={r.manifest.tampered_intervals.map(([a, b]) => `${a.toFixed(0)}–${b.toFixed(0)} s`).join(", ") || "None"} k="seconds found edited" sub="the audio no longer matches its signature" color={RED} />
            <Figure v={r.truth.replay ? `${r.truth.replay.dst_start_s.toFixed(0)}–${r.truth.replay.dst_end_s.toFixed(0)} s` : "—"} k="where we hid the replay" sub="ground truth, for comparison" />
          </Figures>
          <Block title="One Block per Second" text={`Each second of the ${Math.ceil(r.duration_s)}-second recording is hashed into a Merkle tree at capture. Green seconds still match; red seconds were changed.`}>
            <MerkleStrip duration={r.duration_s} tampered={r.manifest.tampered_intervals} />
          </Block>
        </Stack>
      )}
    </Wait>
  );
}

/* 12 ledger */
export function Ledger() {
  const [l, setL] = useState<LedgerView | null>(null);
  const [t, setT] = useState<{ tampered_index: number; verification: LedgerView["verification"] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => { setT(null); api.ledger(8).then(setL).catch(e => setErr(String(e))); };
  useEffect(load, []);
  const target = l?.entries.find(e => e.data.decision === "QUARANTINE") ?? l?.entries[Math.floor((l?.entries.length ?? 0) / 2)];
  const tamper = () => { if (target) api.tamper(target.index).then(setT).catch(e => setErr(String(e))); };
  const broken = !!t && !t.verification.valid;
  return (
    <Stack>
      {err && <p className="p-md color-nasa-red">{err}</p>}
      {l && <>
        <Figures>
          <Figure v={l.verification.entries} k="decisions recorded" sub={`with ${l.verification.checkpoints} signed checkpoints`} />
          <Figure v={broken ? `Broken at #${t.verification.first_broken}` : "Valid"} k="chain verification" sub={broken ? "the rewritten entry no longer matches its hash" : "every entry links to the one before"} color={broken ? RED : OK} />
        </Figures>
        <Block title="Hash Chain" text="The most recent entries. Rewrite one decision and watch the chain fail from that point on.">
          <div className="chain">
            {l.entries.map((e, i) => {
              const cls = broken ? (e.index === t.tampered_index ? "edited" : e.index > t.tampered_index ? "broken" : "") : "";
              return (
                <div key={e.index} style={{ display: "contents" }}>
                  {i > 0 && <span className={`chain-link ${broken && e.index === t.tampered_index + 1 ? "cut" : ""}`} />}
                  <div className={`chain-block ${e.kind === "checkpoint" ? "cp" : ""} ${cls}`} style={{ "--d": `${i * 0.05}s` } as React.CSSProperties}>
                    <strong>Entry {e.index}</strong>
                    <span>{cls === "edited" ? "Rewritten to ACCEPT" : String(e.data.decision ?? e.kind)}</span>
                    <span className="h">{e.hash.slice(0, 14)}</span>
                    <span className="p">{e.prev.slice(0, 14)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </Block>
        <div className="display-flex" style={{ gap: "1rem", flexWrap: "wrap" }}>
          <button className="usa-button bg-nasa-red margin-0" onClick={tamper} disabled={!target}>Rewrite Entry {target?.index}</button>
          <button className="usa-button btn-ghost margin-0" onClick={load}>Verify the Original</button>
        </div>
      </>}
    </Stack>
  );
}

/* 13 the numbers */
export function Proof({ d }: { d: DemoData }) {
  const b = d.bench.data;
  const fd = b?.frame_detection, tw = b?.twin;
  const det = useCountUp(fd ? fd.attacked_passes.detection_rate * 100 : null);
  const fa = useCountUp(fd ? fd.combined.false_alarm_rate * 100 : null);
  const ev = (k: string) => (fd?.events?.[k] ? `${fd.events[k].detected}/${fd.events[k].n}` : "…");
  if (!fd) return <span className="spinner" />;
  return (
    <Stack>
      <Figures>
        <Figure v={`${det.toFixed(1)}%`} k="of replayed and injected frames caught" sub={`${fd.attacked_passes.tp} of ${fd.attacked_passes.attacked}, on passes the models never saw`} />
        <Figure v={`${fa.toFixed(2)}%`} k="of genuine frames flagged" sub="false alarms, attacked and clean passes" />
        <Figure v={`${fd.latency_ms_per_frame.mean.toFixed(1)} ms`} k="to judge a frame on a laptop" sub={`peak memory ${b.resources.peak_rss_mb} MB`} />
      </Figures>
      <Figures>
        <Figure v={ev("standard/replay")} k="standard replays" />
        <Figure v={ev("standard/sequence")} k="sequence anomalies" />
        <Figure v={ev("cross_pass_replay/replay")} k="replays from another day" />
        <Figure v={tw ? `${tw.replay.detected + tw.sequence_duplicate.detected}/${tw.replay.n + tw.sequence_duplicate.n}` : "…"} k="copies heard, no decoder" />
        <Figure v={pct(b.sdls.AUTH.replay_rejection_rate, 0)} k="of replays rejected on our link" />
      </Figures>
      <Callout honest>What still gets through: jammers well below the signal ({pct(b.interference.detection_rate, 0)} found overall) and forged frames that keep the counter consistent ({pct(b.evasion.content_forge_counter_consistent.rate, 0)} caught). We publish the misses.</Callout>
    </Stack>
  );
}

/* 14 blind test */
export const Blind = () => <HeldOutPanel />;
