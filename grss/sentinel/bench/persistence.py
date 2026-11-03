"""Choose the interference persistence rule on calibration data, then report
it on the held-out recordings.

    py -m sentinel.bench.persistence      # -> results/interference_persistence.json

Rule family (``detect.interference.alarm_runs``): an alarm needs at least
``min_windows`` consecutive windows above the calibrated threshold,
optionally with a stable peak frequency. Selection uses only the three
training recordings that set the threshold (``train.py``: last 3 of the
training split), clean and with jammers drawn as in training. Pre-registered
criterion: keep detection within 5 points of the single-window rule and
minimise alarm episodes per hour on clean audio; ties go to the smaller rule.
The held-out rows are reported for every rule, selected or not.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

from .. import RESULTS_ROOT
from ..detect.interference import alarm_runs
from ..dsp.audio import load_audio
from ..redteam import attacks, scenario
from ..train import load_models
from .run import freq_tolerance, wilson

GRID = [(k, tol) for tol in (None, 50.0) for k in (1, 2, 3, 4, 6)]
CAL_JAMMERS = 8


def _meta(d) -> tuple[float, str]:
    fc = json.loads((d / "decoded.json").read_text())["f_offset_hz"]
    return fc, json.loads((d / "record.json").read_text())["station_name"]


def _window_evidence(model, y, fs, fc, station) -> dict:
    r = model.detect(y, fs, fc, station=station)
    return {"centres": r.centres_s, "p": r.prob, "freqs": r.freqs, "minutes": len(y) / fs / 60}


def _score(model, clean: list[dict], jammed: list[tuple[dict, dict]], k: int, tol) -> dict:
    episodes = sum(len(alarm_runs(c["centres"], c["p"], c["freqs"], model.threshold, k, tol)) for c in clean)
    alarmed = sum(bool(alarm_runs(c["centres"], c["p"], c["freqs"], model.threshold, k, tol)) for c in clean)
    hits = 0
    for ev, ti in jammed:
        s, e = ti["start_s"], ti["start_s"] + ti["dur_s"]
        al = alarm_runs(ev["centres"], ev["p"], ev["freqs"], model.threshold, k, tol)
        hits += any(a.end_s > s and a.start_s < e and abs(a.freq_hz - ti["freq_hz"]) <= freq_tolerance(ti["kind"], ti["bw_hz"])
                    for a in al)
    hours = sum(c["minutes"] for c in clean) / 60
    return {"min_windows": k, "freq_tol_hz": tol,
            "clean_recordings_with_alarm": alarmed, "clean_recordings": len(clean),
            "clean_recordings_with_alarm_ci95": wilson(alarmed, len(clean)),
            "clean_alarm_episodes_per_hour": round(episodes / hours, 2),
            "jammed_detected": hits, "jammed": len(jammed),
            "detection_rate": round(hits / len(jammed), 4) if jammed else None,
            "detection_rate_ci95": wilson(hits, len(jammed))}


def main() -> None:
    model = load_models().interference
    train_dirs, test_dirs = scenario.split()
    cal_dirs = train_dirs[-3:]
    rng = np.random.default_rng(2)

    cal_clean, cal_jammed = [], []
    for d in cal_dirs:
        x, fs = load_audio(d / "audio.ogg")
        fc, st = _meta(d)
        cal_clean.append(_window_evidence(model, x, fs, fc, st))
        for _ in range(CAL_JAMMERS):
            xj, ti = attacks.add_interference(x, fs, fc, scenario._draw_interference(rng, fc, len(x) / fs), rng)
            cal_jammed.append((_window_evidence(model, xj, fs, fc, st), ti))
        print(f"  calibration {d.name} done")

    test_clean, test_jammed = [], []
    for d in test_dirs:
        x, fs = load_audio(d / "audio.ogg")
        fc, st = _meta(d)
        test_clean.append(_window_evidence(model, x, fs, fc, st))
        for seed in (1000, 1001, 1002):            # the benchmark's draws
            att = scenario.apply(d, seed, "standard")
            if "interference" in att.truth:
                test_jammed.append((_window_evidence(model, att.audio, fs, fc, st), att.truth["interference"]))
        print(f"  held-out {d.name} done")

    cal = [_score(model, cal_clean, cal_jammed, k, tol) for k, tol in GRID]
    base = next(r for r in cal if r["min_windows"] == 1 and r["freq_tol_hz"] is None)
    ok = [r for r in cal if r["detection_rate"] >= base["detection_rate"] - 0.05]
    chosen = min(ok, key=lambda r: (r["clean_alarm_episodes_per_hour"], r["min_windows"], r["freq_tol_hz"] is not None))
    held = [_score(model, test_clean, test_jammed, k, tol) for k, tol in GRID]
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "threshold": model.threshold, "calibration_observations": [d.name for d in cal_dirs],
           "criterion": "detection within 5 points of the single-window rule; fewest clean alarm episodes per hour",
           "selected": {"min_windows": chosen["min_windows"], "freq_tol_hz": chosen["freq_tol_hz"]},
           "calibration": cal, "held_out": held}
    path = RESULTS_ROOT / "interference_persistence.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    sel = next(r for r in held if (r["min_windows"], r["freq_tol_hz"]) == (chosen["min_windows"], chosen["freq_tol_hz"]))
    print(f"selected {out['selected']} on calibration; held-out: {sel}; wrote {path}")


if __name__ == "__main__":
    main()
