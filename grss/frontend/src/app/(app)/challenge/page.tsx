"use client";

import Link from "next/link";
import { Module, PageIntro, PrimaryLink, SectionHead } from "@/components/hds";
import { pct } from "@/components/ui";
import { api, type Benchmark, type Interop, type ObservationSummary } from "@/lib/api";
import { DOCS } from "@/lib/docs";
import { PHOTOS, useApi } from "@/lib/hooks";

type Row = { req: string; how: string; evidence: string; href: string };

export default function ChallengePage() {
  const { data: b } = useApi<Benchmark>(api.benchmark);
  const { data: obs } = useApi<ObservationSummary[]>(api.observations);
  const { data: interop } = useApi<Interop>(api.interop);
  const fd = b?.frame_detection;
  const it = b?.interference;
  const sd = b?.sdls;
  const ev = (k: string) => (fd?.events?.[k] ? `${fd.events[k].detected}/${fd.events[k].n} caught` : "—");
  const stations = new Set((obs ?? []).map(o => o.station)).size;

  const attacks = [
    { spec: "Replay a valid 5–20-frame subsequence", result: ev("standard/replay"), extra: `Replay from another pass: ${ev("cross_pass_replay/replay")}`, preset: "replay", img: PHOTOS.cubesat },
    { spec: "Inject one sequence anomaly", result: ev("standard/sequence"), extra: fd ? `Forged-counter evasion: ${pct(b.evasion?.counter_forge_far?.rate, 0)} caught` : "", preset: "standard", img: PHOTOS.cubesatDeploy },
    { spec: "Add narrowband interference at a hidden SNR", result: it ? `${pct(it.detection_rate, 0)} of jammed recordings` : "—", extra: "Located, removed, lost frames flagged", preset: "jam", img: PHOTOS.aurora2 },
  ];

  const metrics: [string, string, string][] = [
    ["Detection quality", fd ? `${pct(fd.attacked_passes.detection_rate)} of attacked frames · ROC-AUC ${fd.combined.roc_auc}` : "—", "Held-out passes, decoded from attacked audio"],
    ["False alarms", fd ? `${pct(fd.combined.false_alarm_rate, 2)} of genuine frames` : "—", "Attacked and clean passes"],
    ["Latency", fd ? `${fd.latency_ms_per_frame.mean.toFixed(2)} ms per frame` : "—", "After decoding; decoding runs ≈35× faster than real time"],
    ["Memory", b ? `${b.resources.peak_rss_mb} MB peak` : "—", "Whole benchmark process, laptop CPU"],
    ["Security overhead", sd ? `${sd.AUTH.overhead_bytes} B and ${sd.AUTH.verify_us_per_frame} µs per 256 B frame` : "—", sd ? `Authenticated encryption: ${sd.AUTH_ENC.overhead_bytes} B` : ""],
  ];

  const track: Row[] = [
    { req: "Use recorded SatNOGS observations or organizer telemetry", how: `${obs?.length ?? "…"} SatNOGS recordings from ${stations || "…"} stations; frame files (KISS) accepted too`, evidence: "Passes", href: "/passes" },
    { req: "Authenticate a local command/telemetry sequence", how: "CCSDS SDLS link: anti-replay sequence number + 128-bit MAC", evidence: interop?.byte_identical ? "Byte-identical to NASA CryptoLib" : "Trust", href: "/trust" },
    { req: "Authenticate a stored signal", how: "Station-signed per-second Merkle manifest of the recording", evidence: b?.manifest?.all_attacks_detected ? "Every attacked recording rejected" : "Trust", href: "/trust" },
    { req: "Detect replay, sequence injection, interference", how: "Clock, Doppler, telemetry and spectrum evidence fused into a probability", evidence: "Attack Lab", href: "/attack-lab" },
    { req: "Processing: demodulated features, spectral occupancy, sequence analysis", how: "gr-satellites demodulation, per-block FEC with exact timing, STFT evidence, counter analysis", evidence: "Signal processing", href: "/docs/signal-processing" },
    { req: "Classifier with calibrated confidence", how: "Isotonic-calibrated gradient boosting; calibrated logistic fusion", evidence: fd ? `Calibration error ${fd.calibration_ece}` : "Detection", href: "/docs/detection" },
    { req: "Jury supplies a held-out recording", how: "Blind analysis: no metadata needed, time read from the spacecraft clock", evidence: "Upload", href: "/attack-lab#upload" },
    { req: "Files or conducted setup only, no radiated attack", how: "All attacks are digital edits of recordings", evidence: "Threat model", href: "/docs/threat-model" },
  ];

  const tools: [string, string, boolean][] = [
    ["SatNOGS Network", "30 observations: audio, station decodes, TLEs", true],
    ["gr-satellites", "DBPSK demodulation and AO-40 decoding", true],
    ["NASA OnAIR (NOS3)", "Runs on every pass: its test suite plus our clock plugin", true],
    ["NASA CryptoLib (NOS3)", interop?.available ? `Run live; ${interop.byte_identical ? "byte-identical frames" : "frames differ"}` : "Interop tests", true],
    ["PyOD", "ECOD outlier score on telemetry", true],
    ["Universal Radio Hacker", "Attacked recordings are plain WAV, open directly in URH", false],
  ];

  return (
    <>
      <PageIntro kicker="TSYP14 · Track 1 · Challenge Specification" title="The Challenge, Answered" image={PHOTOS.earthObs}
        text="Every requirement of the Track 1 specification, with the evidence behind it." />

      <Module tone="light">
        <SectionHead title="The Standard Test" button="Run It" href="/attack-lab" />
        <div className="grid-row grid-gap-4">
          {attacks.map(a => (
            <div key={a.spec} className="desktop:grid-col-4 margin-bottom-6">
              <div className="hds-cover-wrapper bg-carbon-black" style={{ aspectRatio: "16 / 9" }}>
                <figure className="hds-media-background"><img alt="" src={a.img} style={{ objectFit: "cover" }} /></figure>
              </div>
              <div className="label color-carbon-60 margin-top-3 margin-bottom-1">Specification</div>
              <h3 className="heading-22 margin-bottom-2">{a.spec}</h3>
              <div className="display-48" style={{ lineHeight: 1.1 }}>{a.result}</div>
              <p className="p-sm color-carbon-60 margin-top-1">{a.extra}</p>
              <PrimaryLink href={`/attack-lab?preset=${a.preset}`} size="sm">Try it</PrimaryLink>
            </div>
          ))}
        </div>
      </Module>

      <Module tone="black">
        <SectionHead title="Required Metrics" button="Full Results" href="/results" />
        <div className="scroll-x">
          <table className="data">
            <thead><tr><th>Metric</th><th>Value</th><th>Measured on</th></tr></thead>
            <tbody>
              {metrics.map(([m, v, n]) => (
                <tr key={m}><td className="heading-16" style={{ fontFamily: "var(--font-display)" }}>{m}</td><td style={{ color: "#fff" }}>{v}</td><td style={{ color: "var(--carbon-40)", whiteSpace: "normal" }}>{n}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Module>

      <Module tone="light">
        <SectionHead title="Track 1 Requirements" />
        <div>
          {track.map((r, i) => (
            <div key={r.req} className="grid-row grid-gap-4 padding-y-3" style={{ borderTop: "1px solid #d1d1d1" }}>
              <div className="desktop:grid-col-1"><span className="label color-nasa-red">{String(i + 1).padStart(2, "0")}</span></div>
              <div className="desktop:grid-col-4"><h3 className="heading-18 margin-0">{r.req}</h3></div>
              <div className="desktop:grid-col-5"><p className="p-sm margin-0">{r.how}</p></div>
              <div className="desktop:grid-col-2">
                <Link href={r.href} className="label" style={{ color: "#1a7f45", textDecoration: "none" }}>✓ {r.evidence} →</Link>
              </div>
            </div>
          ))}
        </div>
      </Module>

      <Module tone="grey">
        <div className="grid-row grid-gap-6">
          <div className="desktop:grid-col-6 margin-bottom-6">
            <SectionHead title="Six Deliverables" />
            {DOCS.slice(1).map((d, i) => (
              <Link key={d.slug} href={`/docs/${d.slug}`} className="display-flex flex-align-center padding-y-2"
                style={{ borderTop: "1px solid #d1d1d1", textDecoration: "none", color: "inherit", gap: "1rem" }}>
                <span className="label color-nasa-red">0{i + 1}</span>
                <span className="heading-18" style={{ flex: 1 }}>{d.title}</span>
                <span className="label" style={{ color: "#1a7f45" }}>Done</span>
              </Link>
            ))}
          </div>
          <div className="desktop:grid-col-6">
            <SectionHead title="Official Tools" />
            {tools.map(([t, use, used]) => (
              <div key={t} className="display-flex padding-y-2" style={{ borderTop: "1px solid #d1d1d1", gap: "1rem" }}>
                <span className="heading-18" style={{ width: 220, flex: "none" }}>{t}</span>
                <span className="p-sm" style={{ flex: 1 }}>{use}</span>
                <span className="label" style={{ color: used ? "#1a7f45" : "var(--carbon-60)" }}>{used ? "Used" : "Compatible"}</span>
              </div>
            ))}
          </div>
        </div>
      </Module>
    </>
  );
}
