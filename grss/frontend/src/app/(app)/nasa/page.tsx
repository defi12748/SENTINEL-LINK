"use client";

import { CryptoLibPanel } from "@/components/CryptoLibPanel";
import { Module, PageIntro, SectionHead } from "@/components/hds";
import { OnAirPanel } from "@/components/OnAirPanel";
import { PHOTOS } from "@/lib/photos";

const MODULES = [
  { name: "OnAIR", org: "NASA GSFC · On-board AI Research platform", role: "Runs on every decoded pass: its telemetry test suite plus our clock plugin.", where: "NOS3 components/onair" },
  { name: "CryptoLib", org: "NASA · CCSDS Space Data Link Security", role: "Reference for our secure link: byte-identical frames, cross-verified live.", where: "NOS3 components/cryptolib" },
];

export default function NasaPage() {
  return (
    <>
      <PageIntro kicker="NASA Open-Source Modules · from NOS3" title="Built On NASA Flight Software" image={PHOTOS.missionControl}
        text="Two NASA modules from the NOS3 simulator run inside Sentinel Link, on real AO-73 data, live." />
      <Module tone="light">
        <div className="grid-row grid-gap-4">
          {MODULES.map(m => (
            <div key={m.name} className="desktop:grid-col-6 margin-bottom-4" style={{ borderTop: "3px solid #000", paddingTop: "1.25rem" }}>
              <div className="label color-nasa-red margin-bottom-2">{m.where}</div>
              <h3 className="display-48 margin-0">{m.name}</h3>
              <p className="heading-18 margin-top-2 margin-bottom-1">{m.org}</p>
              <p className="p-md margin-0">{m.role}</p>
            </div>
          ))}
        </div>
      </Module>
      <Module tone="dark">
        <SectionHead title="NASA OnAIR, Live" />
        <OnAirPanel />
      </Module>
      <Module tone="light">
        <SectionHead title="NASA CryptoLib, Live" />
        <CryptoLibPanel />
      </Module>
    </>
  );
}
