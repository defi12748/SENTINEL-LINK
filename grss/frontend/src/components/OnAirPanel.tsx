"use client";

import { api, type OnAir, type OnAirDemo } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const C = { GREEN: "#288bff", YELLOW: "#ffc83d", RED: "#f64137", "---": "#444447" } as Record<string, string>;

function Strip({ title, cells }: { title: string; cells: { color: string; tip: string }[] }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "230px 1fr", gap: "1rem", alignItems: "center", marginBottom: 6 }}>
      <span className="label" style={{ color: "var(--carbon-20)" }}>{title}</span>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.max(1, cells.length)}, minmax(3px, 1fr))`, gap: 2 }}>
        {cells.map((c, i) => <div key={i} title={c.tip} style={{ height: 22, background: c.color }} />)}
      </div>
    </div>
  );
}

function Run({ title, run, labels }: { title: string; run: OnAir; labels?: boolean[] }) {
  const fr = run.frames ?? [];
  const red = fr.filter(f => f.clock.status === "RED").length;
  const green = fr.filter(f => f.status === "GREEN").length;
  return (
    <div style={{ marginBottom: "2.5rem" }}>
      <div className="display-flex flex-align-end margin-bottom-2" style={{ justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
        <h3 className="heading-22 margin-0">{title}</h3>
        <span className="label" style={{ color: "var(--carbon-40)" }}>{fr.length} frames · OnAIR {run.ms} ms</span>
      </div>
      <Strip title="OnAIR limit checks" cells={fr.map(f => ({ color: C[f.status] ?? C["---"], tip: `t=${f.t_rec.toFixed(1)} s · ${f.status}` }))} />
      <Strip title="Sentinel clock plugin in OnAIR" cells={fr.map(f => ({ color: C[f.clock.status ?? "---"], tip: `t=${f.t_rec.toFixed(1)} s · residual ${f.clock.residual_frames} frames` }))} />
      {labels && <Strip title="Hidden ground truth" cells={labels.map(l => ({ color: l ? "#ffffff" : "#2e2e32", tip: l ? "attacked" : "genuine" }))} />}
      <p className="p-md margin-top-2" style={{ color: "#fff" }}>
        Limit checks: <b>{green}/{fr.length} GREEN</b>. Clock plugin: <b style={{ color: red ? "#ff6a5f" : "var(--ok)" }}>{red} RED</b>
        {labels && <> · ground truth: {labels.filter(Boolean).length} attacked frames</>}.
      </p>
    </div>
  );
}

export function OnAirPanel() {
  const { data, error } = useApi<OnAirDemo>(api.onairDemo);
  if (error) return <p className="mono red">{error}</p>;
  if (!data) return <div className="display-flex flex-align-center" style={{ gap: ".75rem" }}><span className="spinner" /><span className="label">Streaming passes through NASA OnAIR…</span></div>;
  if (!data.available) return <p className="p-md">NASA OnAIR not found. Set <code>SENTINEL_ONAIR_PATH</code> to an OnAIR checkout.</p>;
  const caught = (data.attacked.frames ?? []).filter((f, i) => data.labels[i] && f.clock.status === "RED").length;
  const fa = (data.attacked.frames ?? []).filter((f, i) => !data.labels[i] && f.clock.status === "RED").length;
  return (
    <div>
      <div style={{ borderLeft: "6px solid var(--nasa-red)", padding: "1rem 1.25rem", background: "#000", marginBottom: "2.5rem" }}>
        <div className="label" style={{ color: "var(--nasa-red)" }}>Plausible-looking data may still be untrustworthy</div>
        <p className="heading-22 margin-top-1 margin-bottom-0" style={{ color: "#fff" }}>
          OnAIR&apos;s physical-limit checks pass every replayed frame: the data is real, just old.
          The clock plugin we wrote for OnAIR catches {caught} of {data.labels.filter(Boolean).length} attacked frames with {fa} false alarms.
        </p>
      </div>
      <Run title="Clean pass" run={data.clean} />
      <Run title="Same pass after the standard attack" run={data.attacked} labels={data.labels} />
      <details>
        <summary className="label" style={{ cursor: "pointer", color: "var(--carbon-30)" }}>OnAIR FEASIBILITY limits learned from training passes</summary>
        <div className="scroll-x margin-top-2">
          <table className="data">
            <thead><tr><th>Channel</th><th>Red below</th><th>Green from</th><th>Green to</th><th>Red above</th></tr></thead>
            <tbody>
              {Object.entries(data.limits).map(([k, v]) => (
                <tr key={k}><td>{k}</td>{v.map((x, i) => <td key={i}>{x}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
