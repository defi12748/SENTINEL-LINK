"""Re-score a saved benchmark without re-running it.

    py -m sentinel.bench.rescore [results/benchmark.json]

Applies the current scoring rules to the per-recording rows already stored
in the JSON: interference detections must match the jammer in frequency, and
headline rates get 95 % Wilson intervals. Nothing is re-measured; rows saved
before the bandwidth was recorded use the widest bandwidth the scenario draws
(400 Hz), which can only make the frequency criterion more lenient.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .. import RESULTS_ROOT
from .run import FREQ_TOL_HZ, freq_tolerance, interference_summary, wilson

MAX_SCENARIO_BW_HZ = 400.0


def rescore(b: dict) -> dict:
    fd = b["frame_detection"]
    for part in (fd["attacked_passes"], fd["combined"]):
        part["detection_rate_ci95"] = wilson(part["tp"], part["tp"] + part["fn"])
        part["false_alarm_rate_ci95"] = wilson(part["fp"], part["fp"] + part["tn"])
    it = b["interference"]
    for r in it["cases"]:
        r.setdefault("any_overlap", r["detected"])
        bw = r.get("bw_hz", MAX_SCENARIO_BW_HZ)
        err = r["freq_error_hz"]
        # freq_error_hz is the error of the closest overlapping alarm
        r["detected"] = bool(r["any_overlap"] and err is not None and err <= freq_tolerance(r["kind"], bw))
    it.update(interference_summary(it["cases"]))
    it["frequency_tolerance_hz"] = f"{FREQ_TOL_HZ:g} (+ half the bandwidth for nbnoise/chirp)"
    it["clean_recordings_with_alarm_ci95"] = wilson(it["clean_recordings_with_alarm"], it["clean_recordings"])
    b["rescored"] = "frequency-matched interference scoring and Wilson intervals applied to saved rows"
    return b


def main(argv: list[str]) -> None:
    path = Path(argv[0]) if argv else RESULTS_ROOT / "benchmark.json"
    b = rescore(json.loads(path.read_text(encoding="utf-8")))
    path.write_text(json.dumps(b, indent=2), encoding="utf-8")
    it = b["interference"]
    print(f"interference: {it['detection_rate']} {it['detection_rate_ci95']} "
          f"(any alarm overlap {it['any_alarm_overlap_rate']}); wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
