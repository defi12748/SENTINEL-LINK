"""PostgreSQL storage for production deployments (optional).

Enabled by ``SENTINEL_DATABASE_URL`` (or ``DATABASE_URL``). Without it the
API keeps the decision ledger in memory and the CLI writes JSON Lines, as
before, so a jury can reproduce everything with no database installed.

    ledger_entries   the hash chain itself; append-only, enforced by a trigger
    runs             one row per analysed recording or scenario
    frame_decisions  one row per frame: decision, probability, evidence (JSONB)

A run, its frame decisions and their ledger entries commit in one
transaction. Writers serialise on an advisory lock, so several API processes
can share one chain. Audio stays in files or object storage; only its
SHA-256 is stored here.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from typing import Generator

from .trust.ledger import Ledger
from .trust.manifest import StationKey

LEDGER_LOCK = 0x53_4C_4C_47      # pg_advisory_xact_lock key for ledger writers

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_entries (
    idx        bigint PRIMARY KEY,
    time       double precision NOT NULL,
    kind       text NOT NULL,
    data       jsonb NOT NULL,
    prev       char(64) NOT NULL,
    hash       char(64) NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE FUNCTION ledger_entries_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ledger_entries is append-only (% refused)', TG_OP;
END $$ LANGUAGE plpgsql;
CREATE OR REPLACE TRIGGER ledger_entries_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON ledger_entries
    FOR EACH STATEMENT EXECUTE FUNCTION ledger_entries_append_only();

CREATE TABLE IF NOT EXISTS runs (
    run_id         text PRIMARY KEY,
    created_at     timestamptz NOT NULL DEFAULT now(),
    kind           text NOT NULL,
    observation_id bigint,
    source         text,
    audio_sha256   char(64),
    frames         integer NOT NULL,
    quarantined    integer NOT NULL,
    verify         integer NOT NULL,
    ledger_head    char(64) NOT NULL,
    summary        jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_created ON runs (created_at DESC);

CREATE TABLE IF NOT EXISTS frame_decisions (
    run_id      text NOT NULL REFERENCES runs (run_id),
    frame_index integer NOT NULL,
    t_rec       double precision NOT NULL,
    position    bigint,
    decision    text NOT NULL CHECK (decision IN ('ACCEPT', 'VERIFY', 'QUARANTINE')),
    probability double precision NOT NULL,
    evidence    jsonb NOT NULL,
    sha256      char(64) NOT NULL,
    ledger_idx  bigint REFERENCES ledger_entries (idx),
    PRIMARY KEY (run_id, frame_index)
);
CREATE INDEX IF NOT EXISTS frame_decisions_flagged ON frame_decisions (decision) WHERE decision <> 'ACCEPT';
"""


def database_url() -> str | None:
    return os.environ.get("SENTINEL_DATABASE_URL") or os.environ.get("DATABASE_URL") or None


class Database:
    """One connection per transaction: simple, and survives database restarts."""

    def __init__(self, url: str, init: bool = True):
        import psycopg  # only needed when a database is configured
        self._psycopg = psycopg
        self.url = url
        if init:
            self.init_schema()

    def init_schema(self) -> None:
        """Create tables, indexes and the append-only trigger (idempotent; needs a role that may create them)."""
        with self.transaction() as cur:
            cur.execute(SCHEMA)

    @contextmanager
    def transaction(self) -> Generator:
        with self._psycopg.connect(self.url) as conn:   # commits on success, rolls back on error
            with conn.cursor() as cur:
                yield cur

    def ledger_entries(self, start: int = 0, cur=None) -> list[dict]:
        sql = "SELECT idx, time, kind, data, prev, hash FROM ledger_entries WHERE idx >= %s ORDER BY idx"
        if cur is None:
            with self.transaction() as c:
                c.execute(sql, (start,))
                rows = c.fetchall()
        else:
            cur.execute(sql, (start,))
            rows = cur.fetchall()
        return [{"index": i, "time": t, "kind": k, "data": d, "prev": p.strip(), "hash": h.strip()}
                for i, t, k, d, p, h in rows]

    @staticmethod
    def insert_entry(cur, e: dict) -> None:
        cur.execute("INSERT INTO ledger_entries (idx, time, kind, data, prev, hash) VALUES (%s, %s, %s, %s, %s, %s)",
                    (e["index"], e["time"], e["kind"], json.dumps(e["data"]), e["prev"], e["hash"]))

    @staticmethod
    def record_run(cur, run_id: str, kind: str, frames: list[dict], refs: dict, ledger_head: str,
                   summary: dict, observation_id: int | None = None, source: str | None = None,
                   audio_sha256: str | None = None) -> None:
        q = sum(f["decision"] == "QUARANTINE" for f in frames)
        v = sum(f["decision"] == "VERIFY" for f in frames)
        cur.execute("""INSERT INTO runs (run_id, kind, observation_id, source, audio_sha256, frames, quarantined,
                       verify, ledger_head, summary) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (run_id, kind, observation_id, source, audio_sha256, len(frames), q, v, ledger_head,
                     json.dumps(summary, default=str)))
        cur.executemany("""INSERT INTO frame_decisions (run_id, frame_index, t_rec, position, decision, probability,
                           evidence, sha256, ledger_idx) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        [(run_id, f["index"], f["t_rec"], f["position"], f["decision"], f["probability"],
                          json.dumps(f["evidence"]), f["sha256"], (refs.get(str(f["index"])) or {}).get("entry"))
                         for f in frames])

    def recent_runs(self, limit: int = 20) -> list[dict]:
        with self.transaction() as cur:
            cur.execute("""SELECT run_id, created_at, kind, observation_id, source, frames, quarantined, verify,
                           ledger_head FROM runs ORDER BY created_at DESC LIMIT %s""", (limit,))
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def decisions(self, decision: str = "QUARANTINE", limit: int = 100) -> list[dict]:
        with self.transaction() as cur:
            cur.execute("""SELECT f.run_id, r.kind, r.observation_id, f.frame_index, f.t_rec, f.decision,
                           f.probability, f.ledger_idx, r.created_at FROM frame_decisions f JOIN runs r USING (run_id)
                           WHERE f.decision = %s ORDER BY r.created_at DESC, f.frame_index LIMIT %s""",
                        (decision, limit))
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


