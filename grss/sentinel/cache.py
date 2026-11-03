"""Bounded JSON result cache. No executable serialization or cached run state."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from uuid import uuid4


def encode(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


# Filesystem timestamps are coarser than they look (ext4 advances them once per
# kernel tick), so a same-size rewrite can keep its (size, mtime, ctime). Like
# git's "racy clean" rule, files modified this recently are always re-hashed.
RACY_WINDOW_NS = 2_000_000_000


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@lru_cache(maxsize=2048)
def _file_digest(path: str, size: int, modified: int, changed: int) -> str:
    return _hash_file(path)


def fingerprint(path: Path) -> str:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return "missing"
    resolved = str(path.resolve())
    if time.time_ns() - max(stat.st_mtime_ns, stat.st_ctime_ns) < RACY_WINDOW_NS:
        return _hash_file(resolved)
    return _file_digest(resolved, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def cache_key(namespace: str, parameters: dict, files: list[Path]) -> str:
    dependencies = [(str(p.resolve()), fingerprint(p)) for p in sorted(set(files))]
    return hashlib.sha256(encode([namespace, parameters, dependencies])).hexdigest()


class ResultCache:
    def __init__(self, root: Path, memory_entries: int = 8, disk_entries: int = 64,
                 ttl_s: float = 7 * 86400, max_bytes: int = 256 * 1024 * 1024):
        self.root = root
        self.memory_entries = memory_entries
        self.disk_entries = disk_entries
        self.ttl_s = ttl_s
        self.max_bytes = max_bytes
        self.memory: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self.lock = threading.RLock()
        self.workers = [threading.Lock() for _ in range(32)]

    def get_or_compute(self, key: str, compute) -> tuple[dict, dict]:
        start = time.perf_counter()
        # Stripes bound the number of locks and coalesce concurrent identical work.
        with self.workers[int(key[:8], 16) % len(self.workers)]:
            value, status = self._read(key)
            if value is None:
                value = encode(compute())  # exceptions and non-JSON results are never stored
                self._write(key, value)
                status = "miss"
            # Decode on every return: callers cannot mutate another run's cached data.
            return json.loads(value), {"status": status, "key": key,
                                       "elapsed_ms": round((time.perf_counter() - start) * 1000, 2)}

    def _read(self, key: str) -> tuple[bytes | None, str]:
        now = time.time()
        with self.lock:
            cached = self.memory.get(key)
            if cached and now - cached[0] < self.ttl_s:
                self.memory.move_to_end(key)
                return cached[1], "memory"
            self.memory.pop(key, None)
            path = self.root / f"{key}.json"
            try:
                if now - path.stat().st_mtime >= self.ttl_s:
                    return None, "miss"
                entry = json.loads(path.read_bytes())
                payload = entry["payload"].encode()
                if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                    return None, "miss"
                json.loads(payload)
                self._remember(key, payload, path.stat().st_mtime)
                os.utime(path, None)
                return payload, "disk"
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                return None, "miss"

    def _remember(self, key: str, payload: bytes, created: float) -> None:
        if self.memory_entries <= 0:
            return
        self.memory[key] = (created, payload)
        self.memory.move_to_end(key)
        while len(self.memory) > self.memory_entries:
            self.memory.popitem(last=False)

    def _write(self, key: str, payload: bytes) -> None:
        with self.lock:
            self._remember(key, payload, time.time())
            temporary = self.root / f"{key}.{uuid4().hex}.tmp"
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                temporary.write_bytes(encode({"payload": payload.decode(),
                                             "sha256": hashlib.sha256(payload).hexdigest()}))
                os.replace(temporary, self.root / f"{key}.json")
                files = sorted((p for p in self.root.glob("*.json")
                                if len(p.stem) == 64 and all(c in "0123456789abcdef" for c in p.stem)),
                               key=lambda p: p.stat().st_mtime, reverse=True)
                size = 0
                for index, path in enumerate(files):
                    size += path.stat().st_size
                    if index >= self.disk_entries or size > self.max_bytes:
                        path.unlink(missing_ok=True)
            except OSError:
                # A read-only or full disk must not make analysis unavailable.
                pass
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
