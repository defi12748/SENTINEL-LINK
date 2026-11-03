# Deliverable 2 — Platform, architecture and trust anchor

## Platform

Laptop CPU only. Python 3.10+ (numpy/scipy/scikit-learn/PyOD/cryptography), GNU Radio + gr-satellites for
demodulation (native Linux, or WSL on Windows), FastAPI service, Next.js/three.js console. No purchase, no SDR
required: the testbed operates on recordings (files), as allowed by the challenge.

## Components

| Layer | Module | Role |
|---|---|---|
| Data | `sentinel.data.satnogs`, `corpus` | Authentic SatNOGS observations, SHA-256 manifest, decoded corpus |
| Signal | `sentinel.decode.grsat`, `wsl_ao40_blocks` | DBPSK demod (gr-satellites) → symbol dump → per-block AO-40 FEC with exact timing; FLL carrier and level tracks |
| Signal | `sentinel.dsp` | Carrier estimate, spectral evidence, interference excision |
| Detection | `sentinel.detect` | Clock, splice, telemetry, interference heads; calibrated fusion |
| Trust | `sentinel.trust` | SDLS emulation, signed capture manifest, Merkle proofs, hash-chained ledger |
| Response | `sentinel.pipeline` | ACCEPT / VERIFY / QUARANTINE, ledger entries, excision + re-decode |
| Red team | `sentinel.redteam` | Standard scenario and evasion on real audio / frames |
| Interface | `sentinel.api`, `frontend/` | Console: pass geometry (SGP4), clock/spectrum/Doppler views, Attack Lab, trust demos |

## Trust anchor (software-emulated, as permitted)

`KeyStore` holds one 256-bit master secret and derives every key with HKDF-SHA-256
(`info = purpose ‖ SPI ‖ key-id`). It exposes only *derive*, the interface an HSM/TPM would offer, so a hardware
anchor can replace it without touching callers. The station signing key is Ed25519.

### 1. Authenticated link — CCSDS SDLS (355.0-B-2) emulation

Frame layout (as in NASA CryptoLib):

```
| SPI (2) | IV (12, GCM only) | ARSN (4) |  data field  | MAC (16) |
```

* **AUTH**: HMAC-SHA-256 truncated to 128 bits over primary header ‖ security header ‖ data. 22 B overhead.
* **AUTH_ENC**: AES-256-GCM, AAD = primary header ‖ security header. 34 B overhead.
* **Anti-replay**: highest ARSN + sliding bitmap of width *W* (64). New ARSN → accept and slide; inside window and
  already seen → `REJECT_REPLAY`; older than window → `REJECT_STALE`.
* **Window integrity**: the window moves only after the MAC verifies, so a forged frame cannot advance the counter
  and lock out genuine traffic (tested).

### 2. Stored-signal authentication — signed capture manifest

At capture the station computes SHA-256 leaf hashes over each second of 16-bit PCM, a Merkle root (RFC 6962
domain separation), binds them to the capture context (observation, station, TLE, frequency, start time,
decoder) and signs with Ed25519. Verification returns: signature valid, root valid, length valid, **list of
tampered seconds**. Merkle audit paths prove a single second authentic without the rest of the file.

### 3. Decision provenance — hash-chained ledger

`entry_hash = SHA-256(prev_hash ‖ canonical_json(entry))`; every *N* entries a checkpoint signs the head with the
station key. Verification pinpoints the first broken entry; rewriting history requires the private key and
recomputing all subsequent hashes, and still fails against a published checkpoint.

In production the chain is stored in PostgreSQL (`sentinel.db`, enabled by `SENTINEL_DATABASE_URL`). The database
adds two guarantees the hash chain cannot give on its own: a run, its per-frame decisions and their ledger entries
commit in one transaction, and the `ledger_entries` table refuses `UPDATE`, `DELETE` and `TRUNCATE` by trigger. The
API runs as a role granted only `SELECT` and `INSERT`, so it cannot drop that trigger either. The hash chain still
does the detection: an attacker with database-owner rights who rewrites a row breaks verification at that entry.
Audio is kept outside the database and referenced by SHA-256.

## Data flow per recording

1. Verify capture manifest (if present) → tampered seconds are evidence.
2. Interference head on raw audio → alarms → excision of each alarmed interferer.
3. Demodulate + per-block AO-40 decode → frames with start times; carrier/level tracks.
4. Clock / splice / telemetry heads → evidence vector per frame → fusion probability.
5. Decision per frame; non-accepted frames and the run summary appended to the ledger.

## Security overhead

Measured per frame on real 256-byte AO-73 frames in the benchmark (`results/benchmark.md`, section *Trust anchor*):
bytes added, apply/verify time, replay and bit-flip rejection rates.
