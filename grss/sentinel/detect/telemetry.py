"""Telemetry-content head.

Housekeeping telemetry (battery, solar, temperatures, counters) moves slowly
within a pass. Each frame is compared with the median of its in-pass
neighbours; deviations are scaled by per-field noise learned on clean
training passes, and the resulting vector is scored by PyOD's ECOD
(parameter-free, empirical-CDF outlier detector) fitted on clean frames.
This head is what remains when an attacker forges a clock-consistent counter
on a frame taken from another pass.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pyod.models.ecod import ECOD

from ..decode import funcube

FIELDS = [
    "photo_voltage_x_mv", "photo_voltage_y_mv", "photo_voltage_z_mv", "photo_current_ma",
    "battery_voltage_mv", "system_current_ma", "reboot_count", "software_errors",
    "boost_temp_1_c", "boost_temp_2_c", "boost_temp_3_c", "battery_temp_c",
]
NEIGHBOURS = 4


def telemetry_matrix(payloads: list[bytes]) -> np.ndarray:
    rows = []
    for p in payloads:
        fr = funcube.parse(p)
        rows.append([fr.telemetry[k] for k in FIELDS] if fr else [np.nan] * len(FIELDS))
    return np.array(rows, float)


def neighbour_deviation(M: np.ndarray, k: int = NEIGHBOURS) -> np.ndarray:
    n = len(M)
    D = np.zeros_like(M)
    for i in range(n):
        nb = [j for j in range(max(0, i - k), min(n, i + k + 1)) if j != i]
        D[i] = M[i] - np.nanmedian(M[nb], axis=0) if nb else 0.0
    return np.nan_to_num(D)


@dataclass
class TelemetryModel:
    scale: np.ndarray
    ecod: ECOD
    score_ref: np.ndarray     # sorted clean ECOD scores, for an empirical p-value

    @classmethod
    def fit(cls, passes_payloads: list[list[bytes]]) -> "TelemetryModel":
        D = np.vstack([neighbour_deviation(telemetry_matrix(p)) for p in passes_payloads])
        scale = 1.4826 * np.median(np.abs(D), axis=0)
        scale = np.maximum(scale, np.maximum(1.0, 0.25 * np.std(D, axis=0)))
        Z = np.abs(D) / scale
        ecod = ECOD().fit(Z)
        return cls(scale, ecod, np.sort(ecod.decision_scores_))

    def features(self, payloads: list[bytes]) -> dict[str, np.ndarray]:
        Z = np.abs(neighbour_deviation(telemetry_matrix(payloads))) / self.scale
        score = self.ecod.decision_function(Z)
        # fraction of clean frames scoring higher (empirical tail probability)
        tail = 1.0 - np.searchsorted(self.score_ref, score) / len(self.score_ref)
        return {"tele_max_z": Z.max(axis=1), "tele_ecod_tail": -np.log10(np.maximum(tail, 1e-4))}
