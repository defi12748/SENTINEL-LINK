"""Standard Track 1 scenario on real recordings, plus evasion variants.

Standard test (challenge text): replay a valid 5–20-frame subsequence,
inject one sequence anomaly, add narrowband interference digitally at a
hidden SNR. We draw every parameter at random (length, positions, anomaly
kind, jammer kind/frequency/J/S/timing), apply it to the real audio, then run
the *real* decoder on the attacked audio. Results are cached by a hash of
(observation, seed, variant).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import DATA_ROOT
from ..cache import cache_key
from ..data.corpus import Pass, corpus_root, iso_to_unix
from ..decode import grsat
from ..dsp.audio import estimate_bpsk_center, load_audio
from . import attacks

CACHE = DATA_ROOT / "attacked"
VARIANTS = ("standard", "cross_pass_replay", "clean")


@dataclass
class AttackedPass:
    pass_: Pass
    labels: np.ndarray              # per decoded frame: True = attacked
    label_kind: list[str]           # "", "replay", "sequence"
    truth: dict                     # attack parameters
    audio: np.ndarray | None = None
    fs: int = 48000


def _draw_interference(rng: np.random.Generator, fc: float, dur: float) -> attacks.Interference:
    kind = rng.choice(["cw", "nbnoise", "chirp", "pulsed"])
    if rng.random() < 0.35:               # on or next to the downlink
        freq = fc + rng.uniform(-1500, 1500)
    else:
        freq = rng.uniform(1500, 18500)
    partial = rng.random() < 0.5
    start = rng.uniform(0, dur * 0.6) if partial else 0.0
    length = rng.uniform(30, max(31, dur - start)) if partial else None
    return attacks.Interference(kind=str(kind), freq_hz=float(freq), js_db=float(rng.uniform(-30, 10)),
                                bw_hz=float(rng.uniform(20, 400)), start_s=float(start), dur_s=length,
                                pulse_period_s=float(rng.uniform(0.2, 3.0)), duty=float(rng.uniform(0.2, 0.7)))


def _plan(t: np.ndarray, rng: np.random.Generator) -> tuple[int, int, int, int]:
    """(n_replay, src_idx, dst_idx, seq_idx) on decoded-frame indices."""
    n = len(t)
    n_rep = int(rng.integers(5, min(20, max(5, (n - 4) // 2)) + 1))
    src = int(rng.integers(0, max(1, n - 2 * n_rep - 2)))
    dst = int(rng.integers(src + n_rep, max(src + n_rep + 1, n - n_rep)))
    free = [i for i in range(n - 1) if not (dst - 1 <= i < dst + n_rep) and not (src <= i < src + n_rep)]
    seq = int(rng.choice(free)) if free else max(0, dst - 3)
    return n_rep, src, dst, seq


@dataclass
class AttackedAudio:
    audio: np.ndarray
    fs: int
    truth: dict                                 # attack parameters
    intervals: list[tuple[float, float, str]]   # (start_s, end_s, kind) of replay / sequence edits


def apply(obs_dir: Path, seed: int, variant: str = "standard", donor_dir: Path | None = None,
          overrides: dict | None = None) -> AttackedAudio:
    """The attacked recording only, without decoding it (no GNU Radio needed).
    ``overrides`` (Attack Lab) may set: replay/sequence/interference (bool),
    n_replay, seq_variant ("duplicate"|"swap"), jam_kind, jam_freq_hz, js_db."""
    ov = overrides or {}
    rec = json.loads((obs_dir / "record.json").read_text(encoding="utf-8"))
    dec = json.loads((obs_dir / "decoded.json").read_text(encoding="utf-8"))
    x, fs = load_audio(obs_dir / "audio.ogg")
    t = np.array([f["t_rec"] for f in dec["frames"]])
    # Seed with (seed, observation): every recording gets its own hidden parameters.
    rng = np.random.default_rng([seed, int(rec["observation_id"])])
    fc = dec["f_offset_hz"]
    truth: dict = {"variant": variant, "seed": seed, "observation_id": rec["observation_id"]}
    intervals: list[tuple[float, float, str]] = []
    y = x

    if variant in ("standard", "cross_pass_replay") and len(t) >= 14:
        n_rep, src, dst, seq = _plan(t, rng)
        tr: dict | None = None
        if "n_replay" in ov:
            n_rep = int(np.clip(ov["n_replay"], 5, 20))
            src = min(src, max(0, len(t) - 2 * n_rep - 1))
            dst = int(np.clip(dst, src + n_rep, max(src + n_rep, len(t) - n_rep)))
        if not ov.get("replay", True):
            pass  # Attack Lab: replay disabled
        elif variant == "cross_pass_replay" and donor_dir is not None:
            dx, _ = load_audio(donor_dir / "audio.ogg")
            dd = json.loads((donor_dir / "decoded.json").read_text(encoding="utf-8"))
            dt = np.array([f["t_rec"] for f in dd["frames"]])
            src = int(rng.integers(0, max(1, len(dt) - n_rep)))
            y, tr = attacks.replay_overwrite(y, fs, t, n_rep, src, dst, source=dx, source_frame_t=dt)
            tr["donor_observation"] = int(dd["observation_id"])
        else:
            y, tr = attacks.replay_overwrite(y, fs, t, n_rep, src, dst)
        if tr is not None:
            truth["replay"] = tr
            intervals.append((tr["dst_start_s"], tr["dst_end_s"], "replay"))
        if variant == "standard":
            dup = rng.random() < 0.5
            if "seq_variant" in ov:
                dup = ov["seq_variant"] == "duplicate"
            if ov.get("sequence", True):
                if dup and seq + 1 < len(t):
                    y, tq = attacks.slot_duplicate(y, fs, t, seq)
                else:
                    y, tq = attacks.slot_swap(y, fs, t, min(seq, len(t) - 2))
                truth["sequence"] = tq
                intervals.append((tq["dst_start_s"], tq["dst_end_s"], "sequence"))
            spec = _draw_interference(rng, fc, len(x) / fs)
            for k_ov, k_spec in (("jam_kind", "kind"), ("jam_freq_hz", "freq_hz"), ("js_db", "js_db")):
                if k_ov in ov:
                    setattr(spec, k_spec, ov[k_ov])
            if ov.get("interference", True):
                y, ti = attacks.add_interference(y, fs, fc, spec, rng)
                truth["interference"] = ti
    return AttackedAudio(y, fs, truth, intervals)


def build(obs_dir: Path, seed: int, variant: str = "standard", donor_dir: Path | None = None,
          keep_audio: bool = False, overrides: dict | None = None) -> AttackedPass:
    """The attacked recording decoded by the full chain, with per-frame labels."""
    ov = overrides or {}
    rec = json.loads((obs_dir / "record.json").read_text(encoding="utf-8"))
    att = apply(obs_dir, seed, variant, donor_dir, overrides)
    y, fs, truth, intervals = att.audio, att.fs, att.truth, att.intervals

    dependencies = [Path(__file__), Path(attacks.__file__), Path(grsat.__file__)]
    for source_dir in [obs_dir] + ([donor_dir] if donor_dir else []):
        dependencies.extend(source_dir / name for name in ("audio.ogg", "decoded.json", "record.json"))
    key = cache_key("attacked-decode/5", {"observation": rec["observation_id"], "seed": seed,
                    "variant": variant, "overrides": ov}, dependencies)[:32]
    cache = CACHE / f"{rec['observation_id']}_{variant}_{key}.json"
    if cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
    else:
        start = iso_to_unix(rec["start"])
        res = grsat.decode_audio(y, fs, start, f_offset=estimate_bpsk_center(y, fs))
        cached = {"frames": [{"t_rec": f.t_rec, "hex": f.payload.hex()} for f in res.frames],
                  "track_t": res.track_t.tolist(), "carrier_hz": res.carrier_hz.tolist(),
                  "level_db": res.level_db.tolist(), "f_offset_hz": res.f_offset_hz,
                  "truth": truth}
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(cached), encoding="utf-8")

    t_rec = np.array([f["t_rec"] for f in cached["frames"]])
    labels = np.zeros(len(t_rec), bool)
    kind = [""] * len(t_rec)
    for s, e, k in intervals:
        m = attacks.labels_for_interval(t_rec, s, e)
        labels |= m
        for i in np.flatnonzero(m):
            kind[i] = kind[i] or k
    p = Pass(observation_id=rec["observation_id"], station=rec["station_name"], start_utc=iso_to_unix(rec["start"]),
             t_rec=t_rec, payloads=[bytes.fromhex(f["hex"]) for f in cached["frames"]],
             track_t=np.array(cached["track_t"]), carrier_hz=np.array(cached["carrier_hz"]),
             level_db=np.array(cached["level_db"]), tle=(rec["tle1"], rec["tle2"]),
             station_lla=(rec["station_lat"], rec["station_lng"], rec["station_alt"]))
    return AttackedPass(p, labels, kind, cached["truth"], y if keep_audio else None, fs)


def split(norad_id: int = 39444) -> tuple[list[Path], list[Path]]:
    """Held-out split: test = observations on/after 15 Oct 2026, or from a
    station that never appears in training. Train = the rest."""
    root = corpus_root(norad_id)
    dirs = sorted(d for d in root.glob("obs_*") if (d / "decoded.json").exists())
    recs = {d: json.loads((d / "record.json").read_text(encoding="utf-8")) for d in dirs}
    early = [d for d in dirs if recs[d]["start"] < "2026-10-15"]
    train = [d for d in early if sum(recs[e]["station_name"] == recs[d]["station_name"] for e in early) > 1]
    test = [d for d in dirs if d not in train]
    return train, test
