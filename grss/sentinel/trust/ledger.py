"""Append-only, hash-chained decision ledger with signed checkpoints.

Every pipeline decision (frame verdict, quarantine, verification request,
manifest check) becomes one entry. ``entry_hash = SHA-256(prev_hash ||
canonical(entry))``; every ``checkpoint_every`` entries the ground-station
key signs the current head, so rewriting history requires the private key
and breaks every later hash. Persisted as JSON Lines.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator

from cryptography.exceptions import InvalidSignature

from .manifest import StationKey, canonical_json, public_from_b64

GENESIS = "0" * 64


def _entry_hash(prev: str, body: dict) -> str:
    return hashlib.sha256(bytes.fromhex(prev) + canonical_json(body)).hexdigest()


@dataclass
class Ledger:
    key: StationKey
    checkpoint_every: int = 64
    entries: list[dict] = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    @property
    def head(self) -> str:
        return self.entries[-1]["hash"] if self.entries else GENESIS

    def append(self, kind: str, data: dict, timestamp: float | None = None) -> dict:
        with self._lock:
            body = {"index": len(self.entries), "time": timestamp if timestamp is not None else time.time(),
                    "kind": kind, "data": data, "prev": self.head}
            entry = {**body, "hash": _entry_hash(body["prev"], body)}
            self._store(entry)
            if len(self.entries) % self.checkpoint_every == 0:
                self.checkpoint()
            return entry

    def checkpoint(self) -> dict:
        with self._lock:
            head = self.head
            sig = base64.b64encode(self.key.private.sign(bytes.fromhex(head))).decode()
            body = {"index": len(self.entries), "time": time.time(), "kind": "checkpoint",
                    "data": {"signed_head": head, "signature": sig, "public_key": self.key.public_b64()},
                    "prev": head}
            entry = {**body, "hash": _entry_hash(head, body)}
            self._store(entry)
            return entry

    def _store(self, entry: dict) -> None:
        self.entries.append(entry)

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Group appends with other writes; a database-backed ledger yields its cursor."""
        with self._lock:
            yield None

    def refresh(self) -> None:
        """Pick up entries appended by other writers (database-backed ledgers)."""

    def save(self, path: Path) -> None:
        path.write_text("\n".join(json.dumps(e, sort_keys=True) for e in self.entries) + "\n", encoding="utf-8")


@dataclass
class LedgerCheck:
    valid: bool
    entries: int
    checkpoints: int
    first_broken: int | None
    reason: str | None


def verify(entries: list[dict], trusted_key_b64: str | None = None) -> LedgerCheck:
    prev, checkpoints = GENESIS, 0
    for i, e in enumerate(entries):
        body = {k: v for k, v in e.items() if k != "hash"}
        if e.get("index") != i or e.get("prev") != prev:
            return LedgerCheck(False, len(entries), checkpoints, i, "broken link")
        if _entry_hash(prev, body) != e["hash"]:
            return LedgerCheck(False, len(entries), checkpoints, i, "content hash mismatch")
        if e["kind"] == "checkpoint":
            d = e["data"]
            key = trusted_key_b64 or d["public_key"]
            if trusted_key_b64 and d["public_key"] != trusted_key_b64:
                return LedgerCheck(False, len(entries), checkpoints, i, "untrusted checkpoint key")
            try:
                public_from_b64(key).verify(base64.b64decode(d["signature"]), bytes.fromhex(d["signed_head"]))
            except InvalidSignature:
                return LedgerCheck(False, len(entries), checkpoints, i, "bad checkpoint signature")
            checkpoints += 1
        prev = e["hash"]
    return LedgerCheck(True, len(entries), checkpoints, None, None)


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
