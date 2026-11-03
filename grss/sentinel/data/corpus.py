"""Decoded corpus: every SatNOGS recording decoded once by our own chain
(audio -> gr-satellites -> AO-40 blocks) and cached next to the raw data.

Each observation directory gains ``decoded.json`` (frames with timing) and
``tracks.npz`` (carrier frequency and level at 10 Hz).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .. import DATA_ROOT
from ..decode import funcube, grsat
from ..dsp.audio import load_audio


def iso_to_unix(ts: str) -> float:
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


@dataclass
class Pass:
    """One satellite pass as the detectors see it."""
    observation_id: int
    station: str
    start_utc: float
    t_rec: np.ndarray            # frame start, seconds into the recording
    payloads: list[bytes]
    track_t: np.ndarray
    carrier_hz: np.ndarray
    level_db: np.ndarray
    tle: tuple[str, str]
    station_lla: tuple[float, float, float]

    @property
    def t_utc(self) -> np.ndarray:
        return self.start_utc + self.t_rec

    def parsed(self) -> list[funcube.FuncubeFrame | None]:
        return [funcube.parse(p) for p in self.payloads]


def corpus_root(norad_id: int = 39444) -> Path:
    return DATA_ROOT / "satnogs" / str(norad_id)


def decode_observation(obs_dir: Path, force: bool = False) -> Path:
    out = obs_dir / "decoded.json"
    if out.exists() and not force:
        return out
    rec = json.loads((obs_dir / "record.json").read_text(encoding="utf-8"))
    x, fs = load_audio(obs_dir / "audio.ogg")
    start = iso_to_unix(rec["start"])
    res = grsat.decode_audio(x, fs, start)
    np.savez_compressed(obs_dir / "tracks.npz", t=res.track_t, carrier_hz=res.carrier_hz, level_db=res.level_db)
    out.write_text(json.dumps({
        "observation_id": rec["observation_id"],
        "decoder": "gr-satellites FUNcube-1 + per-block AO-40 (sentinel)",
        "f_offset_hz": res.f_offset_hz,
        "sync_hits": res.sync_hits,
        "audio_seconds": len(x) / fs,
        "frames": [{"t_rec": f.t_rec, "hex": f.payload.hex()} for f in res.frames],
    }, indent=1), encoding="utf-8")
    return out


def decode_all(norad_id: int = 39444, force: bool = False) -> None:
    root = corpus_root(norad_id)
    for obs_dir in sorted(root.glob("obs_*")):
        if not (obs_dir / "audio.ogg").exists():
            continue
        try:
            path = decode_observation(obs_dir, force=force)
            d = json.loads(path.read_text(encoding="utf-8"))
            print(f"{obs_dir.name}: {len(d['frames'])} frames / {d['sync_hits']} blocks")
        except Exception as exc:  # keep going; report at the end
            print(f"{obs_dir.name}: FAILED {exc}")


def load_pass(obs_dir: Path) -> Pass:
    rec = json.loads((obs_dir / "record.json").read_text(encoding="utf-8"))
    dec = json.loads((obs_dir / "decoded.json").read_text(encoding="utf-8"))
    tr = np.load(obs_dir / "tracks.npz")
    frames = dec["frames"]
    return Pass(
        observation_id=rec["observation_id"], station=rec["station_name"], start_utc=iso_to_unix(rec["start"]),
        t_rec=np.array([f["t_rec"] for f in frames]), payloads=[bytes.fromhex(f["hex"]) for f in frames],
        track_t=tr["t"], carrier_hz=tr["carrier_hz"], level_db=tr["level_db"],
        tle=(rec["tle1"], rec["tle2"]), station_lla=(rec["station_lat"], rec["station_lng"], rec["station_alt"]),
    )


def load_corpus(norad_id: int = 39444) -> list[Pass]:
    root = corpus_root(norad_id)
    return [load_pass(d) for d in sorted(root.glob("obs_*")) if (d / "decoded.json").exists()]


if __name__ == "__main__":
    decode_all()
