"""Per-frame fusion: calibrated probability that a frame is not authentic,
and the response it triggers.

Inputs are the evidence vectors of the clock, telemetry and splice heads.
A logistic regression on bounded, log-scaled features keeps the model
transparent (one weight per evidence type, reported in the docs) and its
output is Platt-calibrated by construction. Responses:

* ``ACCEPT``      p < p_verify
* ``VERIFY``      p_verify ≤ p < p_quarantine — request confirmation (e.g. a
                  second station's recording of the same pass)
* ``QUARANTINE``  p ≥ p_quarantine — withheld from the analyst
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression

FEATURES = [
    "u_behind", "u_ahead", "behind", "duplicate", "step_err", "pass_offset_excess",
    "tele_max_z", "tele_ecod_tail",
    "splice_carrier_step", "splice_level_step", "carrier_offset",
]
CLIP = {"u_behind": 50, "u_ahead": 50, "step_err": 20, "pass_offset_excess": 50, "tele_max_z": 50,
        "tele_ecod_tail": 4, "splice_carrier_step": 50, "splice_level_step": 50, "carrier_offset": 50}


def design_matrix(feats: dict[str, np.ndarray]) -> np.ndarray:
    cols = []
    for name in FEATURES:
        v = np.abs(np.asarray(feats[name], float))
        v = np.clip(v, 0, CLIP.get(name, 1.0))
        cols.append(np.log1p(v))
    return np.vstack(cols).T


@dataclass
class FusionModel:
    clf: LogisticRegression
    p_verify: float = 0.5
    p_quarantine: float = 0.9

    @classmethod
    def fit(cls, X: np.ndarray, y: np.ndarray) -> "FusionModel":
        # No class re-weighting: it would bias the output away from a calibrated probability.
        clf = LogisticRegression(C=1.0, max_iter=2000).fit(X, y)
        return cls(clf)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.clf.predict_proba(X)[:, 1] if len(X) else np.zeros(0)

    def decide(self, p: np.ndarray) -> list[str]:
        return ["QUARANTINE" if q >= self.p_quarantine else "VERIFY" if q >= self.p_verify else "ACCEPT" for q in p]

    def weights(self) -> dict[str, float]:
        return {n: float(w) for n, w in zip(FEATURES, self.clf.coef_[0])} | {"bias": float(self.clf.intercept_[0])}
