import type { ReactNode } from "react";
import type { Decision } from "@/lib/api";

export function ArrowCircle() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <circle className="button-primary-circle" cx="16" cy="16" r="16" />
      <path d="M8 16.956h12.604l-3.844 4.106 1.252 1.338L24 16l-5.988-6.4-1.252 1.338 3.844 4.106H8v1.912z" className="color-spacesuit-white" />
    </svg>
  );
}

export function ButtonPrimary({ children, onClick, href, disabled }: {
  children: ReactNode; onClick?: () => void; href?: string; disabled?: boolean;
}) {
  if (href) {
    return <a className="button-primary" href={href}><span>{children}</span><ArrowCircle /></a>;
  }
  return (
    <button className="button-primary" onClick={onClick} disabled={disabled} style={{ background: "none", border: 0, cursor: "pointer", color: "inherit" }}>
      <span>{children}</span><ArrowCircle />
    </button>
  );
}

export function Label({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`label ${className}`}>{children}</div>;
}

export function DecisionChip({ d }: { d: Decision }) {
  return <span className={`chip ${d.toLowerCase()}`}>{d}</span>;
}

export const decisionColor: Record<Decision, string> = {
  // Status trio validated for CVD separation on black (dataviz validator, all pairs ΔE ≥ 18).
  ACCEPT: "#288bff",
  VERIFY: "#ffc83d",
  QUARANTINE: "#f64137",
};

export function Stat({ value, label, note }: { value: ReactNode; label: string; note?: ReactNode }) {
  return (
    <div style={{ display: "grid", gap: ".6rem", borderTop: "1px solid currentColor", paddingTop: "1rem" }}>
      <Label>{label}</Label>
      <div className="stat-value">{value}</div>
      {note && <div className="p-sm muted">{note}</div>}
    </div>
  );
}

export function pct(x: number | null | undefined, digits = 1) {
  return x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`;
}
