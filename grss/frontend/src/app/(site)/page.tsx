"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Callout, LinkStrip, MagHero, PrimaryLink, Story, SubscriptionBanner, TopicGrid,
} from "@/components/hds";
import { pct } from "@/components/ui";
import { api, type Benchmark, type ObservationDetail, type ObservationSummary } from "@/lib/api";
import { DOCS } from "@/lib/docs";
import { PHOTOS, PHOTO_LIST, useApi } from "@/lib/hooks";

const Globe = dynamic(() => import("@/components/Globe"), { ssr: false });

const STEPS = [
  { n: "01", t: "Capture & Sign", d: "The station hashes every second of the recording and signs it. Any later edit is pinpointed.", img: PHOTOS.dsnNew, href: "/trust" },
  { n: "02", t: "Decode", d: "Demodulate and error-correct each frame, keeping its exact arrival time and the carrier's Doppler.", img: PHOTOS.dsn, href: "/docs/signal-processing" },
  { n: "03", t: "Detect", d: "Check every frame against the spacecraft's clock, its Doppler, its telemetry and the spectrum, inside NASA OnAIR.", img: PHOTOS.aurora, href: "/nasa" },
  { n: "04", t: "Respond", d: "Accept, ask for verification or quarantine. Remove jammers. Log every decision in a signed chain.", img: PHOTOS.missionControl, href: "/results" },
];

