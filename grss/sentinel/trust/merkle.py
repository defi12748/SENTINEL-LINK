"""Minimal SHA-256 Merkle tree (RFC 6962 style domain separation)."""

from __future__ import annotations

import hashlib


def leaf_hash(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def root(leaves: list[bytes]) -> bytes:
    """Root over already-hashed leaves (use :func:`leaf_hash`)."""
    if not leaves:
        return hashlib.sha256(b"").digest()
    level = list(leaves)
    while len(level) > 1:
        nxt = [node_hash(level[i], level[i + 1]) for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0]


def proof(leaves: list[bytes], index: int) -> list[tuple[str, bytes]]:
    """Audit path for ``leaves[index]``: list of (side, sibling)."""
    path, level, i = [], list(leaves), index
    while len(level) > 1:
        if i % 2 == 0 and i + 1 < len(level):
            path.append(("R", level[i + 1]))
        elif i % 2 == 1:
            path.append(("L", level[i - 1]))
        nxt = [node_hash(level[j], level[j + 1]) for j in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            nxt.append(level[-1])
        level, i = nxt, i // 2
    return path


def verify_proof(leaf: bytes, path: list[tuple[str, bytes]], expected_root: bytes) -> bool:
    h = leaf
    for side, sib in path:
        h = node_hash(sib, h) if side == "L" else node_hash(h, sib)
    return h == expected_root
