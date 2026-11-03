"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  Blind, Briefing, Capture, ClockEvidence, CryptoLib, JammerEvidence, Ledger, LiveAttack, OnAir, Pipeline, Proof, SecureLink, Threat, TwinEvidence,
} from "@/components/demo/chapters";
import { useDemoData, type DemoData } from "@/components/demo/data";
import { Arrow, Header, Module } from "@/components/hds";
import { PHOTOS } from "@/lib/photos";

const Globe = dynamic(() => import("@/components/Globe"), { ssr: false });

interface Chapter {
  id: string; kicker: string; title: string; text: string; image: string; tone: "dark" | "black" | "light" | "grey";
  notes: string[]; render: (d: DemoData) => ReactNode;
}

const CHAPTERS: Chapter[] = [
  { id: "briefing", kicker: "TSYP14 Challenge, Track 1", title: "Sentinel Link", image: PHOTOS.earthNight, tone: "black",
    text: "Can a stored satellite signal be authenticated? Cryptography where the link allows it, physics where it doesn't.",
    render: d => <Briefing d={d} />,
    notes: ["Everything in this demo comes from the running backend.", "Two NASA modules from NOS3 run inside our chain: OnAIR and CryptoLib.", "The globe is the real AO-73 pass over the station."] },
  { id: "threat", kicker: "The Threat", title: "Valid Data, Wrong Moment", image: PHOTOS.cubesatDeploy, tone: "black",
    text: "Amateur and Earth-observation downlinks carry no authentication. A replayed frame is bit-for-bit genuine.",
    render: d => <Threat d={d} />,
    notes: ["Integrity is not authentication: a replay passes every checksum.", "We decode more frames from raw audio than the stations did.", "All scores are measured on held-out passes."] },
  { id: "attack", kicker: "Live", title: "Watch It Get Attacked", image: PHOTOS.missionControl, tone: "black",
    text: "A 20-frame replay, one injected anomaly and a weak hidden jammer, mixed into a real recording and judged frame by frame.",
    render: d => <LiveAttack d={d} />,
    notes: ["Let it play; the replay near 243 s turns red frame by frame.", "Then reveal the hidden truth: the bands line up with the quarantined frames.", "Be upfront: the weak jammer is missed on this run."] },
  { id: "pipeline", kicker: "Inside the Chain", title: "Every Stage, Its Evidence", image: PHOTOS.dsn, tone: "black",
    text: "From the signed recording to the signed ledger, in ten stages. Click any stage to see what it checked.",
    render: d => <Pipeline d={d} />,
    notes: ["Click NASA OnAIR: its limits stay green, its clock plugin goes red.", "Click Audio Twin: the copied stretch, found without decoding.", "Click Decision: quarantine above 0.9, verify above 0.5."] },
  { id: "clock", kicker: "Evidence One", title: "Replays Fall Behind", image: PHOTOS.cubesat, tone: "dark",
    text: "AO-73 counts its frames on board. Learned from the public archive, that clock predicts every genuine frame to within one.",
    render: d => <ClockEvidence d={d} />,
    notes: ["The dashed line is the spacecraft's clock.", "The replayed frames sit about 40 frames under it: the replay delay, measured."] },
  { id: "twin", kicker: "Evidence Two", title: "Noise Never Repeats", image: PHOTOS.dsnTracks, tone: "dark",
    text: "Receiver noise is new at every instant. Audio copied inside a recording is the same noise twice, so it matches its source almost perfectly.",
    render: d => <TwinEvidence d={d} />,
    notes: ["A copy correlates at 0.99 with its source; genuine audio never exceeds 0.27.", "It never decodes, so it works on any satellite."] },
  { id: "jammer", kicker: "Evidence Three", title: "Jammers Are Located", image: PHOTOS.aurora2, tone: "dark",
    text: "A calibrated classifier reads the spectrum. An alarm only counts if it points at the jammer's frequency.",
    render: d => <JammerEvidence d={d} />,
    notes: ["The red line on the spectrogram is the alarm, right on the jammer.", "Show the strength curve honestly: weak jammers get through."] },
  { id: "onair", kicker: "NASA Module", title: "NASA OnAIR, Live", image: PHOTOS.sunrise, tone: "dark",
    text: "Every decoded frame streams through NASA's On-board AI Research platform, with a clock plugin we wrote for it.",
    render: () => <OnAir />,
    notes: ["Top strip: all green, because replayed data looks physically plausible.", "Second strip: our plugin inside OnAIR turns red on the attacked frames."] },
  { id: "cryptolib", kicker: "NASA Module", title: "NASA CryptoLib, Live", image: PHOTOS.dsnNew, tone: "light",
    text: "Our protected frames are byte-identical to NASA CryptoLib's. Testing against it, we found it accepts a replayed telemetry frame. Ours rejects it.",
    render: () => <CryptoLib />,
    notes: ["Same frames through both libraries: identical output.", "The gap: CryptoLib 1.7.5 only checks replays on commands."] },
  { id: "sdls", kicker: "Our Own Link", title: "Cryptography Where It Can", image: PHOTOS.sentinel6, tone: "black",
    text: "Every frame carries a sequence number and a message authentication code. Same real frames, attacked: nothing gets through.",
    render: d => <SecureLink d={d} />,
    notes: ["Green blocks are genuine frames, red blocks are attacks.", "Switch to authenticated encryption: same result."] },
  { id: "capture", kicker: "The Stored Signal", title: "Signed at Capture", image: PHOTOS.earthObs, tone: "dark",
    text: "The station signs every second of the recording. Verification points at exactly the seconds that changed.",
    render: d => <Capture d={d} />,
    notes: ["This answers the Track 1 question: yes, a stored signal can be authenticated.", "The red seconds match the hidden replay."] },
  { id: "ledger", kicker: "Audit Trail", title: "Break the Chain", image: PHOTOS.aqua, tone: "black",
    text: "Every decision is chained to the one before and signed. Quietly flip one and verification fails from that point on.",
    render: () => <Ledger />,
    notes: ["These are the entries our runs just wrote.", "Rewrite flips a quarantined frame to accepted, on a copy."] },
  { id: "proof", kicker: "Measured, Not Claimed", title: "By the Numbers", image: PHOTOS.aurora, tone: "black",
    text: "Trained on early passes. Measured on later dates and stations it never saw.",
    render: d => <Proof d={d} />,
    notes: ["99.3% of attacked frames, 0.71% false alarms.", "Close on the honest box: we publish what still gets through."] },
  { id: "blind", kicker: "Your Turn", title: "Hand Us Any Recording", image: PHOTOS.earthNight, tone: "black",
    text: "No metadata needed: the time is read back from the spacecraft's own clock.",
    render: () => <Blind />,
    notes: ["Analyse a held-out sample: the hidden truth appears after the analysis.", "Or drop the jury's file."] },
];

