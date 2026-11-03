"""Spectral evidence for narrowband interference in recorded audio.

Per analysis window we compute an STFT (≈11.7 Hz bins) and measure, for
every frequency bin, how far it stands above a running median baseline
(*prominence*), how stationary its envelope is (*spectral kurtosis*: −1 for
a constant-envelope tone, 0 for Gaussian noise) and how persistently it is
elevated over time. The BPSK downlink itself produces two natural lines at
``fc ± baud/2``; they are reported separately and their *imbalance* is a
feature, so a jammer parked on one of them is still visible.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import stft

NPERSEG = 4096
HOP = 2048
BAND = (300.0, 20000.0)   # SatNOGS audio passband actually used
LINE_GUARD_HZ = 35.0

FEATURE_NAMES = [
    "max_prom_db",          # strongest narrow excess outside the BPSK lines
    "max_prom_sk",          # spectral kurtosis at that bin (≈ -1 for CW)
    "max_prom_persist",     # fraction of time the bin is ≥ 6 dB above baseline
    "max_prom_bw_hz",       # contiguous width above half prominence
    "n_peaks_6db",          # number of bins ≥ 6 dB above baseline
    "min_sk",               # most tone-like bin in band
    "line_imbalance_db",    # |prom(fc-600) - prom(fc+600)|
    "line_max_db",          # stronger of the two BPSK lines
    "band_flatness",        # spectral flatness inside the signal band
    "inband_excess_db",     # strongest excess inside fc ± 1.2 kHz (outside lines)
    # 30 s context — separates frequency-static (added) from drifting (natural) emitters
    "stable_line_db",       # max over bins of the per-bin median prominence
    "stable_line_duty",     # fraction of time that bin is ≥ 6 dB up (pulsed jammers)
    "plateau_db",           # ~100 Hz-smoothed spectrum over a 3 kHz baseline (narrowband noise)
    "bpsk_asymmetry_db",    # max |S(fc+d) - S(fc-d)|, d = 30..1500 Hz (jammer inside the signal band)
]
CONTEXT_S = 30.0


@dataclass
class WindowSpectrum:
    f: np.ndarray
    power: np.ndarray         # (bins, frames)
    baseline_db: np.ndarray
    prom_db: np.ndarray


def stft_power(x: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    f, t, Z = stft(x, fs=fs, nperseg=NPERSEG, noverlap=NPERSEG - HOP, boundary=None, padded=False)
    return f, t, (np.abs(Z) ** 2).astype(np.float32)


def analyse(f: np.ndarray, P: np.ndarray) -> WindowSpectrum:
    mean_db = 10 * np.log10(P.mean(axis=1) + 1e-20)
    baseline = median_filter(mean_db, size=129, mode="nearest")
    return WindowSpectrum(f, P, baseline, mean_db - baseline)


def exclusion_mask(f: np.ndarray, exclude: list[tuple[float, float]] | None) -> np.ndarray:
    """Bins inside known station-RFI ranges (learned from the station's own past recordings)."""
    m = np.zeros(len(f), bool)
    for lo, hi in exclude or []:
        m |= (f >= lo) & (f <= hi)
    return m


def window_features(ws: WindowSpectrum, fc: float, baud: float = 1200.0,
                    excl: np.ndarray | None = None) -> np.ndarray:
    f, P, prom = ws.f, ws.power, ws.prom_db
    band = (f > BAND[0]) & (f < BAND[1])
    if excl is not None:
        band = band & ~excl
    near_line = (np.abs(f - (fc - baud / 2)) < LINE_GUARD_HZ) | (np.abs(f - (fc + baud / 2)) < LINE_GUARD_HZ)
    cand = band & ~near_line

    m = P.mean(axis=1) + 1e-20
    sk = (P ** 2).mean(axis=1) / m ** 2 - 2.0

    idx = np.flatnonzero(cand)
    k = idx[np.argmax(prom[idx])]
    base_lin = 10 ** (ws.baseline_db[k] / 10)
    persist = float(np.mean(P[k] > base_lin * 10 ** 0.6))
    half = prom[k] / 2
    lo = k
    while lo > 0 and prom[lo - 1] > half:
        lo -= 1
    hi = k
    while hi < len(f) - 1 and prom[hi + 1] > half:
        hi += 1
    bw = float((hi - lo + 1) * (f[1] - f[0]))

    def line_prom(fl: float) -> float:
        sel = np.abs(f - fl) < LINE_GUARD_HZ
        return float(prom[sel].max()) if sel.any() else 0.0

    l1, l2 = line_prom(fc - baud / 2), line_prom(fc + baud / 2)
    sig = band & (np.abs(f - fc) < baud)
    flat = float(np.exp(np.mean(np.log(m[sig]))) / np.mean(m[sig])) if sig.any() else 1.0
    inband = sig & ~near_line
    inband_excess = float(prom[inband].max()) if inband.any() else 0.0

    return np.array([
        prom[k], sk[k], persist, bw, float(np.sum(prom[cand] >= 6.0)), float(sk[band].min()),
        abs(l1 - l2), max(l1, l2), flat, inband_excess,
    ], dtype=np.float32)


def context_features(f: np.ndarray, P: np.ndarray, fc: float, baud: float = 1200.0,
                     excl: np.ndarray | None = None) -> np.ndarray:
    """Evidence over a long (≈30 s) context."""
    df = f[1] - f[0]
    mean_db = 10 * np.log10(P.mean(axis=1) + 1e-20)
    baseline = median_filter(mean_db, size=129, mode="nearest")
    band = (f > BAND[0]) & (f < BAND[1])
    if excl is not None:
        band = band & ~excl
    near_line = (np.abs(f - (fc - baud / 2)) < LINE_GUARD_HZ) | (np.abs(f - (fc + baud / 2)) < LINE_GUARD_HZ)
    cand = band & ~near_line
    prom_ft = 10 * np.log10(P + 1e-20) - baseline[:, None]
    med = np.median(prom_ft, axis=1) + 1.59        # +1.59 dB: median of an exponential vs its mean
    idx = np.flatnonzero(cand)
    k = idx[np.argmax(med[idx])]
    duty = float(np.mean(prom_ft[k] >= 6.0))
    # plateau: smooth over ~100 Hz, compare with a wide (3 kHz) baseline
    n_s = max(3, int(round(100 / df)) | 1)
    smooth = np.convolve(mean_db, np.ones(n_s) / n_s, mode="same")
    wide = median_filter(mean_db, size=max(5, int(3000 / df)) | 1, mode="nearest")
    outside_signal = cand & (np.abs(f - fc) > baud + 100)   # the BPSK hump is a natural plateau
    plateau = float(np.max((smooth - wide)[outside_signal]))
    # BPSK spectral symmetry around fc
    sm = np.convolve(mean_db, np.ones(5) / 5, mode="same")
    asym = 0.0
    for d in np.arange(30.0, 1500.0, df):
        lo, hi = int(round((fc - d) / df)), int(round((fc + d) / df))
        if 0 <= lo < len(f) and hi < len(f):
            if abs(d - baud / 2) < LINE_GUARD_HZ:
                continue
            asym = max(asym, abs(sm[hi] - sm[lo]))
    return np.array([float(med[k]), duty, plateau, asym], dtype=np.float32)


def windowed_features(x: np.ndarray, fs: int, fc: float, win_s: float = 5.0, hop_s: float = 2.5,
                      exclude: list[tuple[float, float]] | None = None) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Features for overlapping windows. Returns (centres_s, X, peak_info)."""
    f, t, P = stft_power(x, fs)
    excl = exclusion_mask(f, exclude)
    cols_per_win = max(4, int(win_s * fs / HOP))
    cols_hop = max(1, int(hop_s * fs / HOP))
    ctx = max(cols_per_win, int(CONTEXT_S * fs / HOP))
    centres, feats, peaks = [], [], []
    for s in range(0, P.shape[1] - cols_per_win + 1, cols_hop):
        ws = analyse(f, P[:, s:s + cols_per_win])
        c0 = max(0, s + cols_per_win // 2 - ctx // 2)
        cf = context_features(f, P[:, c0:c0 + ctx], fc, excl=excl)
        feats.append(np.concatenate([window_features(ws, fc, excl=excl), cf]))
        band = (f > BAND[0]) & (f < BAND[1]) & ~excl
        k = np.flatnonzero(band)[np.argmax(ws.prom_db[band])]
        peaks.append({"freq_hz": float(f[k]), "prom_db": float(ws.prom_db[k])})
        centres.append(float(t[s] + win_s / 2))
    return np.array(centres), np.vstack(feats) if feats else np.zeros((0, len(FEATURE_NAMES))), peaks
