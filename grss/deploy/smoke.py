"""Exercise the real API, including repeat-cache serving and audit verification.

python deploy/smoke.py --api http://127.0.0.1:8000 --out results/runtime_smoke.json
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--out")
    args = parser.parse_args()
    checks, timings = {}, {}
    def request(name, path, body=None):
        started = time.perf_counter()
        response = requests.get(args.api + path, timeout=300) if body is None else requests.post(args.api + path, json=body, timeout=300)
        response.raise_for_status()
        timings[name] = round((time.perf_counter() - started) * 1000, 2)
        return response.json()
    health = request("health", "/api/health")
    assert health["models"] and health["gr_satellites"] and health["observations"] == 30
    checks["runtime_ready"] = True
    observations = request("observations", "/api/observations")
    assert len(observations) == 30
    body = {"observation_id": 15261075, "seed": 7, "variant": "standard"}
    first = request("scenario_first", "/api/scenario", body)
    second = request("scenario_repeat", "/api/scenario", body)
    assert all(first[key] == second[key] for key in ("frames", "truth", "score", "spectrogram"))
    assert first["run_id"] != second["run_id"] and first["ledger_head"] != second["ledger_head"]
    assert second["cache"]["status"] == "memory"
    checks["cache_preserves_analysis_and_fresh_audit"] = True
    for service in ("AUTH", "AUTH_ENC"):
        demo = request(service, "/api/sdls/demo", {"observation_id": 15261075, "service": service})
        assert all(row["verdict"] != "ACCEPT" for row in demo["log"] if row["step"] != "downlink")
        checks[service + "_rejects_replay_and_injection"] = True
    interop = request("cryptolib", "/api/cryptolib/interop")
    assert interop["available"] and interop["byte_identical"] and all(test["ok"] for test in interop["checks"])
    checks["NASA_CryptoLib_interoperability"] = True
    assert second["onair"]["available"] and second["onair"]["frames"]
    checks["NASA_OnAIR_runs"] = True
    log = request("ledger", "/api/ledger")
    assert log["verification"]["valid"]
    checks["ledger_valid"] = True
    result = {"generated_utc": datetime.now(timezone.utc).isoformat(), "checks": checks, "timing_ms": timings,
              "scenario_score": second["score"], "jammer_detected": second["interference"]["detected_truth"]}
    print(json.dumps(result, indent=2))
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
