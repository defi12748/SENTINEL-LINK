"use client";

import { api, type Interop } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const FIELD_COLOR = ["#2e2e32", "#1c67e3", "#288bff", "#444447", "#f64137", "#58585b"];

/** NASA CryptoLib run live against our SDLS implementation on real AO-73 frames. */
export function CryptoLibPanel() {
  const { data, error } = useApi<Interop>(api.interop);
  if (error) return <p className="mono red">{error}</p>;
  if (!data) return <div className="display-flex flex-align-center" style={{ gap: ".75rem" }}><span className="spinner" /><span className="label">Running NASA CryptoLib…</span></div>;
  if (!data.available) return <p className="p-md">CryptoLib bridge not built on this machine. Build it with <code>{data.hint}</code>.</p>;
  const total = data.anatomy!.reduce((a, f) => a + f.bytes.length / 2, 0);
  return (
    <div style={{ display: "grid", gap: "2.5rem" }}>
      <div className="grid-row grid-gap-4">
        <div className="desktop:grid-col-4 margin-bottom-3">
          <div className="label color-carbon-60 margin-bottom-1">Library</div>
          <div className="heading-18">{data.library}</div>
        </div>
        <div className="desktop:grid-col-4 margin-bottom-3">
          <div className="label color-carbon-60 margin-bottom-1">Frames protected by both</div>
          <div className="heading-18">{data.frames} real AO-73 frames</div>
        </div>
        <div className="desktop:grid-col-4 margin-bottom-3">
          <div className="label color-carbon-60 margin-bottom-1">Output comparison</div>
          <div className="heading-18" style={{ color: data.byte_identical ? "#1a7f45" : "var(--nasa-red)" }}>
            {data.byte_identical ? "Byte-identical" : "Different"}
          </div>
        </div>
      </div>

      <div>
        <h3 className="heading-22 margin-bottom-2">One protected frame, field by field</h3>
        <div style={{ display: "flex", height: 44, width: "100%" }}>
          {data.anatomy!.map((f, i) => (
            <div key={f.field} title={`${f.field}: ${f.bytes.length / 2} bytes`}
              style={{ flex: `${Math.max(f.bytes.length / 2, 6) / total}`, background: FIELD_COLOR[i], borderRight: "2px solid #fff" }} />
          ))}
        </div>
        <div className="scroll-x margin-top-2">
          <table className="data" style={{ color: "#17171b" }}>
            <thead><tr><th>Field</th><th>Bytes</th><th>Value (hex)</th></tr></thead>
            <tbody>
              {data.anatomy!.map((f, i) => (
                <tr key={f.field}>
                  <td><span style={{ display: "inline-block", width: 10, height: 10, background: FIELD_COLOR[i], marginRight: 8 }} />{f.field}</td>
                  <td>{f.bytes.length / 2}</td>
                  <td>{f.bytes.length > 48 ? `${f.bytes.slice(0, 48)}…` : f.bytes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h3 className="heading-22 margin-bottom-2">Same attacks, two receivers</h3>
        <div className="scroll-x">
          <table className="data" style={{ color: "#17171b" }}>
            <thead><tr><th>Test</th><th>NASA CryptoLib</th><th>Sentinel Link</th><th>Result</th></tr></thead>
            <tbody>
              {data.checks!.map(c => (
                <tr key={c.test}>
                  <td style={{ whiteSpace: "normal" }}>{c.test}{c.note && <div className="label color-carbon-60 margin-top-05">{c.note}</div>}</td>
                  <td style={{ color: c.nasa === "ACCEPTED" ? "var(--nasa-red)" : undefined, fontWeight: c.nasa === "ACCEPTED" ? 700 : 400 }}>{c.nasa}</td>
                  <td>{c.sentinel}</td>
                  <td style={{ color: c.ok ? "#1a7f45" : "var(--nasa-red)", fontWeight: 700 }}>{c.ok ? "PASS" : "FAIL"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