function Hero({ ch, d, globe }: { ch: Chapter; d: DemoData; globe: boolean }) {
  const det = d.detail.data;
  return (
    <div className="hds-cover-wrapper width-full maxw-full bg-carbon-black color-spacesuit-white color-mode-dark deck-hero">
      <div className="hds-foreground-wrapper display-flex flex-column z-400 deck-hero">
        <div className="grid-container grid-container-block margin-top-auto width-full padding-x-3 padding-y-6">
          <h3 className="label color-nasa-red margin-bottom-2">{ch.kicker}</h3>
          <h1 className="display-72 margin-0 color-spacesuit-white">{ch.title}</h1>
          <p className="p-lg maxw-tablet margin-top-2 margin-bottom-0 color-spacesuit-white">{ch.text}</p>
        </div>
      </div>
      <div className="skrim-overlay skrim-left mobile-skrim-top z-200" />
      <figure className="hds-media-background">
        {globe && det
          ? <Globe orbit={det.orbit} pass={det.geometry} station={{ lat: det.record.station_lat, lon: det.record.station_lng }} playhead={0.5} unix={Date.parse(det.record.start) / 1000} />
          : <img alt="" src={ch.image} style={{ objectFit: "cover" }} />}
      </figure>
    </div>
  );
}

export default function DemoPage() {
  const d = useDemoData();
  const [i, setI] = useState(0);
  const [notes, setNotes] = useState(false);
  const [grid, setGrid] = useState(false);

  useEffect(() => {
    const k = CHAPTERS.findIndex(c => `#${c.id}` === window.location.hash);
    if (k >= 0) setI(k);
  }, []);
  const go = useCallback((n: number) => {
    const k = Math.min(CHAPTERS.length - 1, Math.max(0, n));
    setI(k);
    setGrid(false);
    window.history.replaceState(null, "", `#${CHAPTERS[k].id}`);
    document.getElementById("demo-stage")?.scrollTo({ top: 0 });
  }, []);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (["INPUT", "SELECT", "TEXTAREA", "BUTTON", "A"].includes(el.tagName) || el.getAttribute("role") === "slider" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === " ") { e.preventDefault(); go(i + 1); }
      else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); go(i - 1); }
      else if (e.key.toLowerCase() === "n") setNotes(v => !v);
      else if (e.key.toLowerCase() === "g") setGrid(v => !v);
      else if (e.key === "Escape") { setGrid(false); setNotes(false); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [i, go]);

  const ch = CHAPTERS[i];
  return (
    <div className="deck bg-carbon-black color-spacesuit-white">
      <div className="deck-head">
        <Header />
        <span className="deck-progress" style={{ width: `${((i + 1) / CHAPTERS.length) * 100}%` }} />
      </div>

      <main id="demo-stage" className="deck-stage">
        <div key={ch.id} className="deck-chapter">
          <Hero ch={ch} d={d} globe={i === 0} />
          <Module tone={ch.tone}>{ch.render(d)}</Module>
        </div>
      </main>

      {grid && (
        <div className="deck-grid" role="dialog" aria-label="Chapters">
          <div className="grid-container grid-container-extrawide padding-x-3 padding-y-6">
            <h2 className="section-heading-md color-spacesuit-white margin-top-0 margin-bottom-5">Chapters</h2>
            <div className="grid-row grid-gap-2">
              {CHAPTERS.map((c, k) => (
                <button key={c.id} type="button" className="tablet:grid-col-4 desktop:grid-col-3 margin-bottom-4 deck-card" onClick={() => go(k)} aria-current={k === i ? "step" : undefined}>
                  <div className="hds-cover-wrapper cover-hover-zoom bg-carbon-black" style={{ aspectRatio: "16 / 9" }}>
                    <figure className="hds-media-background"><img alt="" src={c.image} style={{ objectFit: "cover" }} /></figure>
                  </div>
                  <div className="label color-nasa-red margin-top-2 margin-bottom-1">{c.kicker}</div>
                  <span className="heading-18 color-spacesuit-white">{c.title}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {notes && (
        <aside className="demo-notes" aria-label="Speaker notes">
          <h3 className="heading-18 margin-0">Speaker Notes</h3>
          <ul>{ch.notes.map(n => <li key={n}>{n}</li>)}</ul>
        </aside>
      )}

      <nav className="demo-bar" aria-label="Demo chapters">
        <div className="grid-container grid-container-extrawide padding-x-3 display-flex flex-align-center" style={{ gap: "1.5rem" }}>
          <button type="button" className="demo-step" aria-label="Previous chapter" disabled={i === 0} onClick={() => go(i - 1)}><Arrow topic /></button>
          <span className="heading-16 demo-count">{i + 1} of {CHAPTERS.length}</span>
          <div className="demo-dots">
            {CHAPTERS.map((c, k) => <button key={c.id} type="button" aria-label={c.title} aria-current={k === i ? "step" : undefined}
              className={k === i ? "on" : k < i ? "done" : ""} onClick={() => go(k)} title={c.title} />)}
          </div>
          <button type="button" className="heading-16 demo-link" aria-pressed={grid} onClick={() => setGrid(!grid)}>Chapters</button>
          <button type="button" className="heading-16 demo-link" aria-pressed={notes} onClick={() => setNotes(!notes)}>Notes</button>
          {i < CHAPTERS.length - 1 && <span className="heading-16 demo-next">{CHAPTERS[i + 1].title}</span>}
          <button type="button" className="demo-step" aria-label="Next chapter" disabled={i === CHAPTERS.length - 1} onClick={() => go(i + 1)}><Arrow topic /></button>
        </div>
      </nav>
    </div>
  );
}
