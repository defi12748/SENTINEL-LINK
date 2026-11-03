import base64
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from sentinel.cache import ResultCache, cache_key
from sentinel.trust import ledger
from sentinel.trust.manifest import StationKey, canonical_json, create_manifest


def test_cache_reuses_disk_and_isolates_mutation(tmp_path):
    key = cache_key("test", {}, [])
    cache = ResultCache(tmp_path)
    first, meta = cache.get_or_compute(key, lambda: {"frames": [1]})
    assert meta["status"] == "miss"
    first["frames"].append(2)
    second, meta = cache.get_or_compute(key, lambda: pytest.fail("recomputed"))
    assert second == {"frames": [1]} and meta["status"] == "memory"
    after_restart, meta = ResultCache(tmp_path).get_or_compute(key, lambda: pytest.fail("recomputed"))
    assert after_restart == second and meta["status"] == "disk"


def test_keys_track_parameters_and_content(tmp_path):
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"one")
    initial = cache_key("scenario", {"seed": 7, "overrides": {"replay": True, "js_db": -12}}, [audio])
    assert initial == cache_key("scenario", {"overrides": {"js_db": -12, "replay": True}, "seed": 7}, [audio])
    assert initial != cache_key("scenario", {"seed": 8}, [audio])
    audio.write_bytes(b"two")  # same size, different recording
    assert initial != cache_key("scenario", {"seed": 7, "overrides": {"replay": True, "js_db": -12}}, [audio])


def test_cache_coalesces_concurrent_work(tmp_path):
    cache = ResultCache(tmp_path)
    key = cache_key("scenario", {}, [])
    calls = []
    barrier = threading.Barrier(6)
    def compute():
        calls.append(1)
        time.sleep(.03)
        return {"ok": True}
    def request(_):
        barrier.wait()
        return cache.get_or_compute(key, compute)[0]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(request, range(6)))
    assert len(calls) == 1 and all(r == {"ok": True} for r in results)


def test_corruption_expiry_and_failed_work_are_not_reused(tmp_path):
    key = cache_key("scenario", {}, [])
    cache = ResultCache(tmp_path, memory_entries=0)
    cache.get_or_compute(key, lambda: {"old": True})
    (tmp_path / f"{key}.json").write_text('{"sha256":"wrong","payload":"{}"}')
    value, meta = cache.get_or_compute(key, lambda: {"recovered": True})
    assert value["recovered"] and meta["status"] == "miss"
    expired = ResultCache(tmp_path, ttl_s=0)
    _, meta = expired.get_or_compute(key, lambda: {"new": True})
    assert meta["status"] == "miss"
    key = cache_key("error", {}, [])
    with pytest.raises(ValueError):
        cache.get_or_compute(key, lambda: (_ for _ in ()).throw(ValueError("failed")))
    assert not (tmp_path / f"{key}.json").exists()


def test_cache_is_bounded(tmp_path):
    cache = ResultCache(tmp_path, memory_entries=2, disk_entries=3)
    for seed in range(8):
        cache.get_or_compute(cache_key("test", {"seed": seed}, []), lambda: {"ok": True})
    assert len(cache.memory) == 2 and len(list(tmp_path.glob("*.json"))) == 3


def test_reused_analysis_gets_fresh_audit_and_current_signer(tmp_path, monkeypatch):
    from sentinel.api import server
    key = StationKey.generate()
    capture = create_manifest(np.zeros(1000), 1000, {"observation_id": 1}, key)
    cached_result = {"_capture": {k: v for k, v in capture.items() if k not in {"signer", "signature"}},
                     "manifest": {"authentic": True, "signature_valid": True},
                     "frames": [{"index": 0, "decision": "QUARANTINE", "sha256": "abc", "probability": .99}]}
    calls = []
    monkeypatch.setattr(server, "CACHE", ResultCache(tmp_path))
    monkeypatch.setattr(server, "_obs_dir", lambda _: tmp_path)
    monkeypatch.setattr(server, "_analysis_key", lambda *args: cache_key("test", {}, []))
    monkeypatch.setattr(server, "_scenario", lambda *args: (calls.append(1) or cached_result))
    monkeypatch.setattr(server, "LEDGER", ledger.Ledger(key, checkpoint_every=4))
    monkeypatch.setattr(server, "STATION_KEY", key)
    request = server.ScenarioRequest(observation_id=1)
    first = server.run_scenario(request)
    # Restart: retain only disk cache, use a newly generated station key and ledger.
    second_key = StationKey.generate()
    monkeypatch.setattr(server, "CACHE", ResultCache(tmp_path))
    monkeypatch.setattr(server, "STATION_KEY", second_key)
    monkeypatch.setattr(server, "LEDGER", ledger.Ledger(second_key, checkpoint_every=4))
    second = server.run_scenario(request)
    third = server.run_scenario(request)
    assert len(calls) == 1 and second["cache"]["status"] == "disk" and third["cache"]["status"] == "memory"
    assert len({first["run_id"], second["run_id"], third["run_id"]}) == 3
    assert second["frames"] == first["frames"]
    assert second["ledger_head"] != third["ledger_head"]
    assert second["ledger_refs"]["0"] != third["ledger_refs"]["0"]
    body = {k: v for k, v in second["capture_manifest"].items() if k != "signature"}
    second_key.public.verify(base64.b64decode(second["capture_manifest"]["signature"]), canonical_json(body))
    assert body["signer"]["public_key"] == second_key.public_b64()
    assert ledger.verify(server.LEDGER.entries, second_key.public_b64()).valid


def test_concurrent_ledger_appends_stay_valid():
    key = StationKey.generate()
    log = ledger.Ledger(key, checkpoint_every=8)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: log.append("frame", {"index": i}), range(80)))
    assert ledger.verify(log.entries, key.public_b64()).valid
    assert sum(e["kind"] == "frame" for e in log.entries) == 80
