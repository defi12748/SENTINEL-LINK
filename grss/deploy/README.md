# Run Sentinel Link

## Docker Compose

From the repository root, put a database password in `.env` (git-ignored), then start the stack:

```sh
echo "SENTINEL_DB_PASSWORD=$(openssl rand -hex 24)" > .env
docker compose up --build
```

Open http://localhost:3000. Compose runs PostgreSQL 16 for the decision ledger and run history (see [Production storage](#production-storage-postgresql)); its data lives in the `sentinel-db` volume and its port is not published. The API image includes GNU Radio, gr-satellites, and the pinned NASA OnAIR/CryptoLib sources. On first startup it restores missing audio and checks SHA-256 against the committed manifest. Existing valid recordings are reused. Dataset and results folders persist through bind mounts.

The frontend forwards `/backend/*` to the API, so the same browser URL works for navigation, simulation requests, and uploads. API requests have a ten-minute proxy timeout for cold decoding. Compose binds the published ports to the local machine.

Use `SENTINEL_WEB_PORT` and `SENTINEL_API_PORT` to change published ports. `SENTINEL_FETCH_ON_START=0` skips the startup fetch when operating offline with an already verified dataset.

```sh
docker compose exec api python -m sentinel doctor --verify-data --require-nasa
docker compose exec api python -m pytest tests -q -p no:asyncio
docker compose exec api python deploy/smoke.py
```

## Native Windows or Linux

Use Python 3.13 for the supplied model and dependency lock, Node.js 22, Git, and GNU Radio/gr-satellites. Windows runs the decoder and CryptoLib bridge inside WSL.

Install these packages in Linux or the selected WSL distribution:

```sh
sudo apt-get update
sudo apt-get install gnuradio gr-satellites python3-venv cmake build-essential libgcrypt20-dev git
```

From `grss`, create a new Python 3.13 environment:

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock.txt
python deploy/setup_nasa.py
python -m sentinel fetch
python -m sentinel doctor --verify-data --require-nasa
python -m sentinel serve
```

On Windows use `py -3.13 -m venv .venv`, then `.venv\Scripts\Activate.ps1`. If the decoder lives in a non-default WSL distro, set `$env:SENTINEL_WSL_DISTRO="Ubuntu-NOS3"` before setup and serving.

In a second terminal, from `grss/frontend`:

```sh
npm ci
npm run dev
```

For production, use `npm run build` followed by `npm start`. The browser uses the web server's `/backend` proxy by default. `SENTINEL_API_URL` selects its upstream API at build time (or development-server startup); `NEXT_PUBLIC_API` overrides the browser URL when deliberately deploying the API separately.

### Separate GNU Radio interpreter

GNU Radio's Python modules belong to the Linux system interpreter. If the app uses a managed Python/venv on Linux, set `SENTINEL_GR_PYTHON=/usr/bin/python3`. The Docker image already does this. On Windows the default `python3` resolves inside WSL.

### Storage and external modules

- `SENTINEL_DATA_ROOT`: dataset and regenerable attack cache; defaults to `grss/data`.
- `SENTINEL_RESULTS_ROOT`: reports, CLI ledgers, and API cache; defaults to `grss/results`.
- `SENTINEL_CACHE_DIR`: override the API cache directory.
- `SENTINEL_ONAIR_PATH`: custom OnAIR directory (the one containing `onair/`). Setup installs the tested revision under `~/.sentinel/OnAIR`; a NOS3 checkout works via its `components/onair/fsw`.
- `CRYPTOLIB_SRC`: custom CryptoLib source when building the bridge. The default build fetches the tested revision.

The locked Python environment, NASA source revisions, and system decoder interpreter are separate on purpose. The core app does not require NOS3 Docker services or a running Redis server.

## Production storage (PostgreSQL)

Set `SENTINEL_DATABASE_URL` (or `DATABASE_URL`) to a PostgreSQL 14+ database. Without it the API keeps the ledger in memory and the CLI writes JSON Lines, which is enough to reproduce the benchmark.

| Table | Content |
|---|---|
| `ledger_entries` | The hash chain: one row per entry, checkpoints signed with the station key. A trigger refuses `UPDATE`, `DELETE` and `TRUNCATE`. |
| `runs` | One row per analysed recording or scenario: kind, observation, source file and SHA-256, counts, ledger head. |
| `frame_decisions` | One row per frame: decision, calibrated probability, evidence vector (JSONB), frame SHA-256, ledger entry. |

A run, its frame decisions and their ledger entries commit in one transaction, and writers serialise on an advisory lock, so several API processes can share one chain. Audio is not stored in the database; keep it in files or object storage and refer to it by SHA-256.

With a database the station signing key must outlive the process, because stored checkpoints are verified against it. The API then uses `results/station_ed25519.pem`, created on first start; in a real station this key belongs in an HSM.

Separate the schema owner from the API role so that the API can append to the ledger but cannot rewrite it, drop the trigger or drop a table:

```sh
SENTINEL_DATABASE_URL=postgresql://admin:...@host/sentinel python -m sentinel db init
```

```sql
CREATE ROLE sentinel_api LOGIN PASSWORD '...';
GRANT USAGE ON SCHEMA public TO sentinel_api;
GRANT SELECT, INSERT ON ledger_entries, runs, frame_decisions TO sentinel_api;
```

Run the API as `sentinel_api` with `SENTINEL_DB_INIT=0`, so it does not try to create the schema. Operators query recent runs at `GET /api/runs` and flagged frames at `GET /api/decisions?decision=QUARANTINE`; `python -m sentinel db verify` checks the stored chain against the station key.

The storage tests run against a disposable database:

```sh
SENTINEL_TEST_DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/scratch python -m pytest tests/test_postgres_store.py
```

## Verify an isolated installation

Install `requirements.lock.txt` into a new venv, then use that venv's Python:

```sh
python deploy/verify_clean.py --smoke --out results/clean_install.json
```

This copies application sources, models, tests, and docs into a new temporary directory. It excludes installed packages and prior build/cache outputs, verifies the real public dataset, runs the test suite, and starts a new API to test simulations, cache reuse, SDLS, NASA interoperability, and the ledger. Public recordings are reused as test inputs, with their hashes checked. Both NASA modules must be installed for this strict check.

The measured detector limitations are in `results/benchmark.md`. Cached serving time is separate from detector or decoder execution time.
