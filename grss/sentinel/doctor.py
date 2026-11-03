"""Check a native or container installation before running the demo."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from importlib.metadata import version

from .data.corpus import corpus_root
from .decode import grsat
from .nasa import onair_bridge
from .train import MODEL_PATH, load_models
from .trust.ccsds_tm import cryptolib_available


def inspect(verify_data: bool = False, require_nasa: bool = False) -> dict:
    checks = {}
    def check(name, action, required=True):
        try:
            detail = action()
            checks[name] = {"ok": bool(detail), "required": required, "detail": detail}
        except Exception as error:
            checks[name] = {"ok": False, "required": required, "detail": str(error)}
    check("trained_models", lambda: MODEL_PATH.is_file() and bool(load_models()))
    check("gr_satellites", grsat.available)
    check("NASA_OnAIR", onair_bridge.available, require_nasa)
    check("NASA_CryptoLib", cryptolib_available, require_nasa)
    root = corpus_root()
    missing, invalid = [], []
    manifest = root / "manifest.json"
    if manifest.exists():
        observations = json.loads(manifest.read_text(encoding="utf-8"))["observations"]
        for obs in observations:
            d = root / f"obs_{obs['observation_id']}"
            for name in ("record.json", "decoded.json", "tracks.npz"):
                if not (d / name).is_file(): missing.append(f"{d.name}/{name}")
            files = [(obs["audio_file"], obs["audio_sha256"])] if obs.get("audio_file") else []
            files += [(frame["file"], frame["sha256"]) for frame in obs["frames"]]
            for name, expected in files:
                path = root / name
                if not path.is_file(): missing.append(name)
                elif verify_data and hashlib.sha256(path.read_bytes()).hexdigest() != expected: invalid.append(name)
        checks["dataset"] = {"ok": bool(observations) and not missing and not invalid, "required": True,
                             "observations": len(observations), "missing": missing, "invalid_sha256": invalid,
                             "hashes_verified": verify_data}
    else:
        checks["dataset"] = {"ok": False, "required": True, "detail": "Run python -m sentinel fetch"}
    return {"ok": all(c["ok"] for c in checks.values() if c["required"]),
            "python": platform.python_version(), "platform": platform.system(),
            "versions": {name: version(name) for name in ("numpy", "scipy", "scikit-learn", "fastapi")},
            "checks": checks}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sentinel doctor")
    parser.add_argument("--verify-data", action="store_true")
    parser.add_argument("--require-nasa", action="store_true")
    args = parser.parse_args(argv)
    result = inspect(args.verify_data, args.require_nasa)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1
