import type { Frame } from "@/lib/api";

/** Human-readable reason codes from a frame's evidence vector (thresholds in σ / frames). */
export function reasonCodes(f: Frame): { code: string; detail: string }[] {
  const e = f.evidence;
  const out: { code: string; detail: string }[] = [];
  const add = (cond: boolean, code: string, detail: string) => { if (cond) out.push({ code, detail }); };
  add((e.u_behind ?? 0) > 4, "COUNTER_BEHIND_CLOCK", `${(e.u_behind ?? 0).toFixed(1)}σ behind the spacecraft clock`);
  add((e.u_ahead ?? 0) > 4, "COUNTER_AHEAD_OF_CLOCK", `${(e.u_ahead ?? 0).toFixed(1)}σ ahead of the spacecraft clock`);
  add((e.duplicate ?? 0) > 0, "DUPLICATE_COUNTER", "Same on-board position seen twice in this pass");
  add((e.behind ?? 0) > 0, "COUNTER_REGRESSION", "Counter went backwards");
  add((e.step_err ?? 0) > 2, "COUNTER_TIME_MISMATCH", `Counter step and time step disagree by ${(e.step_err ?? 0).toFixed(1)} frames`);
  add((e.pass_offset_excess ?? 0) > 0, "PASS_FROM_ANOTHER_TIME", `Whole pass is ${(e.pass_offset_excess ?? 0).toFixed(0)} frames off the clock model`);
  add((e.tele_ecod_tail ?? 0) > 2.5, "TELEMETRY_OUTLIER", `Telemetry unlike its neighbours (p < 10^-${(e.tele_ecod_tail ?? 0).toFixed(1)})`);
  add((e.splice_carrier_step ?? 0) > 4, "CARRIER_STEP", `Doppler jumps ${(e.splice_carrier_step ?? 0).toFixed(1)}σ at the frame boundary`);
  add((e.carrier_offset ?? 0) > 4, "DOPPLER_OFF_TRACK", `Carrier ${(e.carrier_offset ?? 0).toFixed(1)}σ off the pass Doppler curve`);
  return out;
}
