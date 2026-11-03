# Compliance matrix — challenge requirements → evidence

Source documents: *Ground Truth Under Attack* call, info session (20 Sep 2026) and official reference resources.
"Verify" gives a command or file a reviewer can check.

## Challenge goal

| Requirement | Where | Verify |
|---|---|---|
| Use authentic public data | 30 SatNOGS Network observations of AO-73, SHA-256 manifest | `grss/data/satnogs/39444/manifest.json`; `py -m sentinel fetch` re-downloads and checks hashes |
| Apply the common standard scenario | `sentinel/redteam/scenario.py` (replay 5–20 frames, one sequence anomaly, narrowband interference at hidden J/S, on real audio, re-decoded) | `py -m sentinel bench` |
| Detect or prevent the attack | Prevent: SDLS (`trust/sdls.py`, `trust/ccsds_tm.py`); detect: four heads + fusion (`detect/`) | `results/benchmark.md` |
| Report detection quality, false alarms, latency, memory, security overhead | `sentinel/bench/run.py` → `results/benchmark.json/.md` | sections *Frame-level*, *Interference*, *Trust anchor*, resources |
| No purchase; software trust anchor; laptop execution | HKDF key store + Ed25519 station key in software; CPU only | `docs/02_architecture_trust_anchor.md` |

## Track 1 — Secure Ground-Link Testbed

| Requirement | Where | Verify |
|---|---|---|
| Recorded SatNOGS observations **or organizer-supplied telemetry** | `py -m sentinel analyse <audio.ogg/.wav>` and `<frames.kss / frames.txt>` | `sentinel/analyse.py` |
| Authenticate a local command/telemetry sequence | CCSDS SDLS TM frames, HMAC-SHA-256 / AES-256-GCM, ARSN window; **byte-identical to NASA CryptoLib** | `tests/test_cryptolib_interop.py` (needs `trust/cryptolib_bridge/build.sh`) |
| Authenticate a stored signal | Ed25519-signed per-second Merkle capture manifest | `tests/test_trust.py::test_manifest_localises_tampering`; benchmark *Signed capture manifest* |
| Detect replay | clock head (+ splice head, duplicate-audio head, manifest, SDLS ARSN) | benchmark events `standard/replay`, `cross_pass_replay/replay` |
| Detect sequence injection | clock head (duplicate / out-of-order), telemetry head (counter-consistent forgery) | benchmark events `standard/sequence`, *Evasion* |
| Detect digitally added interference | interference head (calibrated), excision response | benchmark *Narrowband interference* (Pd vs J/S) |
| No live downlink mandatory | All on files | — |
| Processing: demodulated features, spectral occupancy, sequence analysis | `decode/`, `dsp/spectral.py`, `detect/clock.py` | `docs/03_signal_processing.md` |
| AI/detection: interference/anomaly classifier with **calibrated confidence** | Isotonic-calibrated gradient boosting; Platt-calibrated fusion; ECE reported | benchmark `calibration_ece` |
| Safety: files or conducted only, no radiated attack | All attacks are digital edits of files | `docs/01_threat_model.md` |
| Standard test: jury supplies a held-out recording | Blind analyser; absolute time optional (inferred from on-board clock) | `py -m sentinel analyse heldout.wav --out report.json` |

## Six deliverables

| # | Deliverable | Document |
|---|---|---|
| 1 | Threat model & segment analysis | `docs/01_threat_model.md` |
| 2 | Platform / architecture / trust anchor | `docs/02_architecture_trust_anchor.md` |
| 3 | Signal / image processing | `docs/03_signal_processing.md` |
| 4 | AI or statistical detection | `docs/04_detection.md` |
| 5 | Adversarial validation & response | `docs/05_adversarial_validation.md` |
| 6 | Documentation using the official reference datasets | `docs/06_dataset_and_reproducibility.md`, `README.md` |

## Official reference resources used

| Resource | Use |
|---|---|
| SatNOGS Network observations | Dataset (audio, station decodes, TLE, station position) |
| gr-satellites | Demodulation + AO-40 FEC; our per-block timing wrapper |
| Universal Radio Hacker (URH) | Attacked recordings are plain WAV files that open directly in URH for inspection of the replayed segment (`py -m sentinel analyse … --out`; attacked audio from `redteam.scenario.build(keep_audio=True)`) |
| PyOD | ECOD in the telemetry head. (ruptures not used: the on-board clock model gives exact change locations directly.) |

## Phase 1 rules

| Rule | Status |
|---|---|
| Anonymous report + code, no names/units/logos/identifying metadata | Repository content scrubbed; **git history must be re-created with a neutral author before submission** |
| Exactly one track | Track 1 |
| Official reference datasets for the standard scenario | SatNOGS |
