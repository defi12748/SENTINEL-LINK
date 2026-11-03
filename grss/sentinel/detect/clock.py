"""Clock-consistency head: on-board frame counter vs. reception time.

For AO-73 the frame position ``P = seq*24 + type`` advances once per
transmitted frame (period ≈ 4.9885 s, fitted from the public archive). A
two-parameter model ``P ≈ a + b·t`` learned on training passes predicts the
counter of every authentic frame to about one frame. Two scales of evidence:

* pass offset ``c`` = median residual of the pass: catches whole-recording
  replays from earlier passes (and on-board reboots/counter resets, which we
  route to a verification request rather than an alarm);
* frame residual ``u_i = r_i - c``: catches in-pass replays (counter behind
  the clock by the replay delay) and injected frames with forged counters.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

T_REF = 1.79e9  # keeps the regression well conditioned
PASS_TOLERANCE_FRAMES = 10.0  # 50 s: clock-model drift allowance between refits


@dataclass
class ClockModel:
    a: float
    b: float                 # frames per second
    frame_sigma: float       # robust std of in-pass residuals (frames)
    pass_sigma: float        # robust std of per-pass offsets (frames)
    n_frames: int
    n_passes: int

    @property
    def period_s(self) -> float:
        return 1.0 / self.b

    def predict(self, t_utc: np.ndarray) -> np.ndarray:
        return self.a + self.b * (np.asarray(t_utc) - T_REF)

    def residuals(self, t_utc: np.ndarray, position: np.ndarray) -> np.ndarray:
        return np.asarray(position, float) - self.predict(t_utc)

    @classmethod
    def fit(cls, passes: list[tuple[np.ndarray, np.ndarray]], iters: int = 5) -> "ClockModel":
        """``passes``: list of (t_utc, position) arrays, one per pass."""
        t = np.concatenate([p[0] for p in passes])
        P = np.concatenate([p[1] for p in passes]).astype(float)
        keep = np.ones(len(t), bool)
        a = b = 0.0
        for _ in range(iters):  # iteratively trimmed least squares
            A = np.vstack([np.ones(keep.sum()), t[keep] - T_REF]).T
            (a, b), *_ = np.linalg.lstsq(A, P[keep], rcond=None)
            r = P - (a + b * (t - T_REF))
            mad = 1.4826 * np.median(np.abs(r[keep] - np.median(r[keep])))
            keep = np.abs(r) < max(6 * mad, 3.0)
        offsets, inner = [], []
        for tp, Pp in passes:
            r = np.asarray(Pp, float) - (a + b * (tp - T_REF))
            c = np.median(r)
            offsets.append(c)
            inner.append(r - c)
        inner = np.concatenate(inner)
        frame_sigma = 1.4826 * np.median(np.abs(inner)) or 0.3
        pass_sigma = 1.4826 * np.median(np.abs(np.array(offsets) - np.median(offsets))) or 0.5
        return cls(float(a), float(b), float(max(frame_sigma, 0.25)), float(max(pass_sigma, 0.3)),
                   int(len(t)), len(passes))

    def to_dict(self) -> dict:
        return {**self.__dict__, "period_s": self.period_s}


def frame_features(model: ClockModel, t_utc: np.ndarray, position: np.ndarray) -> dict[str, np.ndarray]:
    """Per-frame clock evidence for one pass (frames in reception order)."""
    t_utc = np.asarray(t_utc, float)
    P = np.asarray(position, float)
    n = len(P)
    r = model.residuals(t_utc, P)
    c = float(np.median(r)) if n else 0.0
    u = r - c
    # counter regression: frame not ahead of everything already received
    running_max = np.maximum.accumulate(np.concatenate([[-np.inf], P[:-1]])) if n else P
    behind = P <= running_max
    # duplicated positions inside the pass
    _, inv, counts = np.unique(P, return_inverse=True, return_counts=True)
    dup = counts[inv] > 1 if n else np.zeros(0, bool)
    # disagreement between counter step and time step to each neighbour
    step_err = np.zeros(n)
    if n > 1:
        e = np.diff(P) - np.diff(t_utc) * model.b
        step_err[1:] = np.abs(e)
        step_err[:-1] = np.maximum(step_err[:-1], np.abs(e))
    return {
        "u_frames": u,
        "u_sigma": u / model.frame_sigma,
        # Replays put the counter *behind* the clock; authentic outliers seen in
        # the archive are small and *ahead* (audio dropouts), so keep the sign.
        "u_behind": np.maximum(0.0, -u) / model.frame_sigma,
        "u_ahead": np.maximum(0.0, u) / model.frame_sigma,
        "pass_offset_sigma": np.full(n, c / model.pass_sigma),
        # Cross-pass replays are hundreds to thousands of frames off; the model
        # extrapolated to later dates drifts by a few frames, so only the excess
        # over PASS_TOLERANCE counts.
        "pass_offset_excess": np.full(n, max(0.0, abs(c) - PASS_TOLERANCE_FRAMES)),
        "behind": behind.astype(float),
        "duplicate": dup.astype(float),
        "step_err": step_err,
    }
