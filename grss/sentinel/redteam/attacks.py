"""Controlled adversarial transformations of *real* recordings and frame
streams. Every function returns the attacked data plus a ground-truth dict.

Audio-level (what the jury's held-out recording will contain):
  * ``replay_overwrite``  — a 5–20 frame stretch of earlier audio (same pass
    or another pass) overwrites later frame slots, cut on frame boundaries so
    the replayed frames decode cleanly.
  * ``slot_duplicate`` / ``slot_swap`` — single-frame sequence anomalies.
  * ``add_interference``  — CW / narrowband noise / chirp / pulsed tone at a
    hidden jammer-to-signal ratio (J/S, signal measured in the BPSK band).

Frame-level (organizer-supplied telemetry, and evasion variants):
  * ``frames_replay``, ``frames_counter_forge``, ``frames_content_forge``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np
from scipy.signal import welch

from ..decode import funcube

GUARD_S = 0.30          # cut this far before a frame start (inside the idle gap)
SLOT_S = 4.9885         # AO-73 frame period


# ----------------------------------------------------------------- helpers
def band_powers(x: np.ndarray, fs: int, fc: float, half_bw: float = 1200.0) -> tuple[float, float]:
    """(signal power in fc±half_bw, noise power in the same bandwidth)."""
    f, p = welch(x, fs, nperseg=1 << 14)
    df = f[1] - f[0]
    noise_density = float(np.median(p[(f > 3000) & (f < 19000)]))
    sel = np.abs(f - fc) < half_bw
    total = float(p[sel].sum() * df)
    noise = noise_density * 2 * half_bw
    return max(total - noise, noise * 1e-3), noise


@dataclass
class Interference:
    kind: str = "cw"           # cw | nbnoise | chirp | pulsed
    freq_hz: float = 11000.0
    js_db: float = -10.0       # jammer / signal power
    bw_hz: float = 100.0       # nbnoise bandwidth or chirp span
    start_s: float = 0.0
    dur_s: float | None = None
    pulse_period_s: float = 1.0
    duty: float = 0.5


def add_interference(x: np.ndarray, fs: int, fc: float, spec: Interference,
                     rng: np.random.Generator) -> tuple[np.ndarray, dict]:
    s_pow, n_pow = band_powers(x, fs, fc)
    j_pow = s_pow * 10 ** (spec.js_db / 10)
    n = len(x)
    i0 = int(spec.start_s * fs)
    i1 = n if spec.dur_s is None else min(n, i0 + int(spec.dur_s * fs))
    t = np.arange(i1 - i0) / fs
    if spec.kind == "cw":
        j = np.cos(2 * np.pi * spec.freq_hz * t + rng.uniform(0, 2 * np.pi))
    elif spec.kind == "pulsed":
        gate = ((t % spec.pulse_period_s) < spec.duty * spec.pulse_period_s).astype(float)
        j = np.cos(2 * np.pi * spec.freq_hz * t + rng.uniform(0, 2 * np.pi)) * gate / np.sqrt(spec.duty)
    elif spec.kind == "chirp":
        period = 10.0
        f_inst = spec.freq_hz + spec.bw_hz / 2 * np.sin(2 * np.pi * t / period)
        j = np.cos(2 * np.pi * np.cumsum(f_inst) / fs)
    elif spec.kind == "nbnoise":
        w = rng.standard_normal(len(t))
        W = np.fft.rfft(w)
        fr = np.fft.rfftfreq(len(t), 1 / fs)
        W[np.abs(fr - spec.freq_hz) > spec.bw_hz / 2] = 0
        j = np.fft.irfft(W, len(t))
    else:
        raise ValueError(spec.kind)
    j = j / np.sqrt(np.mean(j ** 2) + 1e-20) * np.sqrt(j_pow)
    y = x.copy()
    y[i0:i1] += j.astype(x.dtype)
    truth = {"attack": "interference", **spec.__dict__, "dur_s": (i1 - i0) / fs,
             "signal_power": s_pow, "noise_power": n_pow, "jn_db": float(10 * np.log10(j_pow / n_pow))}
    return y, truth


def _slot_start(t_frame: float) -> float:
    return max(0.0, t_frame - GUARD_S)


def replay_overwrite(x: np.ndarray, fs: int, frame_t: np.ndarray, n_frames: int, src_idx: int,
                     dst_idx: int, source: np.ndarray | None = None,
                     source_frame_t: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """Overwrite the audio starting at frame ``dst_idx`` with ``n_frames``
    frame slots taken from frame ``src_idx`` of ``source`` (default: the same
    recording, i.e. an in-pass replay)."""
    source = x if source is None else source
    source_frame_t = frame_t if source_frame_t is None else source_frame_t
    s0 = int(_slot_start(source_frame_t[src_idx]) * fs)
    d0 = int(_slot_start(frame_t[dst_idx]) * fs)
    length = int(n_frames * SLOT_S * fs)
    length = min(length, len(source) - s0, len(x) - d0)
    y = x.copy()
    y[d0:d0 + length] = source[s0:s0 + length]
    truth = {"attack": "replay", "cross_pass": source is not x, "n_frames": n_frames,
             "src_start_s": s0 / fs, "dst_start_s": d0 / fs, "dst_end_s": (d0 + length) / fs}
    return y, truth


def slot_duplicate(x: np.ndarray, fs: int, frame_t: np.ndarray, idx: int) -> tuple[np.ndarray, dict]:
    """Frame slot ``idx`` is transmitted again in place of slot ``idx+1``."""
    y, tr = replay_overwrite(x, fs, frame_t, 1, idx, idx + 1)
    return y, {**tr, "attack": "sequence", "variant": "duplicate"}


def slot_swap(x: np.ndarray, fs: int, frame_t: np.ndarray, idx: int) -> tuple[np.ndarray, dict]:
    a0, b0 = int(_slot_start(frame_t[idx]) * fs), int(_slot_start(frame_t[idx + 1]) * fs)
    L = int(SLOT_S * fs)
    y = x.copy()
    y[a0:a0 + L], y[b0:b0 + L] = x[b0:b0 + L].copy(), x[a0:a0 + L].copy()
    return y, {"attack": "sequence", "variant": "swap", "dst_start_s": a0 / fs, "dst_end_s": (b0 + L) / fs}


def labels_for_interval(t_rec: np.ndarray, start_s: float, end_s: float) -> np.ndarray:
    """Frames whose start falls inside an attacked interval."""
    return (t_rec >= start_s - 0.05) & (t_rec < end_s - 1.0)


# ------------------------------------------------------------ frame level
def frames_replay(t: np.ndarray, payloads: list[bytes], n_frames: int, src_idx: int,
                  dst_idx: int) -> tuple[list[bytes], np.ndarray]:
    out = list(payloads)
    lab = np.zeros(len(payloads), bool)
    for k in range(n_frames):
        if dst_idx + k < len(out) and src_idx + k < len(payloads):
            out[dst_idx + k] = payloads[src_idx + k]
            lab[dst_idx + k] = True
    return out, lab


def frames_counter_forge(payloads: list[bytes], idx: int, delta_frames: int) -> tuple[list[bytes], np.ndarray]:
    out = list(payloads)
    fr = funcube.parse(out[idx])
    pos = fr.position + delta_frames
    out[idx] = funcube.with_position(out[idx], pos // funcube.FRAMES_PER_SET, pos % funcube.FRAMES_PER_SET)
    lab = np.zeros(len(out), bool)
    lab[idx] = True
    return out, lab


def frames_content_forge(payloads: list[bytes], idx: int, donor: bytes) -> tuple[list[bytes], np.ndarray]:
    """Evasion: a frame from another pass with its counter rewritten to the
    expected value, so the clock head cannot see it. Only content/physics
    evidence remains."""
    out = list(payloads)
    target = funcube.parse(out[idx])
    out[idx] = funcube.with_position(donor, target.sequence, target.frame_type)
    lab = np.zeros(len(out), bool)
    lab[idx] = True
    return out, lab
