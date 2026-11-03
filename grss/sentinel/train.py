"""Train every model on the training split only and save the bundle.

    py -m sentinel.train            # writes models/sentinel_models.joblib
"""

from __future__ import annotations

import json

import joblib
import numpy as np

from . import PROJECT_ROOT
from .data.corpus import load_pass
from .detect import clock, fusion
from .detect.interference import HOP_S, WIN_S, InterferenceModel, station_ranges
from .detect.telemetry import TelemetryModel
from .dsp.audio import load_audio
from .dsp.spectral import windowed_features
from .pipeline import Models, frame_evidence
from .redteam import attacks, scenario

MODELS_DIR = PROJECT_ROOT / "models"
MODEL_PATH = MODELS_DIR / "sentinel_models.joblib"
JAMMERS_PER_PASS = 8
# Jammers this far below the in-band noise are physically invisible in every
# STFT bin; keeping them as positives only teaches the model label noise.
# (The benchmark still evaluates every J/S.)
MIN_TRAIN_JN_DB = -22.0
FORGERIES_PER_PASS = 6


def _clock_inputs(p):
    parsed = p.parsed()
    idx = [i for i, f in enumerate(parsed) if f]
    return p.t_utc[idx], np.array([parsed[i].position for i in idx])


def _station(d) -> str:
    return json.loads((d / "record.json").read_text(encoding="utf-8"))["station_name"]


def interference_dataset(dirs, seed: int, station_rfi: dict | None = None, with_jammers: bool = True):
    """Windows of real clean audio (negatives) and the same audio with
    synthetic jammers (positives), with each station's known RFI masked."""
    rng = np.random.default_rng(seed)
    station_rfi = station_rfi or {}
    X, y, clean = [], [], []
    for d in dirs:
        x, fs = load_audio(d / "audio.ogg")
        fc = json.loads((d / "decoded.json").read_text())["f_offset_hz"]
        excl = station_rfi.get(_station(d), [])
        c, F, _ = windowed_features(x, fs, fc, WIN_S, HOP_S, exclude=excl)
        X.append(F)
        y.append(np.zeros(len(F), bool))
        clean.append(F)
        for _ in range(JAMMERS_PER_PASS if with_jammers else 0):
            spec = scenario._draw_interference(rng, fc, len(x) / fs)
            xj, tr = attacks.add_interference(x, fs, fc, spec, rng)
            hidden = any(lo <= tr["freq_hz"] <= hi for lo, hi in excl)
            if tr["jn_db"] < MIN_TRAIN_JN_DB or hidden:
                continue
            c, F, _ = windowed_features(xj, fs, fc, WIN_S, HOP_S, exclude=excl)
            s, e = tr["start_s"], tr["start_s"] + tr["dur_s"]
            overlap = (c + WIN_S / 2 > s + 1.0) & (c - WIN_S / 2 < e - 1.0)
            X.append(F[overlap])
            y.append(np.ones(overlap.sum(), bool))
    return np.vstack(X), np.concatenate(y), np.vstack(clean)


def site_survey(model: InterferenceModel, dirs) -> dict[str, list[tuple[float, float]]]:
    """Per-station ranges of recurring narrowband emitters in clean recordings."""
    peaks: dict[str, list[float]] = {}
    for d in dirs:
        x, fs = load_audio(d / "audio.ogg")
        fc = json.loads((d / "decoded.json").read_text())["f_offset_hz"]
        c, F, pk = windowed_features(x, fs, fc, WIN_S, HOP_S)
        p = model.clf.predict_proba(F)[:, 1]
        peaks.setdefault(_station(d), []).extend(pk[i]["freq_hz"] for i in np.flatnonzero(p >= 0.5))
    return {st: station_ranges(fr) for st, fr in peaks.items() if station_ranges(fr)}


