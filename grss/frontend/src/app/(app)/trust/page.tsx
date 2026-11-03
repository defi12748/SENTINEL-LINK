"use client";

import { CryptoLibPanel } from "@/components/CryptoLibPanel";
import { Module, PageIntro, SectionHead } from "@/components/hds";
import { TrustPanel } from "@/components/TrustPanel";
import { api, type ObservationSummary } from "@/lib/api";
import { PHOTOS, useApi } from "@/lib/hooks";

const LAYERS: [string, string, string][] = [
  ["Authenticated link", "CCSDS SDLS: SPI, anti-replay sequence number, 128-bit MAC", "Replay and injection rejected"],
  ["Stored recording", "Ed25519-signed per-second Merkle manifest", "Edits found to the second"],
  ["Legacy downlink", "Clock, Doppler, telemetry and spectrum evidence", "Attacks detected, calibrated"],
  ["Every decision", "SHA-256 hash chain, signed checkpoints", "Tamper-evident audit trail"],
];

export default function TrustPage() {
  const { data: obs } = useApi<ObservationSummary[]>(api.observations);
  const lead = (obs ?? []).filter(o => o.split === "held-out").sort((a, b) => b.frames - a.frames)[0];
  return (
    <>
      <PageIntro kicker="Trust Anchor · NASA CryptoLib" title="Cryptography Where It Can" image={PHOTOS.dsnNew}
        text="Physics where it can't. Our space-link security runs side by side with NASA's own CryptoLib, live, on real AO-73 frames." />
      <Module tone="light">
        <SectionHead title="NASA CryptoLib, Live" />
        <CryptoLibPanel />
      </Module>
      <Module tone="dark">
        <SectionHead title="Attack the Secure Link" />
        <TrustPanel observationId={lead?.id ?? null} />
      </Module>
      <Module tone="grey">
        <SectionHead title="Four Layers" />
        <div className="grid-row grid-gap-4">
          {LAYERS.map(([t, how, what], i) => (
            <div key={t} className="tablet:grid-col-6 desktop:grid-col-3 margin-bottom-4" style={{ borderTop: "3px solid #000", paddingTop: "1.25rem" }}>
              <div className="label color-nasa-red margin-bottom-2">0{i + 1}</div>
              <h3 className="heading-22 margin-bottom-2">{t}</h3>
              <p className="p-sm margin-0">{how}</p>
              <p className="label color-carbon-60 margin-top-2">{what}</p>
            </div>
          ))}
        </div>
      </Module>
    </>
  );
}
