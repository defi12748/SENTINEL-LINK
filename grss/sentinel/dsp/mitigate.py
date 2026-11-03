"""Response: remove a detected narrowband interferer before (re)decoding.

``tf_excise`` works in the time–frequency plane: a cell is removed only when it
stands well above both its column (the instant) and its row's long-term level
(the frequency), so swept, pulsed and CW jammers are all followed, while the
steady BPSK spectrum — including its ±600 Hz lines — is left in place.
``excise`` (notch / band-stop) is kept for comparison.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt, iirnotch, istft, sosfiltfilt, stft

from .spectral import HOP, NPERSEG

TF_NPERSEG = 1024


def tf_excise(x: np.ndarray, fs: int, start_s: float = 0.0, end_s: float | None = None,
              band: tuple[float, float] = (300.0, 20000.0), col_db: float = 12.0, row_db: float = 8.0) -> np.ndarray:
    end_s = len(x) / fs if end_s is None else end_s
    f, t, Z = stft(x, fs=fs, nperseg=TF_NPERSEG, noverlap=TF_NPERSEG * 3 // 4)
    P = np.abs(Z) ** 2 + 1e-20
    rows = (f >= band[0]) & (f <= band[1])
    cols = (t >= start_s - 1.0) & (t <= end_s + 1.0)
    col_med = np.median(P[rows], axis=0, keepdims=True)
    # long-term level per frequency, from the part of the recording outside the alarm
    quiet = ~cols if (~cols).sum() > 20 else np.ones_like(cols)
    row_med = np.median(P[:, quiet], axis=1, keepdims=True)
    mask = (P > col_med * 10 ** (col_db / 10)) & (P > row_med * 10 ** (row_db / 10))
    mask &= rows[:, None] & cols[None, :]
    # dilate by one bin in frequency to catch leakage
    mask[1:] |= mask[:-1]
    mask[:-1] |= mask[1:]
    Z = np.where(mask, 0, Z)
    _, y = istft(Z, fs=fs, nperseg=TF_NPERSEG, noverlap=TF_NPERSEG * 3 // 4)
    y = y[: len(x)]
    if len(y) < len(x):
        y = np.pad(y, (0, len(x) - len(y)))
    return y.astype(x.dtype)


def estimate_width(x: np.ndarray, fs: int, f0: float, start_s: float, end_s: float) -> float:
    seg = x[int(start_s * fs): int(end_s * fs)]
    f, _, Z = stft(seg, fs=fs, nperseg=NPERSEG, noverlap=NPERSEG - HOP)
    p = 10 * np.log10((np.abs(Z) ** 2).mean(axis=1) + 1e-20)
    k = int(np.argmin(np.abs(f - f0)))
    k = max(range(max(0, k - 3), min(len(f), k + 4)), key=lambda i: p[i])
    floor = np.median(p[max(0, k - 200): k + 200])
    half = floor + (p[k] - floor) / 2
    lo = hi = k
    while lo > 0 and p[lo - 1] > half:
        lo -= 1
    while hi < len(f) - 1 and p[hi + 1] > half:
        hi += 1
    return float(max(f[hi] - f[lo], f[1] - f[0]))


def excise(x: np.ndarray, fs: int, f0: float, width_hz: float, start_s: float = 0.0,
           end_s: float | None = None) -> np.ndarray:
    """Notch (tone-like) or band-stop (wider) at f0 over the alarm interval."""
    end_s = len(x) / fs if end_s is None else end_s
    i0, i1 = int(max(0, start_s - 1) * fs), int(min(len(x) / fs, end_s + 1) * fs)
    y = x.copy()
    if width_hz <= 40:
        b, a = iirnotch(f0, Q=max(5.0, f0 / 30.0), fs=fs)
        y[i0:i1] = filtfilt(b, a, x[i0:i1])
    else:
        lo, hi = max(10.0, f0 - 0.6 * width_hz), min(fs / 2 - 10, f0 + 0.6 * width_hz)
        sos = butter(6, [lo, hi], btype="bandstop", fs=fs, output="sos")
        y[i0:i1] = sosfiltfilt(sos, x[i0:i1])
    return y.astype(x.dtype)
