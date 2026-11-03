"""Persistent station key and per-run ledgers for the command-line analyser."""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import RESULTS_ROOT
from .trust import ledger
from .trust.manifest import StationKey

KEY_PATH = RESULTS_ROOT / "station_ed25519.pem"   # demo station key; a real station keeps it in an HSM


def station_key() -> StationKey:
    if KEY_PATH.exists():
        k = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
        assert isinstance(k, Ed25519PrivateKey)
        return StationKey(k)
    key = StationKey.generate()
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    KEY_PATH.write_bytes(key.private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()))
    return key


def ledger_for_run(name: str, frames) -> dict:
    key = station_key()
    lg = ledger.Ledger(key, checkpoint_every=64)
    lg.append("run", {"input": name, "frames": len(frames)})
    for f in frames:
        lg.append("frame", {"index": f.index, "sha256": f.sha256, "decision": f.decision, "p": round(f.probability, 4)})
    lg.checkpoint()
    out_dir = RESULTS_ROOT / "ledgers"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{Path(name).stem}.jsonl"
    lg.save(path)
    chk = ledger.verify(lg.entries, key.public_b64())
    return {"path": str(path), "head": lg.head, "entries": chk.entries, "valid": chk.valid,
            "station_public_key": key.public_b64()}
