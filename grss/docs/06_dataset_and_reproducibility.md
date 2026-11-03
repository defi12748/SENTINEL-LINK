# Deliverable 6 — Official reference data and reproducibility

## Dataset

| Item | Value |
|---|---|
| Source | SatNOGS Network (official Track 1 reference data), CC BY-SA 4.0 |
| Satellite | AO-73 / FUNcube-1, NORAD 39444, 145.935 MHz, DBPSK 1200 Bd, AO-40 FEC |
| Observations | 30, status "good", 29 Sep – 22 Oct 2026 |
| Stations | 5 (Japan ×2, Bulgaria, Germany, USA) |
| Per observation | Ogg audio (48 kHz), station-decoded frames with timestamps, TLE, station position, metadata |
| Integrity | SHA-256 of every file in `data/satnogs/39444/manifest.json` |
| Query | `GET /api/observations/?norad_cat_id=39444&status=good` (note: the `satellite__norad_cat_id` filter is silently ignored by the API) |

## Split

* **Training (13)**: observations before 15 Oct 2026 from stations that appear more than once.
* **Held-out (17)**: every later observation, plus every observation from a station not in training.

Every model (clock, telemetry, interference, fusion) is fitted on the training split only; every reported
metric is measured on the held-out split.

## What is derived from the data

| Artefact | Produced by | Location |
|---|---|---|
| Frames + exact timing + Doppler/level tracks | `py -m sentinel decode` (gr-satellites + per-block AO-40) | `obs_*/decoded.json`, `obs_*/tracks.npz` |
| Attacked recordings (re-decoded) | `redteam/scenario.py` (seeded by seed × observation) | `data/attacked/` (cache, regenerable) |
| Models | `py -m sentinel train` | `models/sentinel_models.joblib`, `models/model_card.json` |
| Metrics | `py -m sentinel bench` | `results/benchmark.json`, `results/benchmark.md` |

## Reproduce from scratch

```bash
# Linux (or WSL on Windows)
sudo apt install gnuradio gr-satellites            # demodulation + AO-40 FEC
bash grss/sentinel/trust/cryptolib_bridge/build.sh # optional: NASA CryptoLib interop tests

cd grss
python -m pip install -r requirements.lock.txt
py -m sentinel fetch       # audio download + SHA-256 check
py -m sentinel decode      # ~10 s per recording
py -m sentinel train
py -m sentinel bench       # ~25 min on a laptop
py -m sentinel.bench.report
py -m pytest tests
```

Analyse any recording or frame file (e.g. the held-out test):

```bash
py -m sentinel analyse heldout.wav --out report.json            # start time optional
py -m sentinel analyse frames.kss                               # gr-satellites KISS
```

## Determinism

Attack parameters are drawn from `numpy.random.default_rng([seed, observation_id])`; seeds are listed in the
benchmark JSON. Gradient boosting uses `random_state=0`. The only non-deterministic element is the demo
station signing key (generated on first use, never committed).

## Hardware used for the reported numbers

Laptop, Windows 10, 12 logical CPUs, no GPU used; GNU Radio inside WSL2. Environment details are embedded in
`results/benchmark.json`.

## Verified runtime setup

`requirements.lock.txt` pins the Python 3.13 environment used with the supplied model. `deploy/setup_nasa.py` installs the tested NASA revisions. `python -m sentinel doctor --verify-data --require-nasa` checks the model, decoder, integrations, and every audio/frame hash. Downloads fail closed if their hash differs from the committed manifest.

`deploy/verify_clean.py --smoke --out results/clean_install.json` runs the copied source in a new environment and checks the full API. See `deploy/README.md` for Windows/WSL, Linux, and Compose instructions. GNU Radio uses its own Linux system Python; the app's dependency environment remains isolated.
