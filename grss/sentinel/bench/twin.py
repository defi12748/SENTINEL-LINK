"""Benchmark of the duplicate-audio head on the held-out recordings.

    py -m sentinel.bench.twin [--seeds 3]     # -> results/twin_benchmark.json

Runs on audio only (no decoder): the standard scenario is applied with
``scenario.apply`` and the head looks for copied stretches. The threshold is
fixed in ``detect/twin.py``; clean recordings measure false alarms, including
the training ones since the head has nothing to train. Evasion variants model
an attacker who knows about the head: the edited file re-encoded as Ogg
Vorbis, fresh in-band noise added over the copy, and the copy resampled
slightly (10 and 100 ppm).
"""

from __future__ import annotations

import argparse
import json
import platform
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psutil
import soundfile as sf
from scipy.signal import resample

from .. import RESULTS_ROOT
from ..dsp.audio import load_audio
from ..redteam import scenario
from ..detect import twin
from .run import _rate, wilson


def _fc(d) -> float:
    return json.loads((d / "decoded.json").read_text())["f_offset_hz"]


def _overlaps(res: twin.TwinResult, s: float, e: float) -> bool:
    return any(m.end_s > s + 0.5 and m.start_s < e - 0.5 for m in res.matches)


def _false_matches(res: twin.TwinResult, intervals, sources) -> int:
    """Matches that touch neither an edited interval nor its source."""
    spans = list(intervals) + list(sources)
    return sum(not any(m.end_s > s and m.start_s < e for s, e in spans) for m in res.matches)


