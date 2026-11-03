"""One-command reproduction.

    py -m sentinel fetch      # SatNOGS AO-73 observations (+ audio, SHA-256 verified)
    py -m sentinel decode     # our chain: audio -> gr-satellites -> AO-40 blocks
    py -m sentinel train      # models on the training split
    py -m sentinel bench      # held-out benchmark -> results/benchmark.json
    py -m sentinel serve      # API on :8000 for the web console
    py -m sentinel doctor [--verify-data] [--require-nasa]  # installation checks
    py -m sentinel analyse <recording.ogg|frames.kss|frames.txt> [--start ISO] [--out r.json]
    py -m sentinel db init|verify  # PostgreSQL schema / stored ledger check (SENTINEL_DATABASE_URL)
"""

from __future__ import annotations

import hashlib
import sys


def _verify_or_fetch() -> None:
    from .data import satnogs
    from .data.corpus import corpus_root
    root = corpus_root()
    manifest = root / "manifest.json"
    if not manifest.exists():
        satnogs.build_dataset(39444, count=30, min_frames=15, with_audio=True)
        return
    import json
    m = json.loads(manifest.read_text(encoding="utf-8"))
    session = satnogs._session()
    for obs in m["observations"]:
        path = root / (obs["audio_file"] or "")
        valid = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == obs["audio_sha256"]
        if obs["audio_file"] and not valid:
            print(f"fetching audio for {obs['observation_id']}")
            blob = satnogs._get(session, obs["audio_url"]).content
            if hashlib.sha256(blob).hexdigest() != obs["audio_sha256"]:
                raise RuntimeError(f"audio SHA-256 mismatch for observation {obs['observation_id']}")
            path.parent.mkdir(parents=True, exist_ok=True)
            from uuid import uuid4
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            try:
                temporary.write_bytes(blob)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        if obs["audio_file"]:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            status = "ok" if digest == obs["audio_sha256"] else "SHA-256 MISMATCH"
            print(f"  {obs['observation_id']}: {status}")


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else "help"
    if cmd == "fetch":
        _verify_or_fetch()
    elif cmd == "decode":
        from .data.corpus import decode_all
        decode_all(force="--force" in argv)
    elif cmd == "train":
        from .train import main as train
        train()
    elif cmd == "bench":
        from .bench.run import main as bench
        sys.argv = [argv[0]] + argv[2:]
        bench()
    elif cmd == "analyse":
        from .analyse import main as analyse
        sys.exit(analyse(argv[2:]))
    elif cmd == "serve":
        import uvicorn
        uvicorn.run("sentinel.api.server:app", host="127.0.0.1", port=8000)
    elif cmd == "db":
        from .db import main as db
        sys.exit(db(argv[2:]))
    elif cmd == "doctor":
        from .doctor import main as doctor
        sys.exit(doctor(argv[2:]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
