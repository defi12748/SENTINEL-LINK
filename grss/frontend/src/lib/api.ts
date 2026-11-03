export const API = process.env.NEXT_PUBLIC_API ?? "/backend";

export type Decision = "ACCEPT" | "VERIFY" | "QUARANTINE";

export interface ObservationSummary {
  id: number;
  start: string;
  end: string;
  station: string;
  station_lat: number;
  station_lng: number;
  max_elevation: number | null;
  frames: number;
  satnogs_frames: number;
  waterfall_url: string | null;
  split: "train" | "held-out" | "?";
  tle: [string, string];
}

export interface GeoPoint {
  t: number; lat: number; lon: number; alt_km: number; el: number; az: number; range_km: number; doppler_hz: number;
}

export interface Frame {
  index: number;
  t_rec: number;
  t_utc: number;
  frame_type: number | null;
  sequence: number | null;
  position: number | null;
  probability: number;
  decision: Decision;
  evidence: Record<string, number>;
  battery_v: number | null;
  battery_temp_c: number | null;
  sha256: string;
}

export interface Tracks { t: number[]; carrier_hz: number[]; level_db: number[] }
export interface Spectrogram { png: string; f_min: number; f_max: number; duration_s: number }
export interface Alarm { start_s: number; end_s: number; peak_prob: number; freq_hz: number }
export interface InterferenceView {
  prob: number[]; centres_s: number[]; threshold: number; alarms: Alarm[]; detected_truth?: boolean; any_alarm_overlap?: boolean;
}
/** Duplicate-audio head: a later stretch that is a sample-for-sample copy of an earlier one. */
export interface TwinMatch { start_s: number; end_s: number; src_start_s: number; lag_s: number; ncc: number; blocks: number }
export interface TwinTrace {
  block_t: number[]; block_ncc: number[]; threshold: number; block_s: number; ms: number;
  expected?: boolean; detected_truth?: boolean;
}
export interface ClockLine { t_rec: number[]; position: number[]; period_s: number }

export interface ObservationDetail {
  record: {
    observation_id: number; start: string; end: string; station_name: string; station_lat: number;
    station_lng: number; station_alt: number; frequency_hz: number; mode: string; tle1: string; tle2: string;
    max_altitude: number | null; audio_sha256: string;
  };
  split: string;
  geometry: GeoPoint[];
  orbit: GeoPoint[];
  frames: Frame[];
  tracks: Tracks;
  clock: ClockLine;
  spectrogram: Spectrogram;
  f_offset_hz: number;
  interference: InterferenceView;
}

export interface Overrides {
  replay?: boolean; sequence?: boolean; interference?: boolean;
  n_replay?: number; seq_variant?: "duplicate" | "swap";
  jam_kind?: "cw" | "nbnoise" | "chirp" | "pulsed"; jam_freq_hz?: number; js_db?: number;
}

export interface ScenarioResult {
  cache?: { status: "miss" | "memory" | "disk"; key: string; elapsed_ms: number };
  run_id: string;
  truth: {
    variant: string; seed: number; observation_id: number;
    replay?: { n_frames: number; dst_start_s: number; dst_end_s: number; src_start_s: number; cross_pass: boolean };
    sequence?: { variant: string; dst_start_s: number; dst_end_s: number };
    interference?: { kind: string; freq_hz: number; js_db: number; jn_db: number; start_s: number; dur_s: number };
  };
  labels: boolean[];
  label_kind: string[];
  frames: Frame[];
  tracks: Tracks;
  clock: ClockLine;
  spectrogram: Spectrogram;
  interference: InterferenceView;
  manifest: { authentic: boolean; signature_valid: boolean; tampered_intervals: [number, number][]; merkle_root: string };
  duplicates?: TwinMatch[];
  duplicate_trace?: TwinTrace;
  score: { tp: number; fp: number; fn: number; frames: number };
  timing_ms: Record<string, number>;
  ledger_head: string;
  ledger_refs: Record<string, { entry: number; hash: string }>;
  onair: OnAir;
  manifest_root: string;
  duration_s: number;
}

export interface OnAirFrame {
  t_rec: number; status: string; confidence: number; faulting: string[];
  clock: { residual_frames?: number; status?: string; behind_clock?: boolean };
}
export interface OnAir { available: boolean; ms?: number; frames?: OnAirFrame[]; path?: string }
export interface OnAirDemo {
  available: boolean; limits: Record<string, number[]>; clean: OnAir; attacked: OnAir;
  labels: boolean[]; label_kind: string[]; truth: ScenarioResult["truth"];
}

