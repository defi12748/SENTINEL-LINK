"use client";

import { useEffect, useState } from "react";
import {
  api, type Benchmark, type Interop, type ObservationDetail, type ObservationSummary, type Overrides, type ScenarioResult,
} from "@/lib/api";
import { DEMO } from "../AttackLab";

/* Every chapter of the live demo reads real API output. The runs are the
   Attack Lab's opening draw plus two single-attack variants of the same pass,
   so each piece of evidence can be shown on its own. */
export const REPLAY_ONLY: Overrides = { sequence: false, interference: false };
export const JAM_ONLY: Overrides = { replay: false, sequence: false, jam_kind: "cw", js_db: -3, jam_freq_hz: 13500 };

type Health = Awaited<ReturnType<typeof api.health>>;
export interface Slot<T> { data: T | null; error: string | null }

export interface DemoData {
  health: Slot<Health>;
  obs: Slot<ObservationSummary[]>;
  bench: Slot<Benchmark>;
  interop: Slot<Interop>;
  detail: Slot<ObservationDetail>;
  run: Slot<ScenarioResult>;
  replay: Slot<ScenarioResult>;
  jam: Slot<ScenarioResult>;
}

function useSlot<T>(load: () => Promise<T>): Slot<T> {
  const [slot, setSlot] = useState<Slot<T>>({ data: null, error: null });
  useEffect(() => {
    let alive = true;
    load().then(data => alive && setSlot({ data, error: null })).catch(e => alive && setSlot({ data: null, error: String(e) }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return slot;
}

export function useDemoData(): DemoData {
  return {
    health: useSlot(api.health),
    obs: useSlot(api.observations),
    bench: useSlot(api.benchmark),
    interop: useSlot(api.interop),
    detail: useSlot(() => api.observation(DEMO.observation)),
    run: useSlot(() => api.scenario(DEMO.observation, DEMO.seed, "standard")),
    replay: useSlot(() => api.scenario(DEMO.observation, DEMO.seed, "standard", REPLAY_ONLY)),
    jam: useSlot(() => api.scenario(DEMO.observation, DEMO.seed, "standard", JAM_ONLY)),
  };
}

/** Animate a number from 0 to `to` once it is known. */
export function useCountUp(to: number | null | undefined, ms = 1400): number {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (to === null || to === undefined) return;
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / ms);
      setV(to * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [to, ms]);
  return v;
}

/** Frame-counter residual against the clock line, relative to the pass's own accepted frames. */
export function clockLag(run: ScenarioResult): { lag: number; seconds: number } {
  const [p0, p1] = run.clock.position;
  const dur = run.clock.t_rec[1];
  const res = run.frames.filter(f => f.position !== null)
    .map(f => ({ f, r: (f.position as number) - (p0 + ((p1 - p0) * f.t_rec) / dur) }));
  const ok = res.filter(x => x.f.decision === "ACCEPT").map(x => x.r).sort((a, b) => a - b);
  const base = ok.length ? ok[Math.floor(ok.length / 2)] : 0;
  const worst = res.filter(x => x.f.decision === "QUARANTINE").reduce((m, x) => Math.min(m, x.r - base), 0);
  return { lag: Math.round(-worst), seconds: Math.round(-worst * run.clock.period_s) };
}
