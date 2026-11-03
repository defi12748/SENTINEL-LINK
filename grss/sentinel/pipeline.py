"""End-to-end analysis of one recording (or one decoded pass).

    audio ─► carrier estimate ─► interference head, duplicate-audio head ─► (excise) ─► gr-satellites
          ─► AO-40 blocks + timing + Doppler/level tracks ─► clock / telemetry /
          splice heads ─► fusion ─► ACCEPT / VERIFY / QUARANTINE ─► ledger
"""

from __future__ import annotations

import hashlib
import time
import tracemalloc
from dataclasses import dataclass, field

import numpy as np

from .data.corpus import Pass
from .decode import funcube
from .detect import clock, fusion, splice, twin
from .detect.interference import InterferenceModel, InterferenceResult
from .detect.telemetry import TelemetryModel


@dataclass
class Models:
    clock: clock.ClockModel
    telemetry: TelemetryModel
    interference: InterferenceModel
    fusion: fusion.FusionModel


@dataclass
class FrameReport:
    index: int
    t_rec: float
    t_utc: float
    frame_type: int | None
    sequence: int | None
    position: int | None
    probability: float
    decision: str
    evidence: dict[str, float]
    telemetry: dict[str, float] = field(default_factory=dict)
    sha256: str = ""


def frame_evidence(models: Models, p: Pass) -> tuple[dict[str, np.ndarray], list]:
    parsed = p.parsed()
    ok = np.array([f is not None for f in parsed], dtype=bool)
    n = len(parsed)
    feats = {k: np.zeros(n) for k in fusion.FEATURES + ["u_sigma", "pass_offset_sigma"]}
    if ok.any():
        idx = np.flatnonzero(ok)
        pos = np.array([parsed[i].position for i in idx])
        cf = clock.frame_features(models.clock, p.t_utc[idx], pos)
        for k in ("u_sigma", "u_behind", "u_ahead", "behind", "duplicate", "step_err", "pass_offset_sigma",
                  "pass_offset_excess"):
            feats[k][idx] = cf[k]
        tf = models.telemetry.features([p.payloads[i] for i in idx])
        for k, v in tf.items():
            feats[k][idx] = v
    if n and len(p.track_t) > 10:   # frame files carry no physical-layer tracks
        sf = splice.frame_features(p.track_t, p.carrier_hz, p.level_db, p.t_rec)
        for k, v in sf.items():
            feats[k][:] = v
    # unparseable frame (wrong length / type): maximal suspicion on the clock axis
    feats["u_behind"][~ok] = fusion.CLIP["u_behind"]
    return feats, parsed


def analyse_pass(models: Models, p: Pass) -> list[FrameReport]:
    feats, parsed = frame_evidence(models, p)
    X = fusion.design_matrix(feats)
    prob = models.fusion.predict(X)
    decisions = models.fusion.decide(prob)
    out = []
    for i, fr in enumerate(parsed):
        out.append(FrameReport(
            index=i, t_rec=float(p.t_rec[i]), t_utc=float(p.t_utc[i]),
            frame_type=fr.frame_type if fr else None, sequence=fr.sequence if fr else None,
            position=fr.position if fr else None, probability=float(prob[i]), decision=decisions[i],
            evidence={k: float(v[i]) for k, v in feats.items()},
            telemetry=fr.telemetry if fr else {}, sha256=hashlib.sha256(p.payloads[i]).hexdigest()))
    return out


@dataclass
class RecordingReport:
    frames: list[FrameReport]
    interference: InterferenceResult
    f_offset_hz: float
    timings_ms: dict[str, float]
    peak_mem_mb: float
    pass_: Pass
    missing: list[dict] = field(default_factory=list)
    response: str = "none"
    response_frames: dict[str, int] = field(default_factory=dict)
    duplicates: twin.TwinResult | None = None


def flag_duplicates(frames: list[FrameReport], dup: twin.TwinResult | None) -> list[FrameReport]:
    """Frames inside the later copy of a duplicated audio stretch: evidence
    ``audio_duplicate`` and at least a verification request. The head is
    format-independent, so this also holds when the clock cannot be used."""
    for f in frames:
        later = dup is not None and any(m.start_s - 0.05 <= f.t_rec < m.end_s - 1.0 for m in dup.matches)
        f.evidence["audio_duplicate"] = float(later)
        if later and f.decision == "ACCEPT":
            f.decision = "VERIFY"
    return frames


