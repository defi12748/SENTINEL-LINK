"""Physical-layer splice head.

The demodulator's carrier track (FLL) follows the residual Doppler of the
pass, a smooth curve; the level track follows elevation and fading. Audio cut
from another moment of the pass — or from another pass entirely — carries
the Doppler and level of *that* moment, so a replay shows up as

* a step in carrier frequency / level at the frame boundary, and
* a carrier offset of the frame relative to a smooth whole-pass Doppler fit.

Statistics are scaled by noise measured on the same track (MAD of first
differences), so the head adapts to each station's FLL jitter.
"""

from __future__ import annotations

import numpy as np

RATE = 10.0          # track samples per second
GAP = 0.4            # ignore this much either side of the boundary
SPAN = 2.5           # compare medians over this span


def _robust_sigma(x: np.ndarray) -> float:
    d = np.diff(x[np.isfinite(x)])
    return float(1.4826 * np.median(np.abs(d - np.median(d)))) + 1e-6


def _step(track: np.ndarray, centre_s: float) -> float:
    i = int(centre_s * RATE)
    g, s = int(GAP * RATE), int(SPAN * RATE)
    before = track[max(0, i - g - s): max(0, i - g)]
    after = track[i + g: i + g + s]
    if len(before) < 3 or len(after) < 3:
        return 0.0
    return float(np.median(after) - np.median(before))


def smooth_fit(t: np.ndarray, y: np.ndarray, deg: int = 3, iters: int = 3) -> np.ndarray:
    keep = np.isfinite(y)
    fit = np.zeros_like(y)
    for _ in range(iters):
        c = np.polyfit(t[keep], y[keep], deg)
        fit = np.polyval(c, t)
        r = y - fit
        mad = 1.4826 * np.median(np.abs(r[keep]))
        keep = np.isfinite(y) & (np.abs(r) < 4 * mad + 1e-9)
    return fit


def frame_features(track_t: np.ndarray, carrier_hz: np.ndarray, level_db: np.ndarray,
                   frame_t_rec: np.ndarray, slot_guard_s: float = 0.3,
                   frame_len_s: float = 4.33) -> dict[str, np.ndarray]:
    # Only the part of the track where the signal is present is meaningful.
    sig = level_db > np.percentile(level_db, 20)
    c = np.where(sig, carrier_hz, np.nan)
    sc, sl = _robust_sigma(c), _robust_sigma(level_db)
    fit = smooth_fit(track_t, c)
    resid = c - fit
    resid_sigma = 1.4826 * np.nanmedian(np.abs(resid)) + 1e-6
    c_filled = np.where(np.isfinite(c), c, fit)

    step_c, step_l, off_c = [], [], []
    for t0 in frame_t_rec:
        b = t0 - slot_guard_s
        step_c.append(abs(_step(c_filled, b)) / sc)
        step_l.append(abs(_step(level_db, b)) / sl)
        i0, i1 = int(t0 * RATE), int((t0 + frame_len_s) * RATE)
        seg = resid[i0:i1]
        off_c.append(abs(float(np.nanmedian(seg))) / resid_sigma if np.isfinite(seg).any() else 0.0)
    return {"splice_carrier_step": np.array(step_c), "splice_level_step": np.array(step_l),
            "carrier_offset": np.array(off_c)}