export interface SdlsDemo {
  service: string; overhead_bytes: number; verify_us_per_frame: number;
  stats: Record<string, number>;
  log: { step: string; frame: number; arsn: number | null; verdict: string }[];
}

export interface LedgerView {
  verification: { valid: boolean; entries: number; checkpoints: number; first_broken: number | null; reason: string | null };
  head: string;
  entries: { index: number; kind: string; hash: string; prev: string; time: number; data: Record<string, unknown> }[];
  public_key: string;
}

export interface UploadResult {
  run_id: string; file: string; duration_s: number; absolute_time: "given" | "inferred" | "unknown";
  frames: Frame[]; tracks: Tracks; clock: ClockLine; spectrogram: Spectrogram; f_offset_hz: number;
  interference: InterferenceView;
  response: { chosen: string; frames_decoded: Record<string, number> };
  missing: { position: number; frame_type: number; expected_t_rec: number; under_interference: boolean }[];
  duplicates?: TwinMatch[];
  duplicate_trace?: TwinTrace;
  timing_ms: Record<string, number>;
  ledger_head: string;
}

export interface Interop {
  available: boolean; hint?: string; library?: string; frames?: number; byte_identical?: boolean; nasa_apply_ms?: number;
  anatomy?: { field: string; bytes: string }[];
  checks?: { test: string; nasa: string; sentinel: string; ok: boolean; note?: string }[];
}

export type SampleResult = UploadResult & { truth: ScenarioResult["truth"] };

// The benchmark JSON is large; components read the parts they need.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Benchmark = any;

const reads = new Map<string, { expires: number; value: Promise<unknown> }>();

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

// Deterministic results: recordings, docs, the benchmark, NASA module runs, blind
// samples and attack scenarios (same pass, seed and parameters give the same
// analysis). Kept for the browser session so navigating back is instant.
const REUSABLE = /^\/api\/(observations(?:\/\d+)?|benchmark|docs\/[^/]+|onair\/demo|cryptolib\/interop|analyse\/sample\?seed=\d+|scenario)$/;
const SESSION_MS = 30 * 60_000;

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method ?? "GET";
  const reusable = REUSABLE.test(path) && (method === "GET" || path === "/api/scenario");
  if (!reusable) return fetchJson<T>(path, init);
  const key = `${method} ${path} ${init?.body ?? ""}`;
  const cached = reads.get(key);
  if (cached && cached.expires > Date.now()) return structuredClone(await cached.value) as T;
  const value = fetchJson<T>(path, init);
  const entry = { expires: Number.POSITIVE_INFINITY, value };
  reads.delete(key);
  reads.set(key, entry);
  while (reads.size > 48) reads.delete(reads.keys().next().value!);
  try {
    const result = await value;
    entry.expires = Date.now() + SESSION_MS;
    return structuredClone(result);
  } catch (error) {
    if (reads.get(key) === entry) reads.delete(key);
    throw error;
  }
}

export const api = {
  health: () => req<{ models: boolean; gr_satellites: boolean; observations: number; station_public_key: string }>("/api/health"),
  observations: () => req<ObservationSummary[]>("/api/observations"),
  observation: (id: number) => req<ObservationDetail>(`/api/observations/${id}`),
  scenario: (observation_id: number, seed: number, variant: string, overrides?: Overrides) =>
    req<ScenarioResult>("/api/scenario", { method: "POST", body: JSON.stringify({ observation_id, seed, variant, overrides }) }),
  benchmark: () => req<Benchmark>("/api/benchmark"),
  sdls: (observation_id: number, service: "AUTH" | "AUTH_ENC") =>
    req<SdlsDemo>("/api/sdls/demo", { method: "POST", body: JSON.stringify({ observation_id, service }) }),
  ledger: (limit = 40) => req<LedgerView>(`/api/ledger?limit=${limit}`),
  interop: () => req<Interop>("/api/cryptolib/interop"),
  onairDemo: () => req<OnAirDemo>("/api/onair/demo"),
  sample: (seed: number) => req<SampleResult>(`/api/analyse/sample?seed=${seed}`),
  doc: (slug: string) => req<{ slug: string; markdown: string }>(`/api/docs/${slug}`),
  analyse: async (file: File, start?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (start) fd.append("start", start);
    const r = await fetch(`${API}/api/analyse`, { method: "POST", body: fd });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return (await r.json()) as UploadResult;
  },
  tamper: (index: number) =>
    req<{ tampered_index: number; verification: LedgerView["verification"] }>(`/api/ledger/tamper?index=${index}`, { method: "POST" }),
};

export const fmtUtc = (iso: string) => iso.replace("T", " ").replace("Z", " UTC");
