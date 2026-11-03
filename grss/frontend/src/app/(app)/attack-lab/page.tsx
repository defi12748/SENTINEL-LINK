"use client";

import { AttackLab } from "@/components/AttackLab";
import { HeldOutPanel } from "@/components/HeldOutPanel";
import { Module, SectionHead } from "@/components/hds";
import { api, type ObservationSummary } from "@/lib/api";
import { useApi } from "@/lib/hooks";

export default function AttackLabPage() {
  const { data: obs, error } = useApi<ObservationSummary[]>(api.observations);
  return (
    <>
      <Module tone="dark">
        <div className="lab-title"><div><span className="label red">Sentinel Link / Observatory</span><h1 className="display-48">Attack Lab</h1></div><a href="#upload" className="lab-upload-link">Analyse a recording ↗</a></div>
        {error && <p role="alert" className="red">Could not load recordings: {error}</p>}
        {!obs && !error && <p role="status" className="mono muted">Loading recordings…</p>}
        <AttackLab observations={obs ?? []} selectedId={null} onResult={() => undefined} autoRun />
      </Module>
      <Module id="upload" tone="black">
        <SectionHead title="Analyse Your Own Recording" />
        <HeldOutPanel />
      </Module>
    </>
  );
}
