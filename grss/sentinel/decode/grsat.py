"""Decode a recording with gr-satellites and recover exact per-frame timing
plus physical-layer tracks (carrier frequency, signal level).

gr-satellites needs GNU Radio, which runs natively on Linux or inside WSL on
Windows (set ``SENTINEL_WSL_DISTRO`` to choose a distribution; default is the
WSL default). One demodulation pass dumps the symbol stream and the FLL
state; ``wsl_ao40_blocks.py`` then decodes each AO-40 block on its own so
every frame is bound to the symbol where it started.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..dsp.audio import estimate_bpsk_center, save_wav

HELPER = Path(__file__).with_name("wsl_ao40_blocks.py")
BAUD = 1200.0
TRACK_RATE_HZ = 10.0


@dataclass
class DecodedFrame:
    payload: bytes
    t_rec: float          # seconds from start of recording (frame start)
    t_utc: float          # absolute reception time, Unix seconds


@dataclass
class DecodeResult:
    frames: list[DecodedFrame]
    f_offset_hz: float
    sync_hits: int                          # AO-40 blocks found, decoded or not
    track_t: np.ndarray = field(repr=False)  # seconds, TRACK_RATE_HZ
    carrier_hz: np.ndarray = field(repr=False)
    level_db: np.ndarray = field(repr=False)


class GrSatellitesUnavailable(RuntimeError):
    pass


def _windows() -> bool:
    return platform.system() == "Windows"


def _wsl_prefix() -> list[str]:
    distro = os.environ.get("SENTINEL_WSL_DISTRO")
    return ["wsl", "-d", distro, "--"] if distro else ["wsl", "--"]


def _linux_path(p: Path) -> str:
    if not _windows():
        return str(p)
    p = p.resolve()
    return f"/mnt/{p.drive.rstrip(':').lower()}{p.as_posix()[len(p.drive):]}"


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    full = _wsl_prefix() + cmd if _windows() else cmd
    return subprocess.run(full, capture_output=True, text=True, timeout=timeout)


def available() -> bool:
    if _windows():
        return bool(shutil.which("wsl")) and _run(["bash", "-lc", "command -v gr_satellites"], 60).returncode == 0
    return shutil.which("gr_satellites") is not None


def _block_mean(x: np.ndarray, n: int) -> np.ndarray:
    m = len(x) // n
    return x[: m * n].reshape(m, n).mean(axis=1)


def decode_audio(x: np.ndarray, fs: int, start_utc: float, satellite: str = "FUNcube-1",
                 f_offset: float | None = None, timeout_s: int = 900) -> DecodeResult:
    if not available():
        raise GrSatellitesUnavailable(
            "gr_satellites not found: install GNU Radio + gr-satellites (Linux) or inside WSL (Windows)")
    f_offset = f_offset if f_offset is not None else estimate_bpsk_center(x, fs)
    duration = len(x) / fs
    with tempfile.TemporaryDirectory(prefix="sentinel_grsat_") as tmp:
        tmp_path = Path(tmp)
        wav, dump, out_json = tmp_path / "in.wav", tmp_path / "dump", tmp_path / "blocks.json"
        dump.mkdir()
        save_wav(wav, x, fs)
        _run(["gr_satellites", satellite, "--wavfile", _linux_path(wav), "--samp_rate", str(fs),
              "--f_offset", f"{f_offset:.1f}", "--dump_path", _linux_path(dump),
              "--kiss_out", _linux_path(tmp_path / "unused.kss")], timeout_s)
        sym_path = dump / "clock_recovery_out.c64"
        if not sym_path.exists():
            raise RuntimeError("gr-satellites produced no symbol dump")
        r = _run([os.environ.get("SENTINEL_GR_PYTHON", "python3"), _linux_path(HELPER), _linux_path(sym_path), _linux_path(out_json)], timeout_s)
        if not out_json.exists():
            raise RuntimeError(f"AO-40 block decoder failed: {r.stderr[-800:]}")
        blocks = json.loads(out_json.read_text())

        # Physical-layer tracks at TRACK_RATE_HZ.
        fll = np.fromfile(dump / "fll_freq.f32", dtype=np.float32)
        fs_dec = len(fll) / duration
        n = max(1, int(round(fs_dec / TRACK_RATE_HZ)))
        # The FLL reports the correction it applies, i.e. minus the offset
        # of the signal from f_offset (checked against the Welch spectrum).
        carrier = f_offset - _block_mean(fll, n) * fs_dec / (2 * np.pi)
        agc_in = np.fromfile(dump / "agc_in.c64", dtype=np.complex64)
        level = 10 * np.log10(_block_mean(np.abs(agc_in) ** 2, n) + 1e-20)

    sec_per_symbol = duration / max(1, blocks["n_symbols"])
    frames = []
    for b in blocks["blocks"]:
        t_rec = b["symbol_index"] * sec_per_symbol
        for hexframe in b["decoded"]:
            frames.append(DecodedFrame(bytes.fromhex(hexframe), t_rec, start_utc + t_rec))
    m = min(len(carrier), len(level))
    track_t = (np.arange(m) + 0.5) / TRACK_RATE_HZ
    return DecodeResult(frames, f_offset, len(blocks["blocks"]), track_t, carrier[:m], level[:m])
