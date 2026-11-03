import asyncio
import hashlib
import io
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

from sentinel.data.corpus import iso_to_unix


def test_naive_recording_times_are_utc_on_every_platform():
    assert iso_to_unix("2026-10-22T06:29:05") == iso_to_unix("2026-10-22T06:29:05Z")
    assert iso_to_unix("2026-10-22T07:29:05+01:00") == iso_to_unix("2026-10-22T06:29:05Z")


@pytest.mark.parametrize("name,content,start", [("record.txt", b"data", None), ("record.wav", b"", None),
                                               ("record.wav", b"data", "not-a-date")])
def test_bad_uploads_return_actionable_validation_errors(name, content, start):
    from sentinel.api.server import analyse_upload
    upload = UploadFile(filename=name, file=io.BytesIO(content))
    with pytest.raises(HTTPException) as error:
        asyncio.run(analyse_upload(upload, start))
    assert error.value.status_code == 422


def test_corrupt_audio_is_rejected_before_running_detectors():
    from sentinel.api.server import _upload
    with pytest.raises(HTTPException) as error:
        _upload(b"not-a-wav", "broken.wav", ".wav", 0, False)
    assert error.value.status_code == 422


def test_fetch_repairs_corrupt_audio_and_refuses_unverified_downloads(tmp_path, monkeypatch):
    from sentinel.__main__ import _verify_or_fetch
    from sentinel.data import corpus, satnogs
    expected = b"authentic audio"
    record = {"observation_id": 1, "audio_file": "obs_1/audio.ogg", "audio_url": "https://example.invalid/audio",
              "audio_sha256": hashlib.sha256(expected).hexdigest()}
    (tmp_path / "manifest.json").write_text(json.dumps({"observations": [record]}))
    audio = tmp_path / record["audio_file"]
    audio.parent.mkdir()
    audio.write_bytes(b"corrupt")
    monkeypatch.setattr(corpus, "corpus_root", lambda: tmp_path)
    monkeypatch.setattr(satnogs, "_session", lambda: None)
    monkeypatch.setattr(satnogs, "_get", lambda *args: SimpleNamespace(content=b"still wrong"))
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        _verify_or_fetch()
    assert audio.read_bytes() == b"corrupt"
    monkeypatch.setattr(satnogs, "_get", lambda *args: SimpleNamespace(content=expected))
    _verify_or_fetch()
    assert audio.read_bytes() == expected
    assert not list(audio.parent.glob("*.tmp"))
