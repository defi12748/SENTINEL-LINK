"use client";

import { Module, PageIntro, SectionHead } from "@/components/hds";
import { Results } from "@/components/Results";
import { api, type Benchmark } from "@/lib/api";
import { PHOTOS, useApi } from "@/lib/hooks";

export default function ResultsPage() {
  const { data: bench } = useApi<Benchmark>(api.benchmark);
  return (
    <>
      <PageIntro kicker="Held-Out Benchmark" title="By the Numbers" image={PHOTOS.missionControl}
        text="Trained on early passes. Measured on later dates and stations it never saw." />
      <Module tone="light">
        <SectionHead title="Results" />
        <Results bench={bench} />
        {bench && (
          <p className="label color-carbon-60 margin-top-6">
            Generated {bench.generated_utc} · {bench.dataset.held_out_observations.length} held-out observations
          </p>
        )}
      </Module>
    </>
  );
}