export default function Home() {
  const { data: obs } = useApi<ObservationSummary[]>(api.observations);
  const { data: bench } = useApi<Benchmark>(api.benchmark);
  const lead = useMemo(() => (obs ?? []).filter(o => o.split === "held-out").sort((a, b) => b.frames - a.frames)[0], [obs]);
  const [detail, setDetail] = useState<ObservationDetail | null>(null);
  useEffect(() => { if (lead) api.observation(lead.id).then(setDetail).catch(() => undefined); }, [lead]);

  const [play, setPlay] = useState(0);
  useEffect(() => {
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => { setPlay(((t - t0) / 24000) % 1); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
  const frames = detail?.frames ?? [];
  const current = frames.length ? frames.reduce((a, f) => (f.t_rec <= play * detail!.spectrogram.duration_s ? f : a), frames[0]) : null;

  const fd = bench?.frame_detection;
  const it = bench?.interference;
  const sd = bench?.sdls?.AUTH;
  const proof = [
    { v: fd ? pct(fd.attacked_passes.detection_rate, 0) : "—", k: "of replayed and injected frames caught", sub: fd ? `${fd.attacked_passes.tp} of ${fd.attacked_passes.attacked}, on passes the models never saw` : "" },
    { v: fd ? pct(fd.combined.false_alarm_rate, 1) : "—", k: "of genuine frames flagged", sub: "false alarms, attacked and clean passes" },
    { v: sd ? pct(sd.replay_rejection_rate, 0) : "—", k: "of replays rejected on our secure link", sub: sd ? `${sd.overhead_bytes} bytes and ${sd.verify_us_per_frame} microseconds per frame` : "" },
    { v: fd ? `${fd.latency_ms_per_frame.mean.toFixed(1)} ms` : "—", k: "to judge a frame on a laptop", sub: it ? `jammers: ${pct(it.detection_rate, 0)} caught` : "" },
  ];

  return (
    <>
      <LinkStrip
        when={<>TSYP14 Challenge · <strong>Track 1</strong> · Secure Ground-Link Testbed</>}
        title="Can a stored signal be authenticated?"
        text="Yes. Ours are signed at capture, and every frame is checked against physics the attacker can't fake."
        image={PHOTOS.cubesatDeploy}
        href="/docs/compliance"
      />

      <MagHero slides={[
        {
          title: "Sentinel Link",
          text: "Satellite telemetry can be replayed, injected or jammed without anyone noticing. Sentinel Link catches it before it reaches the analyst.",
          cta: "Try an Attack", href: "/attack-lab", thumb: PHOTOS.earthNight,
          media: detail
            ? <Globe orbit={detail.orbit} pass={detail.geometry} station={{ lat: detail.record.station_lat, lon: detail.record.station_lng }}
                playhead={play} alert={!!current && current.decision !== "ACCEPT"} unix={Date.parse(detail.record.start) / 1000} />
            : <img alt="" src={PHOTOS.earthNight} style={{ objectFit: "cover" }} />,
          cols: [
            { label: "Real Data", link: "30 SatNOGS Recordings", href: "/passes" },
            { label: "Live Pass", link: current ? `Frame ${current.index}: ${current.decision}` : "AO-73", href: lead ? `/passes/${lead.id}` : "/passes" },
            { label: "NASA Modules", link: "OnAIR + CryptoLib, Live", href: "/nasa" },
          ],
        },
        {
          title: "Replays Are Caught",
          text: "Every AO-73 frame carries an on-board counter. A replayed frame falls behind the spacecraft's clock by exactly its delay.",
          cta: "Replay a Pass", href: "/attack-lab?preset=replay", thumb: PHOTOS.cubesat,
          media: <img alt="" src={PHOTOS.cubesat} style={{ objectFit: "cover" }} />,
          cols: [
            { label: "Same-Pass Replay", link: "Counter vs. Clock", href: "/docs/detection" },
            { label: "Replay From Another Day", link: "Thousands of Frames Off", href: "/attack-lab?preset=cross" },
            { label: "Spliced Audio", link: "Doppler Jumps", href: "/docs/detection" },
          ],
        },
        {
          title: "Copies Are Heard",
          text: "Receiver noise never repeats. Audio copied inside a recording is the same noise twice, found without decoding a single frame.",
          cta: "See It Live", href: "/demo#twin", thumb: PHOTOS.dsnTracks,
          media: <img alt="" src={PHOTOS.dsnTracks} style={{ objectFit: "cover" }} />,
          cols: [
            { label: "In-Pass Replays", link: "Found Without a Decoder", href: "/demo#twin" },
            { label: "Clean Recordings", link: "No False Matches", href: "/results" },
            { label: "Any Satellite", link: "Format-Independent", href: "/docs/detection" },
          ],
        },
        {
          title: "Jammers Are Found",
          text: "Added interference is located in frequency and time, then removed. The decoder picks the cleanup that recovers the most frames.",
          cta: "Jam a Pass", href: "/attack-lab?preset=jam", thumb: PHOTOS.aurora2,
          media: <img alt="" src={PHOTOS.aurora2} style={{ objectFit: "cover" }} />,
          cols: [
            { label: "Detection", link: "Calibrated Probability", href: "/results" },
            { label: "Response", link: "Closed-Loop Excision", href: "/docs/adversarial-validation" },
            { label: "Hidden Damage", link: "Lost Frames Flagged", href: "/docs/adversarial-validation" },
          ],
        },
      ]} />

      {/* How it works: HDS content cards */}
      <div className="hds-module hds-module-full alignfull bg-spacesuit-white color-mode-light hds-color-mode-light padding-y-9 padding-x-3">
        <div className="grid-container grid-container-block">
          <div className="grid-row flex-align-center margin-bottom-5">
            <div className="desktop:grid-col"><h2 className="section-heading-md">How It Works</h2></div>
            <div className="desktop:grid-col display-flex desktop:flex-justify-end"><PrimaryLink href="/docs/architecture">Architecture</PrimaryLink></div>
          </div>
          <div className="grid-row grid-gap-4">
            {STEPS.map(s => (
              <Link key={s.n} href={s.href} className="tablet:grid-col-6 desktop:grid-col-3 margin-bottom-6" style={{ textDecoration: "none", color: "inherit" }}>
                <div className="hds-cover-wrapper cover-hover-zoom bg-carbon-black" style={{ aspectRatio: "4 / 3" }}>
                  <figure className="hds-media-background"><img alt="" src={s.img} style={{ objectFit: "cover" }} /></figure>
                </div>
                <div className="label color-nasa-red margin-top-3 margin-bottom-1">Step {s.n}</div>
                <h3 className="heading-22 margin-bottom-1">{s.t}</h3>
                <p className="p-sm margin-0 color-carbon-60">{s.d}</p>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* Proof */}
      <div className="hds-module hds-module-full alignfull bg-carbon-black color-spacesuit-white color-mode-dark padding-y-9 padding-x-3">
        <div className="grid-container grid-container-block">
          <div className="grid-row flex-align-center margin-bottom-6">
            <div className="desktop:grid-col">
              <h3 className="label color-nasa-red margin-bottom-2">Measured, Not Claimed</h3>
              <h2 className="section-heading-md color-spacesuit-white">The Proof</h2>
            </div>
            <div className="desktop:grid-col display-flex desktop:flex-justify-end"><PrimaryLink href="/results" white>Full Results</PrimaryLink></div>
          </div>
          <div className="grid-row grid-gap-4">
            {proof.map(p => (
              <div key={p.k} className="tablet:grid-col-6 desktop:grid-col-3 margin-bottom-5" style={{ borderTop: "1px solid #58585b", paddingTop: "1.25rem" }}>
                <div className="display-60 color-spacesuit-white">{p.v}</div>
                <p className="heading-18 margin-top-2 margin-bottom-1 color-spacesuit-white">{p.k}</p>
                <p className="label color-carbon-40 margin-0">{p.sub}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <Callout title="The Live Demo" text="Fourteen chapters, every one computed live: attack a real pass, watch the verdicts land, then break the ledger yourself."
        button="Launch the Demo" href="/demo" image={PHOTOS.missionControl} />

      <Callout title="Attack It Yourself" text="Pick a real recording. Replay frames, inject an anomaly, add a jammer. The full chain decodes it and judges every frame."
        button="Open the Attack Lab" href="/attack-lab" image={PHOTOS.earthNight} />

      <Story subtitle="Trust Anchor · NASA CryptoLib" title="Byte for Byte"
        lead="On links we control, frames are signed with the CCSDS space-link security standard. Ours match NASA CryptoLib exactly."
        text="Testing against it, we found that CryptoLib 1.7.5 checks for replays on commands only. A replayed telemetry frame with a valid signature passes. Ours rejects it."
        image={PHOTOS.dsnTracks} caption="Deep Space Network antenna, Goldstone, California." credit="NASA/JPL-Caltech"
        button="See It Live" href="/trust" />

      <SubscriptionBanner title="Bring Your Own Recording" text="Upload any AO-73 recording. No metadata needed: we read the time from the spacecraft's clock."
        button="Upload" href="/attack-lab#upload" />

      <TopicGrid heading="Challenge Deliverables" button="All Documents" buttonHref="/docs"
        cards={DOCS.slice(1, 5).map((d, i) => ({ title: d.short, href: `/docs/${d.slug}`, image: PHOTO_LIST[(i + 2) % PHOTO_LIST.length] }))} />
    </>
  );
}