def vorbis_roundtrip(y: np.ndarray, fs: int) -> np.ndarray:
    """Re-encode as Ogg Vorbis, the format SatNOGS publishes. Written in
    blocks: libsndfile's Vorbis encoder crashes on one 20 M-sample write."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "attacked.ogg"
        with sf.SoundFile(path, "w", fs, 1, format="OGG", subtype="VORBIS") as f:
            for i in range(0, len(y), 1 << 16):
                f.write(y[i:i + (1 << 16)])
        z, _ = sf.read(path, dtype="float32")
    return z[: len(y)]


def noise_over(y: np.ndarray, s: float, e: float, fs: int, fc: float, rel_db: float, rng) -> np.ndarray:
    """White noise over [s, e], scaled so that inside the band the head
    analyses it has ``rel_db`` the power of the recording there."""
    z = y.copy()
    i0, i1 = int(s * fs), int(e * fs)
    w = rng.standard_normal(i1 - i0).astype(np.float32)
    band = lambda v: float(np.mean(np.abs(twin.baseband(v, fs, fc)[0]) ** 2))   # noqa: E731
    z[i0:i1] += w * np.sqrt(band(y[i0:i1]) * 10 ** (rel_db / 10) / band(w))
    return z


def stretch_copy(y: np.ndarray, s: float, e: float, fs: int, factor: float) -> np.ndarray:
    """Resample the copied stretch by ``factor`` (kept at the same length)."""
    z = y.copy()
    i0, i1 = int(s * fs), int(e * fs)
    seg = resample(y[i0:i1], int(round((i1 - i0) * factor)))
    z[i0:i1] = seg[: i1 - i0] if len(seg) >= i1 - i0 else np.pad(seg, (0, i1 - i0 - len(seg)))
    return z


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    args = ap.parse_args()
    seeds = list(range(1000, 1000 + args.seeds))
    train_dirs, test_dirs = scenario.split()
    t_start = time.time()
    rng = np.random.default_rng(0)

    clean = []
    for d in train_dirs + test_dirs:
        x, fs = load_audio(d / "audio.ogg")
        r = twin.detect(x, fs, _fc(d))
        clean.append({"obs": d.name, "held_out": d in test_dirs, "max_ncc": round(float(r.block_ncc.max()), 3),
                      "matches": len(r.matches), "minutes": round(len(x) / fs / 60, 2), "ms": round(r.ms)})
        print(f"  clean {d.name}: max {clean[-1]['max_ncc']} matches {len(r.matches)}")

    rows, evasion = [], {"vorbis_reencode": [], "inband_noise_-6db": [], "inband_noise_0db": [],
                         "stretch_1e-5": [], "stretch_1e-4": []}
    for d in test_dirs:
        fc = _fc(d)
        for seed in seeds:
            att = scenario.apply(d, seed, "standard")
            fs = att.fs
            res = twin.detect(att.audio, fs, fc)
            rep = att.truth.get("replay")
            seq = att.truth.get("sequence")
            srcs = []
            if rep:
                srcs.append((rep["src_start_s"], rep["src_start_s"] + rep["dst_end_s"] - rep["dst_start_s"]))
            if seq and seq.get("variant") == "duplicate":
                srcs.append((seq["src_start_s"], seq["src_start_s"] + seq["dst_end_s"] - seq["dst_start_s"]))
            row = {"obs": d.name, "seed": seed, "ms": round(res.ms),
                   "false_matches": _false_matches(res, [(s, e) for s, e, _ in att.intervals], srcs)}
            if rep:
                row["replay_detected"] = _overlaps(res, rep["dst_start_s"], rep["dst_end_s"])
                row["replay_ncc"] = round(max((m.ncc for m in res.matches), default=0.0), 3)
            if seq:
                row["sequence_variant"] = seq["variant"]
                row["sequence_detected"] = _overlaps(res, seq["dst_start_s"], seq["dst_end_s"])
            rows.append(row)
            if rep and seed == seeds[0]:
                s, e = rep["dst_start_s"], rep["dst_end_s"]
                variants = {
                    "vorbis_reencode": vorbis_roundtrip(att.audio, fs),
                    "inband_noise_-6db": noise_over(att.audio, s, e, fs, fc, -6.0, rng),
                    "inband_noise_0db": noise_over(att.audio, s, e, fs, fc, 0.0, rng),
                    "stretch_1e-5": stretch_copy(att.audio, s, e, fs, 1 + 1e-5),
                    "stretch_1e-4": stretch_copy(att.audio, s, e, fs, 1 + 1e-4),
                }
                for name, y in variants.items():
                    evasion[name].append(_overlaps(twin.detect(y, fs, fc), s, e))
            print(f"  attacked {d.name} seed {seed}: {row}")

    held = [c for c in clean if c["held_out"]]
    rep_rows = [r for r in rows if "replay_detected" in r]
    dup = [r for r in rows if r.get("sequence_variant") == "duplicate"]
    swap = [r for r in rows if r.get("sequence_variant") == "swap"]
    n_rep = sum(r["replay_detected"] for r in rep_rows)
    n_dup = sum(r["sequence_detected"] for r in dup)
    fa = sum(c["matches"] > 0 for c in clean)
    hours = sum(c["minutes"] for c in clean) / 60
    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "cpu_count": psutil.cpu_count()},
        "threshold": twin.THRESHOLD, "block_s": twin.BLOCK_S, "baseband_hz": 48000 / twin.DECIMATE, "seeds": seeds,
        "clean": {"recordings": len(clean), "with_match": fa, "with_match_ci95": wilson(fa, len(clean)),
                  "false_matches_per_hour": round(sum(c["matches"] for c in clean) / hours, 3),
                  "max_ncc": max(c["max_ncc"] for c in clean),
                  "held_out_max_ncc": max(c["max_ncc"] for c in held), "cases": clean},
        "replay": {"n": len(rep_rows), "detected": n_rep, "rate": _rate(n_rep, len(rep_rows)),
                   "ci95": wilson(n_rep, len(rep_rows))},
        "sequence_duplicate": {"n": len(dup), "detected": n_dup, "rate": _rate(n_dup, len(dup)),
                               "ci95": wilson(n_dup, len(dup))},
        "sequence_swap": {"n": len(swap), "detected": sum(r["sequence_detected"] for r in swap),
                          "note": "a swap copies nothing; not expected to be seen by this head"},
        "attacked_false_matches": sum(r["false_matches"] for r in rows),
        "evasion": {k: {"n": len(v), "detected": int(sum(v)), "rate": _rate(int(sum(v)), len(v))}
                    for k, v in evasion.items()},
        "latency_ms_per_recording_mean": round(float(np.mean([c["ms"] for c in clean])), 1),
        "cases": rows,
        "resources": {"peak_rss_mb": round(psutil.Process().memory_info().rss / 2 ** 20, 1),
                      "wall_clock_s": round(time.time() - t_start, 1)},
    }
    RESULTS_ROOT.mkdir(exist_ok=True)
    path = RESULTS_ROOT / "twin_benchmark.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"replay {n_rep}/{len(rep_rows)} · duplicate {n_dup}/{len(dup)} · clean with match {fa}/{len(clean)}; "
          f"wrote {path}")


if __name__ == "__main__":
    main()
