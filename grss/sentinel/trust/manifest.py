"""Signed capture manifest for stored recordings (C2PA-inspired, for RF).

At capture time the ground station hashes the recording in fixed one-second
chunks, builds a Merkle tree over the chunk hashes, binds it to the capture
context (station, satellite, TLE, frequency, start time, decoder) and signs
the result with its Ed25519 station key. Anyone holding the station public
key can later:

* authenticate a stored recording (root matches, signature valid);
* localise tampering to the exact seconds that changed (chunk hashes);
* prove one chunk is authentic without the rest (Merkle audit path).

This answers the track question "can a stored signal be authenticated?"
for recordings made by stations running SENTINEL-LINK. Legacy recordings
(no manifest) fall back to the statistical detectors.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass

import numpy as np
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

from . import merkle

MANIFEST_VERSION = "sentinel-capture/1"


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _unb64(s: str) -> bytes:
    return base64.b64decode(s)


def canonical_json(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def chunk_hashes(samples: np.ndarray, fs: int, chunk_s: float = 1.0) -> list[bytes]:
    """Leaf hashes over the 16-bit PCM representation, so the manifest is
    independent of float rounding in different readers."""
    pcm = np.clip(np.round(samples * 32767.0), -32768, 32767).astype("<i2")
    n = int(fs * chunk_s)
    return [merkle.leaf_hash(pcm[i:i + n].tobytes()) for i in range(0, len(pcm), n)]


@dataclass
class StationKey:
    private: Ed25519PrivateKey

    @classmethod
    def generate(cls) -> "StationKey":
        return cls(Ed25519PrivateKey.generate())

    @property
    def public(self) -> Ed25519PublicKey:
        return self.private.public_key()

    def public_b64(self) -> str:
        raw = self.public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return _b64(raw)


def public_from_b64(s: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(_unb64(s))


def create_manifest(samples: np.ndarray, fs: int, context: dict, key: StationKey,
                    chunk_s: float = 1.0) -> dict:
    leaves = chunk_hashes(samples, fs, chunk_s)
    body = {
        "version": MANIFEST_VERSION,
        "context": context,
        "audio": {
            "sample_rate": fs,
            "n_samples": int(len(samples)),
            "chunk_seconds": chunk_s,
            "n_chunks": len(leaves),
            "chunk_hashes": [h.hex() for h in leaves],
            "merkle_root": merkle.root(leaves).hex(),
        },
        "signer": {"alg": "Ed25519", "public_key": key.public_b64()},
    }
    sig = key.private.sign(canonical_json(body))
    return {**body, "signature": _b64(sig)}


@dataclass
class ManifestCheck:
    signature_valid: bool
    root_valid: bool
    length_valid: bool
    tampered_chunks: list[int]

    @property
    def authentic(self) -> bool:
        return self.signature_valid and self.root_valid and self.length_valid and not self.tampered_chunks

    def tampered_intervals(self, chunk_s: float) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for c in self.tampered_chunks:
            s, e = c * chunk_s, (c + 1) * chunk_s
            if out and abs(out[-1][1] - s) < 1e-9:
                out[-1] = (out[-1][0], e)
            else:
                out.append((s, e))
        return out


def verify_manifest(manifest: dict, samples: np.ndarray, fs: int,
                    trusted_key_b64: str | None = None) -> ManifestCheck:
    body = {k: v for k, v in manifest.items() if k != "signature"}
    key_b64 = trusted_key_b64 or manifest["signer"]["public_key"]
    try:
        public_from_b64(key_b64).verify(_unb64(manifest["signature"]), canonical_json(body))
        sig_ok = trusted_key_b64 is None or trusted_key_b64 == manifest["signer"]["public_key"]
    except InvalidSignature:
        sig_ok = False
    audio = manifest["audio"]
    claimed = [bytes.fromhex(h) for h in audio["chunk_hashes"]]
    root_ok = merkle.root(claimed).hex() == audio["merkle_root"]
    actual = chunk_hashes(samples, fs, audio["chunk_seconds"])
    length_ok = len(samples) == audio["n_samples"] and fs == audio["sample_rate"]
    tampered = [i for i in range(max(len(actual), len(claimed)))
                if i >= len(actual) or i >= len(claimed) or actual[i] != claimed[i]]
    return ManifestCheck(sig_ok, root_ok, length_ok, tampered)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
