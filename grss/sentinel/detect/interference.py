"""Interference head: calibrated narrowband-interference classifier.

Trained on windows of *real* SatNOGS audio (negatives) and the same audio
with synthetic narrowband interference of random kind, frequency and hidden
J/S (positives). Gradient-boosted trees on the spectral evidence vector,
isotonic-calibrated so the output is a probability. The alarm threshold is
set on clean calibration windows for a target false-alarm rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier

from ..dsp.spectral import FEATURE_NAMES, windowed_features

WIN_S, HOP_S = 5.0, 2.5


@dataclass
class InterferenceAlarm:
    start_s: float
    end_s: float
    peak_prob: float
    freq_hz: float


@dataclass
class InterferenceResult:
    centres_s: np.ndarray
    prob: np.ndarray
    alarms: list[InterferenceAlarm] = field(default_factory=list)
    freqs: np.ndarray = field(default_factory=lambda: np.zeros(0))   # strongest peak per window (Hz)

    @property
    def recording_prob(self) -> float:
        return float(self.prob.max()) if len(self.prob) else 0.0


@dataclass
class InterferenceModel:
    clf: CalibratedClassifierCV
    threshold: float
    target_fpr: float
    # Site survey: frequency ranges of recurring emitters per station, learned
    # from that station's past (training) recordings. Masked from the evidence.
    station_rfi: dict[str, list[tuple[float, float]]] = field(default_factory=dict)

    @classmethod
    def fit(cls, X: np.ndarray, y: np.ndarray, X_cal_clean: np.ndarray,
            target_fpr: float = 0.005) -> "InterferenceModel":
        base = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=31,
                                              l2_regularization=1.0, random_state=0)
        # Balance the classes so the calibrated output is not inflated by the
        # jammed-window majority of the synthetic training set.
        w = np.where(y, 0.5 / max(1, y.sum()), 0.5 / max(1, (~y).sum())) * len(y)
        clf = CalibratedClassifierCV(base, method="isotonic", cv=3).fit(X, y, sample_weight=w)
        scores = np.sort(clf.predict_proba(X_cal_clean)[:, 1])
        k = int(np.ceil((1 - target_fpr) * len(scores))) - 1
        threshold = float(min(0.999, max(0.5, scores[max(0, k)] + 1e-6)))
        return cls(clf, threshold, target_fpr)

    def detect(self, x: np.ndarray, fs: int, fc: float, station: str | None = None) -> InterferenceResult:
        exclude = self.station_rfi.get(station or "", [])
        centres, X, peaks = windowed_features(x, fs, fc, WIN_S, HOP_S, exclude=exclude)
        if len(X) == 0:
            return InterferenceResult(centres, np.zeros(0))
        p = self.clf.predict_proba(X)[:, 1]
        freqs = np.array([pk["freq_hz"] for pk in peaks])
        # bundles pickled before the persistence rule existed alarm on single windows
        alarms = alarm_runs(centres, p, freqs, self.threshold, getattr(self, "min_windows", 1),
                            getattr(self, "freq_tol_hz", None))
        return InterferenceResult(centres, p, alarms, freqs)


def alarm_runs(centres: np.ndarray, p: np.ndarray, freqs: np.ndarray, threshold: float,
               min_windows: int = 1, freq_tol_hz: float | None = None) -> list[InterferenceAlarm]:
    """Alarms from runs of consecutive windows above the threshold. A run
    must hold ``min_windows`` windows (with ``freq_tol_hz``: windows whose
    strongest peak stays within that distance of the run's median peak), so
    a lone window on a passing spur is not an alarm while a jammer, which
    lasts, still is. Frequency of an alarm = peak of its most probable window."""
    alarms: list[InterferenceAlarm] = []
    above = p >= threshold
    i, n = 0, len(p)
    while i < n:
        if not above[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and above[j + 1]:
            j += 1
        run = np.arange(i, j + 1)
        support = len(run)
        if freq_tol_hz is not None:
            support = int((np.abs(freqs[run] - np.median(freqs[run])) <= freq_tol_hz).sum())
        if support >= min_windows:
            k = run[int(np.argmax(p[run]))]
            s, e = float(centres[i] - WIN_S / 2), float(centres[j] + WIN_S / 2)
            if alarms and s <= alarms[-1].end_s:      # runs one window apart still touch: one alarm
                a = alarms[-1]
                a.end_s = e
                if p[k] > a.peak_prob:
                    a.peak_prob, a.freq_hz = float(p[k]), float(freqs[k])
            else:
                alarms.append(InterferenceAlarm(s, e, float(p[k]), float(freqs[k])))
        i = j + 1
    return alarms


MAX_RANGE_HZ = 1500.0


def station_ranges(peak_freqs: list[float], pad_hz: float = 150.0, min_hits: int = 2) -> list[tuple[float, float]]:
    """Merge the peak frequencies of a station's alarmed clean windows into ranges.
    Ranges wider than MAX_RANGE_HZ are drifting emitters, not fixed spurs: masking
    them would blind the detector, so they are left in (and cost false alarms)."""
    fs_sorted = sorted(peak_freqs)
    ranges: list[list[float]] = []
    for f in fs_sorted:
        if ranges and f - ranges[-1][1] <= 2 * pad_hz:
            ranges[-1][1] = f
            ranges[-1][2] += 1
        else:
            ranges.append([f, f, 1])
    return [(lo - pad_hz, hi + pad_hz) for lo, hi, n in ranges
            if n >= min_hits and hi - lo + 2 * pad_hz <= MAX_RANGE_HZ]


def feature_names() -> list[str]:
    return list(FEATURE_NAMES)