class PostgresLedger(Ledger):
    """The same hash chain as :class:`Ledger`, with every entry written to
    ``ledger_entries`` inside a transaction that holds the writer lock."""

    def __init__(self, key: StationKey, db: Database, checkpoint_every: int = 64):
        super().__init__(key=key, checkpoint_every=checkpoint_every)
        self.db = db
        self.entries = db.ledger_entries()
        self._cur = None
        self._local = threading.local()

    @contextmanager
    def transaction(self) -> Generator:
        if self._cur is not None and getattr(self._local, "owner", False):
            yield self._cur          # already inside this thread's transaction
            return
        with self._lock:
            mark = None
            try:
                with self.db.transaction() as cur:     # the commit happens on leaving this block
                    cur.execute("SELECT pg_advisory_xact_lock(%s)", (LEDGER_LOCK,))
                    self.entries.extend(self.db.ledger_entries(len(self.entries), cur))   # other writers' entries
                    mark = len(self.entries)
                    self._cur, self._local.owner = cur, True
                    try:
                        yield cur
                    finally:
                        self._cur, self._local.owner = None, False
            except BaseException:
                if mark is not None:
                    del self.entries[mark:]   # body or commit failed: the rows rolled back, so does the memory copy
                raise

    def refresh(self) -> None:
        with self.transaction():
            pass

    def _store(self, entry: dict) -> None:
        self.db.insert_entry(self._cur, entry)
        self.entries.append(entry)

    def append(self, kind: str, data: dict, timestamp: float | None = None) -> dict:
        with self.transaction():
            return super().append(kind, data, timestamp)

    def checkpoint(self) -> dict:
        with self.transaction():
            return super().checkpoint()


def open_store(key: StationKey, checkpoint_every: int) -> tuple[Ledger, Database | None]:
    """Ledger plus database for the API: Postgres when configured, memory otherwise.
    ``SENTINEL_DB_INIT=0`` skips schema creation, for an API role that may only SELECT and INSERT."""
    url = database_url()
    if not url:
        return Ledger(key, checkpoint_every=checkpoint_every), None
    db = Database(url, init=os.environ.get("SENTINEL_DB_INIT", "1") != "0")
    return PostgresLedger(key, db, checkpoint_every=checkpoint_every), db


def main(argv: list[str]) -> int:
    """``py -m sentinel db init`` creates the schema; ``py -m sentinel db verify`` checks the stored chain
    against this station's key."""
    url = database_url()
    if not url:
        print("set SENTINEL_DATABASE_URL (or DATABASE_URL)")
        return 2
    cmd = argv[0] if argv else ""
    if cmd == "init":
        Database(url)
        print("schema ready")
        return 0
    if cmd == "verify":
        from .ledger_store import station_key
        from .trust.ledger import verify
        chk = verify(Database(url, init=False).ledger_entries(), station_key().public_b64())
        print(f"entries {chk.entries}, checkpoints {chk.checkpoints}: "
              + ("chain valid" if chk.valid else f"BROKEN at {chk.first_broken}: {chk.reason}"))
        return 0 if chk.valid else 1
    print("usage: py -m sentinel db init|verify")
    return 2
