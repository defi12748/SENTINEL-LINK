"""Duplicate-audio ("noise twin") head.

A genuine recording never contains the same stretch of receiver noise twice:
thermal noise is new at every instant, and the downlink's residual Doppler
keeps moving. Audio replayed inside a file (a copied run of frame slots, or a
single slot re-sent in place of the next) is a sample-for-sample copy of an
earlier stretch, noise included, so it correlates with its source almost
perfectly while any two authentic stretches do not.

The test needs no decoder, no frame format and no trained model, so it works
on any satellite's recording. It says *that* two stretches are copies, not
which one is the original; the clock head (counter behind the clock) answers
that for AO-73, and otherwise the later copy is the presumed replay.

Method: mix the downlink band to complex baseband, decimate to 1 kHz, whiten
with the file's own spectrum, and cross-correlate 2 s query blocks against
the whole recording by FFT. Normalised peaks away from the query's own
position are block matches; blocks matching at the same lag are merged into
one duplicated segment.
Swapped slots are a permutation, not a copy, and are not seen here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from scipy import fft as sfft
from scipy.ndimage import uniform_filter1d
from scipy.signal import resample_poly

DECIMATE = 48        # 48 kHz audio -> 1 kHz complex baseband around the downlink
BLOCK_S = 2.0        # query length and hop
THRESHOLD = 0.5      # normalised correlation; fixed a priori, not fitted (clean maxima: bench.twin)
LAG_TOL_S = 0.01     # blocks within this lag of each other belong to one copy
MIN_ENERGY = 0.05    # skip blocks below this fraction of the median block energy (silence)
WHITEN_BINS = 33     # smoothing of the whitening spectrum (bins of the whole-file FFT)


@dataclass
class TwinMatch:
    start_s: float       # duplicated (later) segment
    end_s: float
    src_start_s: float   # where the same audio occurs earlier
    lag_s: float
    ncc: float           # strongest normalised correlation in the segment
    blocks: int


@dataclass
class TwinResult:
    matches: list[TwinMatch]
    block_ncc: np.ndarray        # best off-diagonal correlation per query block
    block_t: np.ndarray          # block start times (s)
    ms: float = 0.0

    def covers(self, t_s: np.ndarray) -> np.ndarray:
        """Per time instant: inside a duplicated segment (either copy)."""
        t_s = np.asarray(t_s, float)
        out = np.zeros(len(t_s), bool)
        for m in self.matches:
            out |= (t_s >= m.start_s) & (t_s < m.end_s)
            out |= (t_s >= m.src_start_s) & (t_s < m.src_start_s + (m.end_s - m.start_s))
        return out


def baseband(x: np.ndarray, fs: int, fc: float) -> tuple[np.ndarray, float]:
    # single precision: a 7-min recording is 20 M samples
    phase = (np.arange(len(x)) * (fc / fs) % 1.0).astype(np.float32)
    z = x.astype(np.float32) * np.exp(np.complex64(-2j * np.pi) * phase)
    return resample_poly(z, 1, DECIMATE).astype(np.complex64), fs / DECIMATE


def detect(x: np.ndarray, fs: int, fc: float, threshold: float = THRESHOLD) -> TwinResult:
    t0 = time.perf_counter()
    z, rate = baseband(x, fs, fc)
    L = int(BLOCK_S * rate)
    n = len(z)
    if n < 3 * L:
        return TwinResult([], np.zeros(0), np.zeros(0), (time.perf_counter() - t0) * 1e3)
    nfft = sfft.next_fast_len(n + L)
    # Whiten with the recording's own long-term spectrum (PHAT). It is one
    # fixed filter for the whole file, so a copy stays a copy, but steady
    # tones and lines (CW jammers, birdies, an unmodulated carrier) no longer
    # make distant blocks look alike.
    Z = sfft.fft(z, nfft, workers=-1)
    mag = uniform_filter1d(np.abs(Z), WHITEN_BINS, mode="wrap")
    z = sfft.ifft(Z / (mag + 1e-12 * mag.max()), workers=-1)[:n].astype(np.complex64)
    S = sfft.fft(z, nfft, workers=-1)
    # energy of every length-L window, for normalisation
    c = np.concatenate([[0.0], np.cumsum(np.abs(z) ** 2)])
    win_e = c[L:] - c[:-L]
    starts = np.arange(0, n - L + 1, L)
    block_e = win_e[starts]
    floor = MIN_ENERGY * np.median(block_e)
    best = np.zeros(len(starts))
    lags = np.zeros(len(starts), int)
    for i, q0 in enumerate(starts):
        if block_e[i] <= floor:
            continue
        q = z[q0:q0 + L]
        corr = sfft.ifft(S * np.conj(sfft.fft(q, nfft, workers=-1)), workers=-1)[: n - L + 1]
        ncc = np.abs(corr) / (np.sqrt(block_e[i] * np.maximum(win_e, floor)) + 1e-30)
        ncc[max(0, q0 - L + 1): q0 + L] = 0.0      # the block itself and its overlaps
        k = int(np.argmax(ncc))
        best[i], lags[i] = ncc[k], k
    matches: list[TwinMatch] = []
    tol = int(LAG_TOL_S * rate)
    for i in np.flatnonzero(best >= threshold):
        q0, k = int(starts[i]), int(lags[i])
        a, b = (q0, k) if q0 > k else (k, q0)     # report the later copy as the duplicate
        lag = a - b
        m = matches[-1] if matches else None
        if m is not None and abs(m.lag_s * rate - lag) <= tol and a / rate <= m.end_s + BLOCK_S:
            m.end_s = max(m.end_s, (a + L) / rate)
            m.start_s = min(m.start_s, a / rate)
            m.src_start_s = min(m.src_start_s, b / rate)
            m.ncc = max(m.ncc, float(best[i]))
            m.blocks += 1
        else:
            matches.append(TwinMatch(a / rate, (a + L) / rate, b / rate, lag / rate, float(best[i]), 1))
    matches = _merge(matches, tol / rate)
    return TwinResult(matches, best, starts / rate, (time.perf_counter() - t0) * 1e3)


def _merge(matches: list[TwinMatch], tol_s: float) -> list[TwinMatch]:
    """Each copy is found twice (from the source block and from the copy);
    keep one segment per (lag, position)."""
    out: list[TwinMatch] = []
    for m in sorted(matches, key=lambda m: (round(m.lag_s, 1), m.start_s)):
        o = out[-1] if out else None
        if o is not None and abs(o.lag_s - m.lag_s) <= tol_s and m.start_s <= o.end_s + BLOCK_S:
            o.start_s, o.end_s = min(o.start_s, m.start_s), max(o.end_s, m.end_s)
            o.src_start_s = min(o.src_start_s, m.src_start_s)
            o.ncc, o.blocks = max(o.ncc, m.ncc), o.blocks + m.blocks
        else:
            out.append(TwinMatch(**m.__dict__))
    return sorted(out, key=lambda m: m.start_s)
