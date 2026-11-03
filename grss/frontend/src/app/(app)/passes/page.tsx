"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Module, PageIntro } from "@/components/hds";
import { api, type ObservationSummary } from "@/lib/api";
import { PHOTOS, PHOTO_LIST, fmtDay, useApi } from "@/lib/hooks";

export default function PassesPage() {
  const { data: obs } = useApi<ObservationSummary[]>(api.observations);
  const [q, setQ] = useState("");
  const [split, setSplit] = useState<"all" | "held-out" | "train">("all");
  useEffect(() => { setQ(new URLSearchParams(window.location.search).get("q") ?? ""); }, []);
  const list = useMemo(() => (obs ?? []).filter(o =>
    (split === "all" || o.split === split) && (!q || o.station.toLowerCase().includes(q.toLowerCase()))), [obs, q, split]);

  return (
    <>
      <PageIntro kicker="SatNOGS Network · AO-73" title="Passes" image={PHOTOS.sentinel6}
        text="Thirty recordings of FUNcube-1 from five ground stations, decoded by our chain. Open one to see every frame and the station's own waterfall, then attack it." />
      <Module tone="light">
        <div className="grid-row flex-align-end margin-bottom-5" style={{ gap: "1.5rem" }}>
          <div className="field" style={{ minWidth: 260 }}>
            <label className="label" htmlFor="q">Station</label>
            <input id="q" className="usa-input" value={q} onChange={e => setQ(e.target.value)} placeholder="Search" style={{ marginTop: 0 }} />
          </div>
          <div className="display-flex" style={{ gap: ".5rem" }}>
            {(["all", "held-out", "train"] as const).map(s => (
              <button key={s} onClick={() => setSplit(s)} className={`usa-button ${split === s ? "bg-nasa-red" : "usa-button--outline"}`}
                style={{ margin: 0, textTransform: "capitalize" }}>{s === "all" ? "All" : s}</button>
            ))}
          </div>
          <span className="label color-carbon-60" style={{ marginLeft: "auto" }}>{list.length} Passes</span>
        </div>
        <div className="grid-row grid-gap-2">
          {list.map((o, i) => (
            <Link key={o.id} href={`/passes/${o.id}`} className="tablet:grid-col-6 desktop:grid-col-4 margin-bottom-4" style={{ textDecoration: "none", color: "inherit" }}>
              <div className="hds-cover-wrapper cover-hover-zoom bg-carbon-black color-mode-dark" style={{ aspectRatio: "16 / 10" }}>
                <div className="skrim-overlay skrim-overlay-dark skrim-left mobile-skrim-top padding-3 display-flex flex-column flex-align-start z-200">
                  <span className="label color-spacesuit-white margin-bottom-auto">{o.split === "held-out" ? "Held-Out" : "Training"}</span>
                  <span className="label color-spacesuit-white margin-bottom-1">{o.frames} Frames · Max {o.max_elevation?.toFixed(0) ?? "—"}°</span>
                  <span className="heading-22 color-spacesuit-white">{o.station}</span>
                </div>
                <figure className="hds-media-background"><img alt="" src={PHOTO_LIST[i % PHOTO_LIST.length]} style={{ objectFit: "cover" }} /></figure>
              </div>
              <div className="padding-top-1 label color-carbon-60">{fmtDay(o.start)} · {o.start.slice(11, 16)} UTC · #{o.id}</div>
            </Link>
          ))}
        </div>
      </Module>
    </>
  );
}
