"""PostgreSQL storage: the ledger survives restarts, refuses edits, stays one
chain under several writers, and a failed run leaves no trace.

Needs a disposable database:
    SENTINEL_TEST_DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/db py -m pytest tests/test_postgres_store.py
"""

import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest

from sentinel import db as db_mod
from sentinel.trust import ledger
from sentinel.trust.manifest import StationKey

URL = os.environ.get("SENTINEL_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="SENTINEL_TEST_DATABASE_URL not set")


@pytest.fixture
def url():
    psycopg = pytest.importorskip("psycopg")
    assert URL
    schema = f"t_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute(f"CREATE SCHEMA {schema}")
    sep = "&" if "?" in URL else "?"
    yield f"{URL}{sep}options=-csearch_path%3D{schema}"
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute(f"DROP SCHEMA {schema} CASCADE")


def _frames(n, flagged=(1,)):
    return [{"index": i, "t_rec": 5.0 * i, "position": 1000 + i, "decision": "QUARANTINE" if i in flagged else "ACCEPT",
             "probability": 0.99 if i in flagged else 0.01, "evidence": {"u_behind": 9.0 if i in flagged else 0.0},
             "sha256": f"{i:064x}"} for i in range(n)]


def test_ledger_survives_restart_and_verifies(url):
    key = StationKey.generate()
    lg = db_mod.PostgresLedger(key, db_mod.Database(url), checkpoint_every=4)
    for i in range(9):
        lg.append("frame", {"index": i, "decision": "ACCEPT"})
    head = lg.head
    reopened = db_mod.PostgresLedger(key, db_mod.Database(url), checkpoint_every=4)
    assert reopened.head == head and reopened.entries == lg.entries
    chk = ledger.verify(reopened.entries, key.public_b64())
    assert chk.valid and chk.checkpoints == 2


def test_ledger_rows_are_append_only(url):
    psycopg = pytest.importorskip("psycopg")
    lg = db_mod.PostgresLedger(StationKey.generate(), db_mod.Database(url))
    lg.append("frame", {"decision": "QUARANTINE"})
    for sql in ("UPDATE ledger_entries SET data = '{\"decision\": \"ACCEPT\"}'", "DELETE FROM ledger_entries",
                "TRUNCATE ledger_entries CASCADE"):
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            with psycopg.connect(url) as c:
                c.execute(sql)
    assert db_mod.Database(url).ledger_entries() == lg.entries


def test_api_role_can_append_but_not_rewrite(url):
    """Production layout: an admin creates the schema, the API runs as a role with SELECT and INSERT only."""
    psycopg = pytest.importorskip("psycopg")
    schema = url.rsplit("%3D", 1)[1]
    role, password = f"app_{uuid.uuid4().hex[:8]}", uuid.uuid4().hex
    db_mod.Database(url).init_schema()
    with psycopg.connect(url, autocommit=True) as c:
        c.execute(f"CREATE ROLE {role} LOGIN PASSWORD '{password}'")
        c.execute(f"GRANT USAGE ON SCHEMA {schema} TO {role}")
        c.execute(f"GRANT SELECT, INSERT ON ledger_entries, runs, frame_decisions TO {role}")
    parts = urlsplit(url)
    host = f"{parts.hostname}:{parts.port}" if parts.port else parts.hostname
    app_url = urlunsplit(parts._replace(netloc=f"{role}:{password}@{host}"))
    try:
        key = StationKey.generate()
        lg = db_mod.PostgresLedger(key, db_mod.Database(app_url, init=False))
        lg.append("frame", {"decision": "QUARANTINE"})
        assert ledger.verify(db_mod.Database(url).ledger_entries(), key.public_b64()).valid
        for sql in ("UPDATE ledger_entries SET kind = 'x'", "DROP TRIGGER ledger_entries_append_only ON ledger_entries",
                    "DROP TABLE frame_decisions"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with psycopg.connect(app_url) as c:
                    c.execute(sql)
    finally:
        with psycopg.connect(url, autocommit=True) as c:
            c.execute(f"DROP OWNED BY {role}")
            c.execute(f"DROP ROLE {role}")


def test_two_writers_share_one_chain(url):
    key = StationKey.generate()
    a = db_mod.PostgresLedger(key, db_mod.Database(url), checkpoint_every=1000)
    b = db_mod.PostgresLedger(key, db_mod.Database(url), checkpoint_every=1000)
    for i in range(6):
        (a if i % 2 else b).append("frame", {"i": i})
    stored = db_mod.Database(url).ledger_entries()
    assert len(stored) == 6 and [e["data"]["i"] for e in stored] == list(range(6))
    assert ledger.verify(stored, key.public_b64()).valid


def test_run_and_its_entries_commit_together(url):
    key = StationKey.generate()
    store = db_mod.Database(url)
    lg = db_mod.PostgresLedger(key, store)
    frames = _frames(4)
    with pytest.raises(RuntimeError):
        with lg.transaction() as cur:
            lg.append("run", {"run": "r1"})
            store.record_run(cur, "r1", "standard", frames, {}, lg.head, {"variant": "standard"})
            raise RuntimeError("analysis failed half-way")
    assert lg.entries == [] and store.ledger_entries() == [] and store.recent_runs() == []

    with lg.transaction() as cur:
        lg.append("run", {"run": "r2"})
        entry = lg.append("frame", {"run": "r2", "index": 1, "decision": "QUARANTINE"})
        store.record_run(cur, "r2", "standard", frames, {"1": {"entry": entry["index"]}}, lg.head,
                         {"variant": "standard"}, observation_id=15261075)
    run = store.recent_runs()[0]
    assert (run["run_id"], run["frames"], run["quarantined"], run["observation_id"]) == ("r2", 4, 1, 15261075)
    flagged = store.decisions("QUARANTINE")
    assert [(f["run_id"], f["frame_index"], f["ledger_idx"]) for f in flagged] == [("r2", 1, entry["index"])]
