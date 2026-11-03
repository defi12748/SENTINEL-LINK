"use client";

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Panel } from "@/components/AttackLab";
import { ClockChart, DopplerChart, FrameRibbon, SpectrogramView } from "@/components/Charts";
import { Arrow, Module, PrimaryLink } from "@/components/hds";
import { DecisionChip } from "@/components/ui";
import { api, type ObservationDetail, type ObservationSummary } from "@/lib/api";
import { fmtLong, useApi } from "@/lib/hooks";

const Globe = dynamic(() => import("@/components/Globe"), { ssr: false });

export default function PassPage() {
  const { id } = useParams<{ id: string }>();
  const { data: d, error } = useApi<ObservationDetail>(() => api.observation(Number(id)), [id]);
  const { data: list } = useApi<ObservationSummary[]>(api.observations);
  const waterfall = list?.find(o => o.id === Number(id))?.waterfall_url ?? null;
  const [play, setPlay] = useState(0);
  const [sel, setSel] = useState<number | null>(null);
  useEffect(() => {
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => { setPlay(((t - t0) / 30000) % 1); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  if (error) return <Module tone="black"><p className="mono red">{error}</p></Module>;
  if (!d) return <Module tone="black"><span className="spinner" /></Module>;

  const r = d.record;
  const counts = { ACCEPT: 0, VERIFY: 0, QUARANTINE: 0 } as Record<string, number>;
  d.frames.forEach(f => { counts[f.decision] += 1; });
  const current = d.frames.reduce((a, f) => (f.t_rec <= play * d.spectrogram.duration_s ? f : a), d.frames[0]);
  const facts: [string, string][] = [
    ["Station", r.station_name], ["Start", `${fmtLong(r.start)}, ${r.start.slice(11, 19)} UTC`],
    ["Max Elevation", `${r.max_altitude?.toFixed(0) ?? "—"}°`], ["Downlink", `${(r.frequency_hz / 1e6).toFixed(3)} MHz · ${r.mode}`],
    ["Frames Decoded", `${d.frames.length}`], ["Split", d.split],
  ];

  return (
    <>
      <div className="bg-carbon-black color-spacesuit-white">
        <div className="grid-container grid-container-extrawide padding-x-3 padding-y-6">
          <div className="grid-row grid-gap-4">
            <div className="desktop:grid-col-5">
              <h3 className="label color-nasa-red margin-bottom-2">Pass #{r.observation_id}</h3>
              <h1 className="display-60 margin-0">{r.station_name}</h1>
              <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: ".75rem 1.5rem", margin: "2rem 0" }}>
                {facts.map(([k, v]) => (
                  <div key={k} style={{ display: "contents" }}>
                    <dt className="label color-carbon-40" style={{ alignSelf: "center" }}>{k}</dt>
                    <dd className="heading-16 margin-0">{v}</dd>
                  </div>
                ))}
              </dl>
              <div className="display-flex flex-align-center" style={{ gap: ".75rem", flexWrap: "wrap" }}>
                {(["ACCEPT", "VERIFY", "QUARANTINE"] as const).map(k => (
                  <span key={k} className="display-flex flex-align-center" style={{ gap: ".4rem" }}>
                    <DecisionChip d={k} /><span className="mono">{counts[k]}</span>
                  </span>
                ))}
              </div>
              <div className="margin-top-4 display-flex" style={{ gap: "2rem", flexWrap: "wrap" }}>
                <PrimaryLink href={`/attack-lab?obs=${r.observation_id}`} white>Attack This Pass</PrimaryLink>
                <a className="button-primary" href={`https://network.satnogs.org/observations/${r.observation_id}/`} target="_blank" rel="noreferrer">
                  <span className="line-height-alt-1 color-spacesuit-white-important">Original on SatNOGS</span><Arrow />
                </a>
              </div>
            </div>
            <div className="desktop:grid-col-7">
              <div style={{ position: "relative", height: 460 }}>
                <Globe orbit={d.orbit} pass={d.geometry} station={{ lat: r.station_lat, lon: r.station_lng }} playhead={play}
                  alert={current.decision !== "ACCEPT"} unix={Date.parse(r.start) / 1000} />
              </div>
            </div>
          </div>
        </div>
      </div>
      <Module tone="dark">
        <div style={{ display: "grid", gap: "3rem" }}>
          <Panel title="Frame Counter vs. Clock">
            <ClockChart frames={d.frames} clock={d.clock} selected={sel} onSelect={setSel} />
            <FrameRibbon frames={d.frames} selected={sel} onSelect={setSel} />
          </Panel>
          <div style={{ display: "grid", gap: "2rem", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 520px), 1fr))" }}>
            <Panel title="Spectrum"><SpectrogramView spec={d.spectrogram} interference={d.interference} fOffset={d.f_offset_hz} /></Panel>
            <Panel title="Doppler"><DopplerChart tracks={d.tracks} frames={d.frames} /></Panel>
          </div>
          {waterfall && (
            <Panel title="The Station's Own Waterfall" sub="Recorded by the SatNOGS station during this pass, as published on the network">
              <a href={waterfall} target="_blank" rel="noreferrer" style={{ display: "block", maxWidth: 560, maxHeight: 340, overflow: "hidden", border: "1px solid var(--carbon-80)" }}>
                <img alt={`SatNOGS waterfall for observation ${r.observation_id}`} src={waterfall} style={{ width: "100%", display: "block" }} />
              </a>
            </Panel>
          )}
          <Panel title="Frames">
            <div className="scroll-x" style={{ maxHeight: 420, overflowY: "auto" }}>
              <table className="data">
                <thead><tr><th>#</th><th>t (s)</th><th>Type</th><th>Sequence</th><th>Battery</th><th>P</th><th>Decision</th><th>SHA-256</th></tr></thead>
                <tbody>
                  {d.frames.map(f => (
                    <tr key={f.index} onClick={() => setSel(f.index)} style={{ cursor: "pointer", background: sel === f.index ? "#2e2e32" : undefined }}>
                      <td>{f.index}</td><td>{f.t_rec.toFixed(1)}</td><td>{f.frame_type}</td><td>{f.sequence}</td>
                      <td>{f.battery_v?.toFixed(2)} V</td><td>{f.probability.toFixed(3)}</td><td><DecisionChip d={f.decision} /></td>
                      <td>{f.sha256.slice(0, 12)}…</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      </Module>
    </>
  );
}