def main() -> None:
    train_dirs, test_dirs = scenario.split()
    print(f"train observations: {len(train_dirs)}  held-out: {len(test_dirs)}")
    clean = [load_pass(d) for d in train_dirs]

    clock_model = clock.ClockModel.fit([_clock_inputs(p) for p in clean])
    print(f"clock: period {clock_model.period_s:.5f} s, frame sigma {clock_model.frame_sigma:.2f}, "
          f"pass sigma {clock_model.pass_sigma:.2f} frames ({clock_model.n_frames} frames)")
    tele_model = TelemetryModel.fit([p.payloads for p in clean])

    # Interference, two passes: (1) fit, (2) site survey of each training
    # station's recurring emitters, (3) refit and calibrate on masked evidence.
    # Fit on 10 passes, set the alarm threshold on 3 others.
    fit_dirs, cal_dirs = train_dirs[:-3], train_dirs[-3:]
    Xi, yi, _ = interference_dataset(fit_dirs, seed=1)
    _, _, Xcal = interference_dataset(cal_dirs, seed=2, with_jammers=False)
    first = InterferenceModel.fit(Xi, yi, Xcal, target_fpr=0.005)
    survey = site_survey(first, train_dirs)
    print(f"site survey: {survey}")
    Xi, yi, _ = interference_dataset(fit_dirs, seed=1, station_rfi=survey)
    _, _, Xcal = interference_dataset(cal_dirs, seed=2, station_rfi=survey, with_jammers=False)
    intf_model = InterferenceModel.fit(Xi, yi, Xcal, target_fpr=0.005)
    intf_model.station_rfi = survey
    print(f"interference: {len(yi)} windows ({yi.mean():.0%} jammed), threshold {intf_model.threshold:.3f}")

    # Fusion: attacked training passes (decoded through the real chain).
    partial = Models(clock_model, tele_model, intf_model, fusion.FusionModel.fit(
        np.zeros((2, len(fusion.FEATURES))), np.array([0, 1])))
    Xs, ys = [], []
    for k, d in enumerate(train_dirs):
        for seed in (11, 12):
            ap = scenario.build(d, seed, "standard")
            f, _ = frame_evidence(partial, ap.pass_)
            Xs.append(fusion.design_matrix(f))
            ys.append(ap.labels)
        donor = train_dirs[(k + 3) % len(train_dirs)]
        ap = scenario.build(d, 13, "cross_pass_replay", donor_dir=donor)
        f, _ = frame_evidence(partial, ap.pass_)
        Xs.append(fusion.design_matrix(f))
        ys.append(ap.labels)
        f, _ = frame_evidence(partial, clean[k])
        Xs.append(fusion.design_matrix(f))
        ys.append(np.zeros(len(clean[k].payloads), bool))
        # Frame-level forgeries (counter rewritten to look fresh / pushed ahead),
        # so fusion learns to use the telemetry evidence, not only the clock.
        rng = np.random.default_rng(100 + k)
        donors = clean[(k + 3) % len(clean)].payloads
        for _ in range(FORGERIES_PER_PASS):
            i = int(rng.integers(1, len(clean[k].payloads) - 1))
            pl, lab = attacks.frames_content_forge(clean[k].payloads, i, donors[int(rng.integers(0, len(donors)))])
            f, _ = frame_evidence(partial, type(clean[k])(**{**clean[k].__dict__, "payloads": pl}))
            Xs.append(fusion.design_matrix(f)[[i]])
            ys.append(lab[[i]])
            pl, lab = attacks.frames_counter_forge(clean[k].payloads, i, int(rng.integers(1, 400)))
            f, _ = frame_evidence(partial, type(clean[k])(**{**clean[k].__dict__, "payloads": pl}))
            Xs.append(fusion.design_matrix(f)[[i]])
            ys.append(lab[[i]])
        print(f"  fusion data from {d.name}")
    X, y = np.vstack(Xs), np.concatenate(ys)
    fusion_model = fusion.FusionModel.fit(X, y)
    print(f"fusion: {len(y)} frames ({y.mean():.1%} attacked); weights {fusion_model.weights()}")

    MODELS_DIR.mkdir(exist_ok=True)
    bundle = Models(clock_model, tele_model, intf_model, fusion_model)
    joblib.dump({"models": bundle, "train": [d.name for d in train_dirs], "test": [d.name for d in test_dirs]},
                MODEL_PATH)
    (MODELS_DIR / "model_card.json").write_text(json.dumps({
        "train_observations": [d.name for d in train_dirs],
        "held_out_observations": [d.name for d in test_dirs],
        "clock": clock_model.to_dict(),
        "interference": {"threshold": intf_model.threshold, "target_window_fpr": intf_model.target_fpr,
                         "train_windows": int(len(yi)), "station_rfi_ranges_hz": intf_model.station_rfi},
        "fusion_weights": fusion_model.weights(),
    }, indent=2), encoding="utf-8")
    print(f"saved {MODEL_PATH}")


def load_models() -> Models:
    return joblib.load(MODEL_PATH)["models"]


if __name__ == "__main__":
    main()
