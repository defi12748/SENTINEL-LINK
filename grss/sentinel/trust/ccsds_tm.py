"""CCSDS TM Transfer Frames protected with SDLS, byte-compatible with NASA
CryptoLib (v1.7.5, as shipped with NOS3) for an authentication-only SA:

    | primary header 6 | SPI 2 | ARSN 4 | data N | MAC 16 | FECF 2 |

    MAC  = HMAC-SHA-256(key, primary header ‖ security header ‖ data)[:16]
           (authentication bit mask all ones)
    FECF = CRC-16-CCITT (poly 0x1021, init 0xFFFF) over everything before it

Interoperability is checked against the real library through
``cryptolib_bridge`` (see ``tests/test_cryptolib_interop.py``). The receiver
here adds what CryptoLib's TM path does not do: an anti-replay check on the
ARSN (CryptoLib 1.7.5 enforces anti-replay on TC only).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import platform
import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .sdls import Verdict

SCID, VCID = 44, 0
HDR, SPI_LEN, ARSN_LEN, MAC_LEN, FECF_LEN = 6, 2, 4, 16, 2


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def primary_header(vcfc: int, scid: int = SCID, vcid: int = VCID) -> bytes:
    w0 = (0 << 14) | ((scid & 0x3FF) << 4) | ((vcid & 0x7) << 1)   # TFVN 0, no OCF
    return struct.pack(">HBBH", w0, vcfc & 0xFF, vcfc & 0xFF, 0x1800)


@dataclass
class TmSdlsLink:
    key: bytes
    spi: int = 5
    window: int = 64
    tx_arsn: int = 0          # CryptoLib transmits the current value, then increments
    tx_vcfc: int = 0
    rx_max: int = -1
    rx_bitmap: int = 0
    stats: dict = field(default_factory=lambda: {v.value: 0 for v in Verdict})

    def apply(self, data: bytes) -> bytes:
        body = primary_header(self.tx_vcfc) + struct.pack(">HI", self.spi, self.tx_arsn) + data
        mac = hmac.new(self.key, body, hashlib.sha256).digest()[:MAC_LEN]
        frame = body + mac
        self.tx_arsn += 1
        self.tx_vcfc += 1
        return frame + struct.pack(">H", crc16_ccitt(frame))

    def process(self, frame: bytes) -> tuple[Verdict, bytes | None, int | None]:
        if len(frame) < HDR + SPI_LEN + ARSN_LEN + MAC_LEN + FECF_LEN:
            return self._count(Verdict.REJECT_MALFORMED), None, None
        if crc16_ccitt(frame[:-FECF_LEN]) != struct.unpack(">H", frame[-FECF_LEN:])[0]:
            return self._count(Verdict.REJECT_MALFORMED), None, None
        spi, arsn = struct.unpack(">HI", frame[HDR:HDR + SPI_LEN + ARSN_LEN])
        if spi != self.spi:
            return self._count(Verdict.REJECT_UNKNOWN_SPI), None, arsn
        body, mac = frame[:-(MAC_LEN + FECF_LEN)], frame[-(MAC_LEN + FECF_LEN):-FECF_LEN]
        if not hmac.compare_digest(mac, hmac.new(self.key, body, hashlib.sha256).digest()[:MAC_LEN]):
            return self._count(Verdict.REJECT_MAC), None, arsn
        if arsn <= self.rx_max:
            lag = self.rx_max - arsn
            if lag >= self.window:
                return self._count(Verdict.REJECT_STALE), None, arsn
            if self.rx_bitmap >> lag & 1:
                return self._count(Verdict.REJECT_REPLAY), None, arsn
            self.rx_bitmap |= 1 << lag
        else:
            shift = arsn - self.rx_max if self.rx_max >= 0 else self.window
            self.rx_bitmap = ((self.rx_bitmap << shift) | 1) & ((1 << self.window) - 1)
            self.rx_max = arsn
        return self._count(Verdict.ACCEPT), body[HDR + SPI_LEN + ARSN_LEN:], arsn

    def _count(self, v: Verdict) -> Verdict:
        self.stats[v.value] += 1
        return v


# ------------------------------------------------------- NASA CryptoLib bridge
BRIDGE = "~/.sentinel/cryptolib_bridge"


def _cmd(args: list[str]) -> list[str]:
    if platform.system() == "Windows":
        distro = os.environ.get("SENTINEL_WSL_DISTRO")
        return (["wsl", "-d", distro, "--"] if distro else ["wsl", "--"]) + ["bash", "-lc", " ".join(args)]
    return ["bash", "-lc", " ".join(args)]


def cryptolib_available() -> bool:
    if platform.system() == "Windows" and not shutil.which("wsl"):
        return False
    r = subprocess.run(_cmd([f"test -x {BRIDGE}"]), capture_output=True)
    return r.returncode == 0


def cryptolib(mode: str, key: bytes, lines: list[str], timeout: int = 120) -> list[str]:
    """Run the NASA CryptoLib bridge (``apply`` data fields / ``process`` frames)."""
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    r = subprocess.run(_cmd([BRIDGE, mode, key.hex()]), input="\n".join(lines) + "\n",
                       capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"cryptolib bridge failed: {r.stderr[-500:]}")
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def build_bridge_hint() -> str:
    return str(Path(__file__).with_name("cryptolib_bridge") / "build.sh")
