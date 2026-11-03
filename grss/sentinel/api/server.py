"""SENTINEL-LINK HTTP API (FastAPI). Every response is computed by the real
pipeline on real SatNOGS data; nothing here is simulated in the browser.

    py -m uvicorn sentinel.api.server:app --port 8000
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import threading
import time
from uuid import uuid4
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from scipy.signal import stft

from .. import PACKAGE_ROOT, PROJECT_ROOT, RESULTS_ROOT
from .. import db as db_mod
from ..cache import ResultCache, cache_key, fingerprint
from ..data.corpus import corpus_root, iso_to_unix, load_pass
from ..decode import grsat
from ..detect import twin
from ..dsp.audio import load_audio
from ..geo import pass_geometry
from ..pipeline import analyse_pass, analyse_recording, flag_duplicates
from ..redteam import scenario
from ..train import MODEL_PATH, load_models
from ..trust import ledger as ledger_mod
from ..trust.manifest import StationKey, canonical_json, create_manifest, verify_manifest
from ..trust.sdls import KeyStore, SdlsEndpoint, SecurityAssociation, Service

app = FastAPI(title="SENTINEL-LINK", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ROOT = corpus_root()
# With a database the ledger outlives the process, so its checkpoints need a station key that does too.
if db_mod.database_url():
    from ..ledger_store import station_key
    STATION_KEY = station_key()
else:
    STATION_KEY = StationKey.generate()      # this ground station's signing key (per server run)
LEDGER, DB = db_mod.open_store(STATION_KEY, checkpoint_every=32)
CACHE = ResultCache(Path(os.environ.get("SENTINEL_CACHE_DIR", RESULTS_ROOT / "api-cache")))
COMPUTE_LOCK = threading.RLock()  # matplotlib and NASA OnAIR use process-global state
AUDIT_LOCK = threading.RLock()


def _analysis_key(kind: str, params: dict, directories: list[Path]) -> str:
    from ..nasa import onair_bridge
    files = [MODEL_PATH, *(p for p in PACKAGE_ROOT.rglob("*.py")
                           if "bench" not in p.relative_to(PACKAGE_ROOT).parts)]
    for d in directories:
        files.extend(d / name for name in ("audio.ogg", "record.json", "decoded.json", "tracks.npz"))
    # OnAIR learns limits from the training corpus. Changing that corpus also invalidates results.
    files.extend(ROOT.glob("obs_*/record.json"))
    files.extend(ROOT.glob("obs_*/decoded.json"))
    onair = onair_bridge.onair_path()
    if onair:
        files.extend(onair.rglob("*.py"))
    return cache_key(kind, params, files)


def _cached(key: str, compute) -> tuple[dict, dict]:
    def locked():
        with COMPUTE_LOCK:
            return compute()
    return CACHE.get_or_compute(key, locked)


def _log_run(run_id: str, kind: str, metadata: dict, frames: list[dict], **run_fields) -> dict:
    """Ledger entries for a run and its non-accepted frames; with a database, the run and every frame
    decision are written in the same transaction, so the tables and the chain cannot disagree."""
    with AUDIT_LOCK, LEDGER.transaction() as cur:
        LEDGER.append("run", {"run": run_id, **metadata})
        refs = {}
        for frame in frames:
            if frame["decision"] != "ACCEPT":
                entry = LEDGER.append("frame", {"run": run_id, "index": frame["index"],
                    "sha256": frame["sha256"], "decision": frame["decision"], "p": frame["probability"]})
                refs[str(frame["index"])] = {"entry": entry["index"], "hash": entry["hash"]}
        if cur is not None:
            DB.record_run(cur, run_id, kind, frames, refs, LEDGER.head, metadata, **run_fields)
        return refs


def _audit(result: dict, prefix: str, metadata: dict) -> dict:
    result["run_id"] = f"{prefix}-{uuid4().hex}"
    result["ledger_refs"] = _log_run(result["run_id"], metadata.get("variant", prefix), metadata, result["frames"],
                                    observation_id=metadata.get("observation"))
    result["ledger_head"] = LEDGER.head
    return result


def models():
    return _models(fingerprint(MODEL_PATH))


@lru_cache(maxsize=1)
def _models(version: str):
    if not MODEL_PATH.exists():
        raise HTTPException(503, "models not trained: run `py -m sentinel.train`")
    return load_models()


def _obs_dir(oid: int) -> Path:
    d = ROOT / f"obs_{oid}"
    if not (d / "decoded.json").exists():
        raise HTTPException(404, f"observation {oid} not in corpus")
    return d


def _split() -> dict[str, str]:
    train, test = scenario.split()
    return {d.name: "train" for d in train} | {d.name: "held-out" for d in test}


def _record(d: Path) -> dict:
    return json.loads((d / "record.json").read_text(encoding="utf-8"))


def spectrogram_png(x: np.ndarray, fs: int, fc: float, span_hz: float = 2500.0, cols: int = 720) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import cm, colors
    from matplotlib.image import imsave

    f, _, Z = stft(x, fs=fs, nperseg=2048, noverlap=0, boundary=None, padded=False)
    sel = np.abs(f - fc) <= span_hz
    P = np.abs(Z[sel]) ** 2
    g = max(1, P.shape[1] // cols)
    P = P[:, : P.shape[1] // g * g].reshape(P.shape[0], -1, g).mean(axis=2)
    db = 10 * np.log10(P + 1e-20)
    lo, hi = np.percentile(db, 5), np.percentile(db, 99.7)
    cmap = colors.LinearSegmentedColormap.from_list(
        "nasa", ["#000000", "#0b1d3a", "#1c67e3", "#8fb8ff", "#ffffff"])
    img = cmap(np.clip((db - lo) / (hi - lo + 1e-9), 0, 1))[::-1]
    buf = io.BytesIO()
    imsave(buf, img, format="png")
    return {"png": base64.b64encode(buf.getvalue()).decode(), "f_min": float(f[sel][0]),
            "f_max": float(f[sel][-1]), "duration_s": len(x) / fs}


def _frames_json(reports) -> list[dict]:
    return [{
        "index": r.index, "t_rec": round(r.t_rec, 3), "t_utc": r.t_utc, "frame_type": r.frame_type,
        "sequence": r.sequence, "position": r.position, "probability": round(r.probability, 4),
        "decision": r.decision, "evidence": {k: round(v, 3) for k, v in r.evidence.items()},
        "battery_v": r.telemetry.get("battery_voltage_mv", 0) / 1000 if r.telemetry else None,
        "battery_temp_c": r.telemetry.get("battery_temp_c") if r.telemetry else None,
        "sha256": r.sha256,
    } for r in reports]


def _tracks_json(p, step: int = 5) -> dict:
    # 1 s running median for display only; detectors use the raw 10 Hz track.
    from scipy.ndimage import median_filter
    carrier = median_filter(p.carrier_hz, size=11, mode="nearest")
    return {"t": p.track_t[::step].round(2).tolist(), "carrier_hz": carrier[::step].round(2).tolist(),
            "level_db": p.level_db[::step].round(2).tolist()}


def _twin_trace(dup) -> dict:
    """Duplicate-audio head output for plotting: best off-diagonal correlation per 2 s block."""
    if dup is None:
        return {"block_t": [], "block_ncc": [], "threshold": twin.THRESHOLD, "block_s": twin.BLOCK_S, "ms": 0.0}
    return {"block_t": dup.block_t.round(2).tolist(), "block_ncc": dup.block_ncc.round(3).tolist(),
            "threshold": twin.THRESHOLD, "block_s": twin.BLOCK_S, "ms": round(dup.ms, 1)}


def _clock_line(start_utc: float, duration_s: float) -> dict:
    m = models().clock
    t = np.array([start_utc, start_utc + duration_s])
    return {"t_rec": [0.0, duration_s], "position": m.predict(t).tolist(), "period_s": m.period_s}


# ------------------------------------------------------------------ routes
@app.get("/api/health")
def health() -> dict:
    return {"models": MODEL_PATH.exists(), "gr_satellites": grsat.available(),
            "observations": len(list(ROOT.glob("obs_*/decoded.json"))),
            "station_public_key": STATION_KEY.public_b64(), "storage": "postgres" if DB else "memory"}


@app.get("/api/observations")
def observations() -> list[dict]:
    out = []
    split = _split()
    for d in sorted(ROOT.glob("obs_*"), reverse=True):
        if not (d / "decoded.json").exists():
            continue
        r = _record(d)
        dec = json.loads((d / "decoded.json").read_text(encoding="utf-8"))
        out.append({"id": r["observation_id"], "start": r["start"], "end": r["end"], "station": r["station_name"],
                    "station_lat": r["station_lat"], "station_lng": r["station_lng"],
                    "max_elevation": r["max_altitude"], "frames": len(dec["frames"]),
                    "satnogs_frames": len(r["frames"]), "waterfall_url": r["waterfall_url"],
                    "split": split.get(d.name, "?"), "tle": [r["tle1"], r["tle2"]]})
    return out


@app.get("/api/observations/{oid}")
def observation(oid: int) -> dict:
    d = _obs_dir(oid)
    result, meta = _cached(_analysis_key("observation", {"id": oid}, [d]), lambda: _observation(oid))
    result["cache"] = meta
    return result


def _observation(oid: int) -> dict:
    d = _obs_dir(oid)
    r = _record(d)
    p = load_pass(d)
    x, fs = load_audio(d / "audio.ogg")
    fc = json.loads((d / "decoded.json").read_text(encoding="utf-8"))["f_offset_hz"]
    start, end = iso_to_unix(r["start"]), iso_to_unix(r["end"])
    reports = analyse_pass(models(), p)
    intf = models().interference.detect(x, fs, fc, station=r["station_name"])
    return {
        "record": {k: r[k] for k in ("observation_id", "start", "end", "station_name", "station_lat", "station_lng",
                                     "station_alt", "frequency_hz", "mode", "tle1", "tle2", "max_altitude",
                                     "audio_sha256")},
        "split": _split().get(d.name, "?"),
        "geometry": pass_geometry(r["tle1"], r["tle2"], start, end, r["station_lat"], r["station_lng"],
                                  r["station_alt"], downlink_hz=r["frequency_hz"]),
        "orbit": pass_geometry(r["tle1"], r["tle2"], start - 2900, end + 2900, r["station_lat"], r["station_lng"],
                               r["station_alt"], step_s=30, downlink_hz=r["frequency_hz"]),
        "frames": _frames_json(reports), "tracks": _tracks_json(p), "clock": _clock_line(start, len(x) / fs),
        "spectrogram": spectrogram_png(x, fs, fc), "f_offset_hz": fc,
        "interference": {"prob": intf.prob.round(4).tolist(), "centres_s": intf.centres_s.round(2).tolist(),
                         "threshold": models().interference.threshold,
                         "alarms": [a.__dict__ for a in intf.alarms]},
    }


class ScenarioRequest(BaseModel):
    observation_id: int
    seed: int = Field(default=1, ge=0)
    variant: str = "standard"
    overrides: dict | None = None


@app.post("/api/scenario")
def run_scenario(req: ScenarioRequest) -> dict:
    d = _obs_dir(req.observation_id)
    if req.variant not in scenario.VARIANTS:
        raise HTTPException(400, f"variant must be one of {scenario.VARIANTS}")
    donor = None
    if req.variant == "cross_pass_replay":
        others = [o for o in sorted(ROOT.glob("obs_*")) if o != d and (o / "decoded.json").exists()]
        donor = others[req.seed % len(others)]
    params = req.model_dump()
    params["overrides"] = req.overrides or {}
    key = _analysis_key("scenario", params, [d] + ([donor] if donor else []))
    result, meta = _cached(key, lambda: _scenario(req, d, donor))
    capture = result.pop("_capture")
    capture["signer"] = {"alg": "Ed25519", "public_key": STATION_KEY.public_b64()}
    signature = STATION_KEY.private.sign(canonical_json(capture))
    STATION_KEY.public.verify(signature, canonical_json(capture))
    result["manifest"]["signature_valid"] = True
    result["manifest"]["public_key"] = STATION_KEY.public_b64()
    result["manifest"]["signature"] = base64.b64encode(signature).decode()
    result["capture_manifest"] = {**capture, "signature": base64.b64encode(signature).decode()}
    result["cache"] = meta
    return _audit(result, f"{req.observation_id}-{req.variant}-{req.seed}",
                  {"observation": req.observation_id, "variant": req.variant,
                   "manifest_authentic": result["manifest"]["authentic"], "analysis_cache": meta})


def _scenario(req: ScenarioRequest, d: Path, donor: Path | None) -> dict:
    t0 = time.perf_counter()
    ap = scenario.build(d, req.seed, req.variant, donor_dir=donor, keep_audio=True, overrides=req.overrides)
    t_build = time.perf_counter() - t0
    m = models()
    t0 = time.perf_counter()
    reports = analyse_pass(m, ap.pass_)
    t_frames = time.perf_counter() - t0
    x_clean, fs = load_audio(d / "audio.ogg")
    fc = json.loads((d / "decoded.json").read_text(encoding="utf-8"))["f_offset_hz"]
    y = ap.audio if ap.audio is not None else x_clean
    t0 = time.perf_counter()
    intf = m.interference.detect(y, fs, fc, station=_record(d)["station_name"])
    t_intf = time.perf_counter() - t0
    # Independent evidence lane: reported beside the fused decisions, not folded
    # into them, so Attack Lab scores stay those of the frame benchmark.
    dup = twin.detect(y, fs, fc)

    # Provenance: the station signed the clean capture; check the attacked copy.
    manifest = create_manifest(x_clean, fs, {"observation_id": req.observation_id}, STATION_KEY)
    chk = verify_manifest(manifest, y, fs, STATION_KEY.public_b64())

    onair = _onair(ap.pass_)

    labels = ap.labels
    flagged = np.array([r.decision != "ACCEPT" for r in reports], dtype=bool)
    tp = int((flagged & labels).sum()); fp = int((flagged & ~labels).sum()); fn = int((~flagged & labels).sum())
    ti = ap.truth.get("interference")
    # Scored as in the benchmark: an alarm must overlap the jammer in time and point at it in frequency.
    from ..bench.run import freq_tolerance
    overlap = [a for a in intf.alarms if ti and a.end_s > ti["start_s"] and a.start_s < ti["start_s"] + ti["dur_s"]]
    intf_hit = bool(ti and any(abs(a.freq_hz - ti["freq_hz"]) <= freq_tolerance(ti["kind"], ti.get("bw_hz"))
                               for a in overlap))
    copied = [s for s in (ap.truth.get("replay"), ap.truth.get("sequence")) if s and not s.get("cross_pass")
              and s.get("variant", "duplicate") == "duplicate"]
    dup_hit = bool(copied) and all(any(m.end_s > s["dst_start_s"] and m.start_s < s["dst_end_s"] for m in dup.matches)
                                   for s in copied)
    start = iso_to_unix(_record(d)["start"])
    return {
        "_capture": {k: v for k, v in manifest.items() if k not in {"signature", "signer"}},
        "truth": ap.truth, "labels": labels.tolist(), "label_kind": ap.label_kind,
        "frames": _frames_json(reports), "tracks": _tracks_json(ap.pass_),
        "clock": _clock_line(start, len(y) / fs),
        "spectrogram": spectrogram_png(y, fs, fc),
        "interference": {"prob": intf.prob.round(4).tolist(), "centres_s": intf.centres_s.round(2).tolist(),
                         "threshold": m.interference.threshold, "alarms": [a.__dict__ for a in intf.alarms],
                         "detected_truth": intf_hit, "any_alarm_overlap": bool(overlap)},
        "manifest": {"authentic": chk.authentic, "signature_valid": chk.signature_valid,
                     "tampered_intervals": chk.tampered_intervals(1.0),
                     "merkle_root": manifest["audio"]["merkle_root"]},
        "duplicates": [m.__dict__ for m in dup.matches],
        "duplicate_trace": {**_twin_trace(dup), "expected": bool(copied), "detected_truth": dup_hit},
        "score": {"tp": tp, "fp": fp, "fn": fn, "frames": len(reports)},
        "timing_ms": {"attack_and_decode": round(t_build * 1e3, 1), "frame_heads": round(t_frames * 1e3, 1),
                      "interference_head": round(t_intf * 1e3, 1), "duplicate_audio_head": round(dup.ms, 1)},
        "onair": onair,
        "manifest_root": manifest["audio"]["merkle_root"],
        "duration_s": len(y) / fs,
    }


def _onair(p) -> dict:
    """NASA OnAIR verdicts for every decoded frame (empty if OnAIR is not installed)."""
    from ..nasa import onair_bridge
    if not onair_bridge.available():
        return {"available": False}
    t0 = time.perf_counter()
    recs = onair_bridge.run(p, period_s=models().clock.period_s)
    return {"available": True, "ms": round((time.perf_counter() - t0) * 1e3, 1), "frames": recs,
            "path": str(onair_bridge.onair_path())}


@app.get("/api/onair/demo")
def onair_demo(observation_id: int = 15123656, seed: int = 1000) -> dict:
    """OnAIR on the clean pass and on the same pass after the standard attack."""
    d = _obs_dir(observation_id)
    result, meta = _cached(_analysis_key("onair", {"observation_id": observation_id, "seed": seed}, [d]),
                           lambda: _onair_demo(observation_id, seed))
    result["cache"] = meta
    return result


def _onair_demo(observation_id: int, seed: int) -> dict:
    d = _obs_dir(observation_id)
    clean = load_pass(d)
    ap = scenario.build(d, seed, "standard")
    from ..nasa import onair_bridge
    return {"available": onair_bridge.available(), "limits": onair_bridge.training_limits() if onair_bridge.available() else {},
            "clean": _onair(clean), "attacked": _onair(ap.pass_), "labels": ap.labels.tolist(), "label_kind": ap.label_kind,
            "truth": ap.truth}


@app.get("/api/benchmark")
def benchmark() -> dict:
    path = RESULTS_ROOT / "benchmark.json"
    if not path.exists():
        path = RESULTS_ROOT / "benchmark_quick.json"
    if not path.exists():
        raise HTTPException(404, "run `py -m sentinel.bench.run` first")
    result = json.loads(path.read_text(encoding="utf-8"))
    twin_path = RESULTS_ROOT / "twin_benchmark.json"
    if twin_path.exists():
        t = json.loads(twin_path.read_text(encoding="utf-8"))
        result["twin"] = {k: v for k, v in t.items() if k != "cases"}
        result["twin"]["clean"] = {k: v for k, v in t["clean"].items() if k != "cases"}
    return result


@app.get("/api/model-card")
def model_card() -> dict:
    return json.loads((PROJECT_ROOT / "models" / "model_card.json").read_text(encoding="utf-8"))


class SdlsRequest(BaseModel):
    observation_id: int
    service: str = "AUTH"


@app.post("/api/sdls/demo")
def sdls_demo(req: SdlsRequest) -> dict:
    """Protect a real pass with SDLS, then try the standard attacks on it."""
    p = load_pass(_obs_dir(req.observation_id))
    service = Service(req.service)
    ks = KeyStore()
    tx = SecurityAssociation(spi=0x0073, key=ks.derive(0x0073), service=service)
    rx = SdlsEndpoint(ks)
    rx.add_sa(0x0073, service=service, window=64)
    log = []
    protected = [tx.apply(f) for f in p.payloads]
    t0 = time.perf_counter()
    for i, f in enumerate(protected):
        v, _, arsn = rx.process(f)
        log.append({"step": "downlink", "frame": i, "arsn": arsn, "verdict": v.value})
    us = (time.perf_counter() - t0) / max(1, len(protected)) * 1e6
    k = min(8, len(protected))
    first = max(0, len(protected) - k - 4)
    for i, f in enumerate(protected[first:first + k], start=first):
        v, _, arsn = rx.process(f)
        log.append({"step": "replay", "frame": i, "arsn": arsn, "verdict": v.value})
    forged = bytearray(protected[-1])
    forged[20] ^= 0x01
    v, _, arsn = rx.process(bytes(forged))
    log.append({"step": "bit-flip injection", "frame": len(protected) - 1, "arsn": arsn, "verdict": v.value})
    bumped = bytearray(protected[-1])
    off = 2 + (12 if service is Service.AUTH_ENC else 0)
    bumped[off:off + 4] = (tx.tx_arsn + 100).to_bytes(4, "big")
    v, _, arsn = rx.process(bytes(bumped))
    log.append({"step": "forged counter", "frame": len(protected) - 1, "arsn": arsn, "verdict": v.value})
    return {"service": service.value, "overhead_bytes": tx.overhead_bytes, "verify_us_per_frame": round(us, 2),
            "stats": rx.sas[0x0073].stats, "log": log}


@app.get("/api/ledger")
def ledger_view(limit: int = 40) -> dict:
    LEDGER.refresh()
    chk = ledger_mod.verify(LEDGER.entries, STATION_KEY.public_b64())
    return {"verification": chk.__dict__, "head": LEDGER.head, "entries": LEDGER.entries[-limit:],
            "public_key": STATION_KEY.public_b64()}


@app.get("/api/runs")
def runs(limit: int = 20) -> dict:
    """Recent runs from the database (production storage)."""
    if DB is None:
        raise HTTPException(404, "no database configured: set SENTINEL_DATABASE_URL")
    return {"runs": DB.recent_runs(min(max(limit, 1), 200))}


@app.get("/api/decisions")
def decisions(decision: str = "QUARANTINE", limit: int = 100) -> dict:
    """Frames with a given decision across all stored runs, newest first."""
    if DB is None:
        raise HTTPException(404, "no database configured: set SENTINEL_DATABASE_URL")
    if decision not in ("ACCEPT", "VERIFY", "QUARANTINE"):
        raise HTTPException(400, "decision must be ACCEPT, VERIFY or QUARANTINE")
    return {"decision": decision, "frames": DB.decisions(decision, min(max(limit, 1), 1000))}


@app.post("/api/ledger/tamper")
def ledger_tamper(index: int = 0) -> dict:
    """Demonstrate tamper evidence on a *copy* of the ledger."""
    if not LEDGER.entries:
        raise HTTPException(400, "ledger is empty: run a scenario first")
    entries = [dict(e) for e in LEDGER.entries]
    i = min(max(0, index), len(entries) - 1)
    entries[i] = {**entries[i], "data": {**entries[i]["data"], "decision": "ACCEPT", "tampered": True}}
    chk = ledger_mod.verify(entries, STATION_KEY.public_b64())
    return {"tampered_index": i, "verification": chk.__dict__}


@app.post("/api/analyse")
async def analyse_upload(file: UploadFile = File(...), start: str | None = Form(None)) -> dict:
    """Blind analysis of an uploaded recording (the jury's held-out file)."""
    suffix = Path(file.filename or "rec.wav").suffix.lower()
    if suffix not in {".wav", ".ogg", ".flac"}:
        raise HTTPException(422, "Upload a .wav, .ogg or .flac recording")
    data = await file.read(256 * 1024 * 1024 + 1)
    if not data:
        raise HTTPException(422, "The recording is empty")
    if len(data) > 256 * 1024 * 1024:
        raise HTTPException(413, "Recording exceeds 256 MiB")
    try:
        start_utc = iso_to_unix(start) if start else 0.0
    except (ValueError, OverflowError):
        raise HTTPException(422, "Start UTC must be an ISO-8601 timestamp")
    return await run_in_threadpool(_upload, data, file.filename or "rec.wav", suffix, start_utc, bool(start))


def _upload(data: bytes, filename: str, suffix: str, start_utc: float, given: bool) -> dict:
    with COMPUTE_LOCK:
        return _upload_locked(data, filename, suffix, start_utc, given)


def _upload_locked(data: bytes, filename: str, suffix: str, start_utc: float, given: bool) -> dict:
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        try:
            x, fs = load_audio(tmp_path)
        except Exception as error:
            raise HTTPException(422, "The file is not a readable audio recording") from error
        if not len(x):
            raise HTTPException(422, "The recording contains no samples")
    finally:
        tmp_path.unlink(missing_ok=True)
    m = models()
    if not grsat.available():
        raise HTTPException(503, "GNU Radio / gr-satellites is unavailable; run sentinel doctor")
    rr = analyse_recording(m, x, fs, start_utc, {"observation_id": 0})
    absolute_time = "given" if given else "unknown"
    p, reports = rr.pass_, rr.frames
    if not given:
        from ..analyse import _infer_start
        inferred = _infer_start(m, p.t_rec, p.payloads)
        if inferred is not None:
            p.start_utc = inferred
            reports = flag_duplicates(analyse_pass(m, p), rr.duplicates)
            absolute_time = "inferred"
    run_id = f"upload-{uuid4().hex}"
    audio_sha = hashlib.sha256(data).hexdigest()
    frames = _frames_json(reports)
    _log_run(run_id, "upload", {"file": filename, "sha256": audio_sha}, frames, source=filename, audio_sha256=audio_sha)
    duration = len(x) / fs
    clock_line = {"t_rec": [0.0, duration], "position": m.clock.predict(np.array([p.start_utc, p.start_utc + duration])).tolist(),
                  "period_s": m.clock.period_s}
    return {
        "run_id": run_id, "file": filename, "duration_s": duration, "absolute_time": absolute_time,
        "frames": frames, "tracks": _tracks_json(p), "clock": clock_line,
        "spectrogram": spectrogram_png(x, fs, rr.f_offset_hz), "f_offset_hz": rr.f_offset_hz,
        "interference": {"prob": rr.interference.prob.round(4).tolist(),
                         "centres_s": rr.interference.centres_s.round(2).tolist(),
                         "threshold": m.interference.threshold, "alarms": [a.__dict__ for a in rr.interference.alarms]},
        "response": {"chosen": rr.response, "frames_decoded": rr.response_frames},
        "missing": rr.missing, "duplicates": [dm.__dict__ for dm in rr.duplicates.matches] if rr.duplicates else [],
        "duplicate_trace": _twin_trace(rr.duplicates),
        "timing_ms": {k: round(v, 1) for k, v in rr.timings_ms.items()},
        "ledger_head": LEDGER.head,
    }


DOCS = {
    "compliance": "00_compliance_matrix.md", "threat-model": "01_threat_model.md",
    "architecture": "02_architecture_trust_anchor.md", "signal-processing": "03_signal_processing.md",
    "detection": "04_detection.md", "adversarial-validation": "05_adversarial_validation.md",
    "dataset": "06_dataset_and_reproducibility.md",
}


@app.get("/api/docs/{slug}")
def doc(slug: str) -> dict:
    if slug not in DOCS:
        raise HTTPException(404, "unknown document")
    return {"slug": slug, "markdown": (PROJECT_ROOT / "docs" / DOCS[slug]).read_text(encoding="utf-8")}


_INTEROP_CACHE: dict = {}


@app.get("/api/cryptolib/interop")
def cryptolib_interop(observation_id: int = 15261075, n: int = 6) -> dict:
    """Run NASA CryptoLib (CCSDS SDLS, as shipped with NOS3) live against our
    implementation on real AO-73 frames."""
    from ..trust.ccsds_tm import (ARSN_LEN, FECF_LEN, HDR, MAC_LEN, SPI_LEN, TmSdlsLink, cryptolib,
                                  cryptolib_available, crc16_ccitt)
    key = (observation_id, n)
    if key in _INTEROP_CACHE:
        return _INTEROP_CACHE[key]
    if not cryptolib_available():
        return {"available": False, "hint": "bash grss/sentinel/trust/cryptolib_bridge/build.sh (Linux/WSL)"}
    frames = load_pass(_obs_dir(observation_id)).payloads[:n]
    k = bytes(range(32))
    t0 = time.perf_counter()
    nasa_apply = cryptolib("apply", k, [f.hex() for f in frames])
    t_nasa = (time.perf_counter() - t0) * 1e3
    ours = TmSdlsLink(k)
    ours_apply = [ours.apply(f).hex() for f in frames]
    nasa_on_ours = [ln.split()[0] == "0" for ln in cryptolib("process", k, ours_apply)]
    rx = TmSdlsLink(k)
    ours_on_nasa = [rx.process(bytes.fromhex(h))[0].value == "ACCEPT" for h in nasa_apply]

    forged = bytearray(bytes.fromhex(ours_apply[0]))
    forged[HDR + SPI_LEN + ARSN_LEN + 40] ^= 0x01
    forged[-2:] = crc16_ccitt(bytes(forged[:-2])).to_bytes(2, "big")
    nasa_forged = cryptolib("process", k, [bytes(forged).hex()])[0].split()[0]
    rx2 = TmSdlsLink(k)
    ours_forged = rx2.process(bytes(forged))[0].value

    replay_seq = nasa_apply + [nasa_apply[1]]
    nasa_replay = cryptolib("process", k, replay_seq)[-1].split()[0]
    rx3 = TmSdlsLink(k)
    ours_replay = [rx3.process(bytes.fromhex(h))[0].value for h in replay_seq][-1]

    f0 = bytes.fromhex(nasa_apply[0])
    anatomy = [
        {"field": "Primary header", "bytes": f0[:HDR].hex()},
        {"field": "SPI", "bytes": f0[HDR:HDR + SPI_LEN].hex()},
        {"field": "ARSN", "bytes": f0[HDR + SPI_LEN:HDR + SPI_LEN + ARSN_LEN].hex()},
        {"field": "AO-73 telemetry (256 B)", "bytes": f0[HDR + SPI_LEN + ARSN_LEN:-(MAC_LEN + FECF_LEN)].hex()},
        {"field": "MAC (HMAC-SHA-256/128)", "bytes": f0[-(MAC_LEN + FECF_LEN):-FECF_LEN].hex()},
        {"field": "FECF", "bytes": f0[-FECF_LEN:].hex()},
    ]
    out = {
        "available": True, "library": "NASA CryptoLib 1.7.5 (NOS3 components/cryptolib)", "frames": len(frames),
        "byte_identical": nasa_apply == ours_apply, "nasa_apply_ms": round(t_nasa, 1), "anatomy": anatomy,
        "checks": [
            {"test": "Our frames verified by CryptoLib", "nasa": f"{sum(nasa_on_ours)}/{len(frames)} accepted", "sentinel": "—", "ok": all(nasa_on_ours)},
            {"test": "CryptoLib frames verified by Sentinel", "nasa": "—", "sentinel": f"{sum(ours_on_nasa)}/{len(frames)} accepted", "ok": all(ours_on_nasa)},
            {"test": "Telemetry bit flipped (CRC fixed)", "nasa": "rejected" if nasa_forged != "0" else "ACCEPTED",
             "sentinel": "rejected" if ours_forged != "ACCEPT" else "ACCEPTED", "ok": nasa_forged != "0" and ours_forged != "ACCEPT"},
            {"test": "Valid frame replayed", "nasa": "ACCEPTED" if nasa_replay == "0" else "rejected",
             "sentinel": "rejected" if ours_replay != "ACCEPT" else "ACCEPTED", "ok": ours_replay != "ACCEPT",
             "note": "CryptoLib checks anti-replay on TC only"},
        ],
    }
    _INTEROP_CACHE[key] = out
    return out


@app.get("/api/analyse/sample")
def analyse_sample(seed: int = 4242, observation_id: int = 15254375) -> dict:
    """Blind analysis of a held-out recording attacked with hidden parameters
    (what the jury will do), returned with the hidden truth for comparison."""
    d = _obs_dir(observation_id)
    result, meta = _cached(_analysis_key("sample", {"observation_id": observation_id, "seed": seed}, [d]),
                           lambda: _analyse_sample(seed, observation_id))
    result["cache"] = meta
    return _audit(result, f"sample-{observation_id}-{seed}",
                  {"observation": observation_id, "variant": "blind-sample", "analysis_cache": meta})


def _analyse_sample(seed: int, observation_id: int) -> dict:
    d = _obs_dir(observation_id)
    ap = scenario.build(d, seed, "standard", keep_audio=True)
    m = models()
    rr = analyse_recording(m, ap.audio, ap.fs, 0.0, {"observation_id": observation_id})
    p, reports = rr.pass_, rr.frames
    from ..analyse import _infer_start
    inferred = _infer_start(m, p.t_rec, p.payloads)
    if inferred is not None:
        p.start_utc = inferred
        reports = flag_duplicates(analyse_pass(m, p), rr.duplicates)
    duration = len(ap.audio) / ap.fs
    return {
        "file": f"heldout_{observation_id}_{seed}.wav", "duration_s": duration,
        "absolute_time": "inferred" if inferred is not None else "unknown", "truth": ap.truth,
        "frames": _frames_json(reports), "tracks": _tracks_json(p),
        "clock": {"t_rec": [0.0, duration], "position": m.clock.predict(np.array([p.start_utc, p.start_utc + duration])).tolist(),
                  "period_s": m.clock.period_s},
        "spectrogram": spectrogram_png(ap.audio, ap.fs, rr.f_offset_hz), "f_offset_hz": rr.f_offset_hz,
        "interference": {"prob": rr.interference.prob.round(4).tolist(), "centres_s": rr.interference.centres_s.round(2).tolist(),
                         "threshold": m.interference.threshold, "alarms": [a.__dict__ for a in rr.interference.alarms]},
        "response": {"chosen": rr.response, "frames_decoded": rr.response_frames},
        "missing": rr.missing, "duplicates": [dm.__dict__ for dm in rr.duplicates.matches] if rr.duplicates else [],
        "duplicate_trace": _twin_trace(rr.duplicates),
        "timing_ms": {k: round(v, 1) for k, v in rr.timings_ms.items()},
    }
