"""SatNOGS Network client: fetch authentic observations (metadata, demodulated
frames, audio) for one satellite and record a SHA-256 manifest of everything
downloaded, so the dataset is reproducible and tamper-evident.

Note: the Network API filters by satellite with ``norad_cat_id``. The older
``satellite__norad_cat_id`` parameter is silently ignored and returns
observations of arbitrary satellites.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import requests

from .. import DATA_ROOT

API = "https://network.satnogs.org/api/observations/"
USER_AGENT = "sentinel-link-research/0.2 (TSYP14 Track 1 testbed)"
_FRAME_NAME = re.compile(r"data_(\d+)_(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})(?:_g(\d+))?")


@dataclass
class FrameRecord:
    index: int
    timestamp_utc: str
    group: int
    size_bytes: int
    sha256: str
    file: str


@dataclass
class ObservationRecord:
    observation_id: int
    norad_id: int
    start: str
    end: str
    station_id: int
    station_name: str
    station_lat: float
    station_lng: float
    station_alt: float
    frequency_hz: int
    mode: str
    baud: float | None
    tle1: str
    tle2: str
    max_altitude: float | None
    audio_url: str | None
    waterfall_url: str | None
    audio_file: str | None = None
    audio_sha256: str | None = None
    frames: list[FrameRecord] = field(default_factory=list)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def _get(session: requests.Session, url: str, **kw) -> requests.Response:
    """GET with polite retry on 429/5xx (SatNOGS rate-limits anonymous clients)."""
    for attempt in range(6):
        r = session.get(url, timeout=60, **kw)
        if r.status_code == 429 or r.status_code >= 500:
            wait = float(r.headers.get("Retry-After", 2 ** attempt * 5))
            time.sleep(min(wait, 120))
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


def frame_timestamp(url: str) -> tuple[str, int]:
    """Frame reception time (UTC, 1 s resolution) and same-second group index,
    parsed from the SatNOGS demoddata file name."""
    m = _FRAME_NAME.search(url)
    if not m:
        raise ValueError(f"unrecognised demoddata name: {url}")
    date, clock = m.group(2).split("T")
    ts = f"{date}T{clock.replace('-', ':')}Z"
    return ts, int(m.group(3) or 0)


def iter_observations(norad_id: int, status: str = "good", max_pages: int = 20,
                      session: requests.Session | None = None) -> Iterator[dict]:
    session = session or _session()
    url: str | None = API
    params = {"format": "json", "norad_cat_id": norad_id, "status": status}
    for _ in range(max_pages):
        if url is None:
            return
        r = _get(session, url, params=params)
        for obs in r.json():
            if obs.get("norad_cat_id") != norad_id:
                # Guard against the API ignoring the filter (see module docstring).
                raise RuntimeError(f"SatNOGS returned NORAD {obs.get('norad_cat_id')} for a {norad_id} query")
            yield obs
        url = r.links.get("next", {}).get("url")
        params = None  # the "next" link already carries the query string


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_observation(obs: dict, out_root: Path, with_audio: bool = True,
                         session: requests.Session | None = None) -> ObservationRecord:
    session = session or _session()
    oid = obs["id"]
    obs_dir = out_root / f"obs_{oid}"
    obs_dir.mkdir(parents=True, exist_ok=True)
    (obs_dir / "observation.json").write_text(json.dumps(obs, indent=2), encoding="utf-8")

    rec = ObservationRecord(
        observation_id=oid, norad_id=obs["norad_cat_id"], start=obs["start"], end=obs["end"],
        station_id=obs["ground_station"], station_name=obs.get("station_name") or "",
        station_lat=obs["station_lat"], station_lng=obs["station_lng"], station_alt=obs["station_alt"],
        frequency_hz=obs["observation_frequency"], mode=obs.get("transmitter_mode") or "",
        baud=obs.get("transmitter_baud"), tle1=obs.get("tle1") or "", tle2=obs.get("tle2") or "",
        max_altitude=obs.get("max_altitude"), audio_url=obs.get("payload"),
        waterfall_url=obs.get("waterfall"),
    )

    # Demodulated frames, sorted by reception time then group index.
    entries = []
    for d in obs.get("demoddata", []):
        url = d["payload_demod"]
        ts, group = frame_timestamp(url)
        entries.append((ts, group, url))
    entries.sort()
    frames_dir = obs_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    for i, (ts, group, url) in enumerate(entries):
        path = frames_dir / f"frame_{i:04d}.bin"
        if not path.exists():
            path.write_bytes(_get(session, url).content)
        blob = path.read_bytes()
        rec.frames.append(FrameRecord(i, ts, group, len(blob), _sha256(blob),
                                      path.relative_to(out_root).as_posix()))

    if with_audio and rec.audio_url:
        audio_path = obs_dir / "audio.ogg"
        if not audio_path.exists():
            audio_path.write_bytes(_get(session, rec.audio_url).content)
        rec.audio_file = audio_path.relative_to(out_root).as_posix()
        rec.audio_sha256 = _sha256(audio_path.read_bytes())

    (obs_dir / "record.json").write_text(json.dumps(asdict(rec), indent=2), encoding="utf-8")
    return rec


def build_dataset(norad_id: int, count: int, min_frames: int = 10, with_audio: bool = True,
                  out_root: Path | None = None) -> Path:
    """Download ``count`` good observations of ``norad_id`` that carry at least
    ``min_frames`` demodulated frames (and audio when requested). Writes
    ``manifest.json`` listing every file with its SHA-256."""
    out_root = out_root or DATA_ROOT / "satnogs" / str(norad_id)
    out_root.mkdir(parents=True, exist_ok=True)
    session = _session()
    records: list[ObservationRecord] = []
    for obs in iter_observations(norad_id, session=session):
        if len(obs.get("demoddata", [])) < min_frames:
            continue
        if with_audio and not obs.get("payload"):
            continue
        rec = download_observation(obs, out_root, with_audio=with_audio, session=session)
        records.append(rec)
        print(f"  obs {rec.observation_id} {rec.start} {rec.station_name[:28]:28s} "
              f"frames={len(rec.frames):3d} audio={'yes' if rec.audio_file else 'no'}")
        if len(records) >= count:
            break

    manifest = {
        "source": "SatNOGS Network (https://network.satnogs.org), CC BY-SA 4.0",
        "norad_id": norad_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query": {"norad_cat_id": norad_id, "status": "good", "min_frames": min_frames},
        "observations": [asdict(r) for r in records],
    }
    path = out_root / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def load_manifest(norad_id: int, root: Path | None = None) -> dict:
    root = root or DATA_ROOT / "satnogs" / str(norad_id)
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))
