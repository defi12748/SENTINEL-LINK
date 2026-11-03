"""Audio I/O and carrier estimation for SatNOGS recordings."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import welch


def load_audio(path: str | Path) -> tuple[np.ndarray, int]:
    """Load a mono float32 recording (.ogg/.wav/.flac)."""
    x, fs = sf.read(str(path), dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    return x, int(fs)


def save_wav(path: str | Path, x: np.ndarray, fs: int) -> None:
    peak = float(np.max(np.abs(x))) or 1.0
    scale = 0.95 / peak if peak > 0.95 else 1.0
    sf.write(str(path), x * scale, fs, subtype="PCM_16")


def estimate_bpsk_center(x: np.ndarray, fs: int, baud: float = 1200.0,
                         search: tuple[float, float] = (2000.0, 20000.0)) -> float:
    """Centre frequency of a BPSK signal in real audio.

    BPSK with NRZ data shows spectral lines/lobes at ``fc ± baud/2``; we pick
    the ``fc`` maximising the summed excess power at both lobes, which is
    robust to a single narrowband interferer sitting on one side.
    """
    f, p = welch(x, fs, nperseg=1 << 14)
    pdb = 10 * np.log10(p + 1e-20)
    floor = np.median(pdb[(f > search[0]) & (f < search[1])])
    excess = np.clip(pdb - floor, 0, None)
    df = f[1] - f[0]
    half = baud / 2
    best, best_fc = -1.0, (search[0] + search[1]) / 2
    for fc in np.arange(search[0] + half, search[1] - half, df):
        lo = excess[int(round((fc - half) / df))]
        hi = excess[int(round((fc + half) / df))]
        score = min(lo, hi)  # both lobes must be present
        if score > best:
            best, best_fc = score, fc
    return float(best_fc)