def missing_frames(models: Models, frames: list[FrameReport], alarms) -> list[dict]:
    """Frame positions the on-board clock says were transmitted but were not
    decoded among the accepted frames. Inside an interference alarm they are
    'unaccounted under interference' -> verification request: a jammer can
    hide a dropped or injected frame."""
    good = sorted((f.position, f.t_rec) for f in frames if f.decision == "ACCEPT" and f.position is not None)
    if len(good) < 2:
        return []
    have = {p for p, _ in good}
    p0, t0 = good[0]
    out = []
    for pos in range(good[0][0], good[-1][0] + 1):
        if pos in have:
            continue
        t = t0 + (pos - p0) * models.clock.period_s
        jammed = any(a.start_s - 2 <= t <= a.end_s + 2 for a in alarms)
        out.append({"position": pos, "frame_type": pos % funcube.FRAMES_PER_SET, "expected_t_rec": round(t, 2),
                    "under_interference": jammed})
    return out


def analyse_recording(models: Models, x: np.ndarray, fs: int, start_utc: float, meta: dict,
                      mitigate: bool = True) -> RecordingReport:
    from .decode import grsat
    from .dsp.audio import estimate_bpsk_center
    from .dsp.mitigate import estimate_width, excise, tf_excise

    tracemalloc.start()
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    fc = estimate_bpsk_center(x, fs)
    timings["carrier_estimate"] = (time.perf_counter() - t0) * 1e3

    t0 = time.perf_counter()
    intf = models.interference.detect(x, fs, fc, station=meta.get("station"))
    timings["interference_head"] = (time.perf_counter() - t0) * 1e3

    t0 = time.perf_counter()
    dup = twin.detect(x, fs, fc)
    timings["duplicate_audio_head"] = (time.perf_counter() - t0) * 1e3

    # Response, closed loop: try each excision and keep the one that yields
    # the most FEC-verified frames (only Reed-Solomon-valid frames are counted,
    # so the choice cannot be gamed by garbage output).
    candidates = {"none": x}
    if mitigate and intf.alarms:
        s0, s1 = min(a.start_s for a in intf.alarms), max(a.end_s for a in intf.alarms)
        t0 = time.perf_counter()
        y = x
        for a in intf.alarms:
            y = excise(y, fs, a.freq_hz, estimate_width(y, fs, a.freq_hz, a.start_s, a.end_s), a.start_s, a.end_s)
        candidates["band_stop"] = y
        candidates["tf_mask"] = tf_excise(x, fs, s0, s1)
        timings["excision"] = (time.perf_counter() - t0) * 1e3
    t0 = time.perf_counter()
    decoded = {name: grsat.decode_audio(sig, fs, start_utc, f_offset=fc) for name, sig in candidates.items()}
    timings["decode"] = (time.perf_counter() - t0) * 1e3
    response = max(decoded, key=lambda k: (len(decoded[k].frames), k == "none"))
    res = decoded[response]
    response_log = {k: len(v.frames) for k, v in decoded.items()}

    p = Pass(observation_id=meta.get("observation_id", 0), station=meta.get("station", ""), start_utc=start_utc,
             t_rec=np.array([f.t_rec for f in res.frames]), payloads=[f.payload for f in res.frames],
             track_t=res.track_t, carrier_hz=res.carrier_hz, level_db=res.level_db,
             tle=meta.get("tle", ("", "")), station_lla=meta.get("station_lla", (0.0, 0.0, 0.0)))
    t0 = time.perf_counter()
    frames = flag_duplicates(analyse_pass(models, p), dup)
    timings["frame_heads_and_fusion"] = (time.perf_counter() - t0) * 1e3
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return RecordingReport(frames, intf, fc, timings, peak / 2 ** 20, p,
                           missing_frames(models, frames, intf.alarms), response, response_log, dup)


def frame_position(payload: bytes) -> int | None:
    f = funcube.parse(payload)
    return f.position if f else None
