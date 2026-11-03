"use client";

import { useEffect, useState } from "react";
import { api, type LedgerView, type SdlsDemo } from "@/lib/api";
import { ButtonPrimary, Label } from "./ui";

const verdictColor = (v: string) => (v === "ACCEPT" ? "var(--ok)" : "var(--nasa-red)");

export function TrustPanel({ observationId }: { observationId: number | null }) {
  const [service, setService] = useState<"AUTH" | "AUTH_ENC">("AUTH");
  const [sdls, setSdls] = useState<SdlsDemo | null>(null);
  const [ledger, setLedger] = useState<LedgerView | null>(null);
  const [tamper, setTamper] = useState<{ tampered_index: number; verification: LedgerView["verification"] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const runSdls = async () => {
    if (observationId === null) return;
    setBusy(true); setErr(null);
    try { setSdls(await api.sdls(observationId, service)); } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  const loadLedger = async () => {
    setErr(null);
    try { setLedger(await api.ledger()); setTamper(null); } catch (e) { setErr(String(e)); }
  };
  const doTamper = async () => {
    if (!ledger || !ledger.entries.length) return;
    try { setTamper(await api.tamper(Math.floor(ledger.verification.entries / 2))); } catch (e) { setErr(String(e)); }
  };

  useEffect(() => {
    if (observationId === null) return;
    runSdls();
    loadLedger();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [observationId, service]);

  const attacks = sdls?.log.filter(l => l.step !== "downlink") ?? [];
  const downlink = sdls?.log.filter(l => l.step === "downlink") ?? [];

  return (
    <div style={{ display: "grid", gap: "3rem", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 460px), 1fr))" }}>
      <div style={{ display: "grid", gap: "1.25rem", alignContent: "start" }}>
        <h3 className="heading-29">CCSDS SDLS</h3>
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center" }}>
          <div className="field" style={{ minWidth: 220 }}>
            <Label>Service</Label>
            <select value={service} onChange={e => setService(e.target.value as "AUTH" | "AUTH_ENC")}>
              <option value="AUTH">Authentication (HMAC-SHA-256/128)</option>
              <option value="AUTH_ENC">Authenticated encryption (AES-256-GCM)</option>
            </select>
          </div>
          <ButtonPrimary onClick={runSdls} disabled={busy || observationId === null}>Protect and Attack</ButtonPrimary>
        </div>
        {sdls && (
          <div style={{ display: "grid", gap: "1rem" }}>
            <div className="mono p-sm">
              {downlink.length} genuine frames → {downlink.filter(l => l.verdict === "ACCEPT").length} accepted ·
              overhead {sdls.overhead_bytes} B/frame ({((sdls.overhead_bytes / 256) * 100).toFixed(1)}%) ·
              verify {sdls.verify_us_per_frame} µs/frame
            </div>
            <div className="scroll-x">
              <table className="data">
                <thead><tr><th>Attack</th><th>Frame</th><th>ARSN</th><th>Receiver verdict</th></tr></thead>
                <tbody>
                  {attacks.map((l, i) => (
                    <tr key={i}>
                      <td>{l.step}</td><td>{l.frame}</td><td>{l.arsn ?? "—"}</td>
                      <td style={{ color: verdictColor(l.verdict) }}>{l.verdict}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      <div style={{ display: "grid", gap: "1.25rem", alignContent: "start" }}>
        <h3 className="heading-29">Signed Ledger</h3>
        <div style={{ display: "flex", gap: "2rem", flexWrap: "wrap" }}>
          <ButtonPrimary onClick={loadLedger}>Verify</ButtonPrimary>
          <ButtonPrimary onClick={doTamper} disabled={!ledger?.entries.length}>Tamper</ButtonPrimary>
        </div>
        {ledger && (
          <div style={{ display: "grid", gap: ".75rem" }}>
            <div className="mono p-sm" style={{ color: ledger.verification.valid ? "var(--ok)" : "var(--nasa-red)" }}>
              {ledger.verification.valid ? "CHAIN VALID" : `BROKEN at ${ledger.verification.first_broken}`} ·
              {" "}{ledger.verification.entries} entries · {ledger.verification.checkpoints} signed checkpoints
            </div>
            {tamper && (
              <div className="mono p-sm" style={{ color: tamper.verification.valid ? "var(--ok)" : "var(--nasa-red)" }}>
                Copy with entry {tamper.tampered_index} rewritten → {tamper.verification.valid ? "valid (unexpected)" :
                  `rejected at entry ${tamper.verification.first_broken}: ${tamper.verification.reason}`}
              </div>
            )}
            <div style={{ display: "grid", gap: 6, maxHeight: 280, overflow: "auto" }}>
              {ledger.entries.slice().reverse().map(e => (
                <div key={e.index} style={{ display: "grid", gridTemplateColumns: "48px 90px 1fr", gap: ".75rem",
                  padding: ".5rem .6rem", border: "1px solid var(--carbon-10)", fontFamily: "var(--font-label)", fontSize: ".72rem" }}>
                  <span>#{e.index}</span><span style={{ color: e.kind === "checkpoint" ? "var(--nasa-blue)" : undefined }}>{e.kind}</span>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.hash}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      {err && <div className="mono red" style={{ gridColumn: "1 / -1" }}>{err}</div>}
    </div>
  );
}
