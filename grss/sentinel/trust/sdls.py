"""Software emulation of CCSDS Space Data Link Security (CCSDS 355.0-B-2)
for the local command/telemetry link.

Layout follows the SDLS Security Header / Trailer, as implemented by NASA
CryptoLib (shipped with NOS3):

    | Security Header                      | Data field       | Security Trailer |
    | SPI (2) | IV (12, GCM only) | ARSN (4) | payload          | MAC (16)         |

* AUTH service: HMAC-SHA-256 truncated to 128 bits over
  (frame primary header || security header || payload).
* AUTH_ENC service: AES-256-GCM, AAD = primary header || security header,
  payload encrypted, 128-bit tag in the trailer.
* Anti-replay: the receiver keeps the highest ARSN seen and a sliding bitmap
  of width W; a frame is accepted only if its ARSN is new and inside the
  window. Replay and counter rewind are therefore *rejected*, not merely
  detected, and the MAC prevents an attacker from forging a fresh ARSN.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
from dataclasses import dataclass, field
from enum import Enum

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SPI_LEN, IV_LEN, ARSN_LEN, MAC_LEN = 2, 12, 4, 16


class Service(Enum):
    AUTH = "AUTH"            # authentication only (cleartext telemetry stays readable)
    AUTH_ENC = "AUTH_ENC"    # authenticated encryption


class Verdict(Enum):
    ACCEPT = "ACCEPT"
    REJECT_UNKNOWN_SPI = "REJECT_UNKNOWN_SPI"
    REJECT_MALFORMED = "REJECT_MALFORMED"
    REJECT_MAC = "REJECT_MAC"
    REJECT_REPLAY = "REJECT_REPLAY"          # ARSN already seen inside the window
    REJECT_STALE = "REJECT_STALE"            # ARSN older than the window


class KeyStore:
    """Software trust anchor: one master secret, per-SA keys derived with
    HKDF-SHA-256. Stands in for an HSM/TPM; the interface is the same."""

    def __init__(self, master_secret: bytes | None = None):
        self._master = master_secret or os.urandom(32)

    def derive(self, spi: int, key_id: int = 0, purpose: bytes = b"sdls") -> bytes:
        info = purpose + struct.pack(">HH", spi, key_id)
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"sentinel-link/v1", info=info).derive(self._master)


@dataclass
class SecurityAssociation:
    spi: int
    key: bytes
    service: Service = Service.AUTH
    window: int = 64
    # transmit side
    tx_arsn: int = 0
    # receive side
    rx_max: int = -1
    rx_bitmap: int = 0
    stats: dict = field(default_factory=lambda: {v.value: 0 for v in Verdict})

    # ------------------------------------------------------------- sender
    def apply(self, payload: bytes, primary_header: bytes = b"") -> bytes:
        self.tx_arsn += 1
        arsn = struct.pack(">I", self.tx_arsn)
        if self.service is Service.AUTH_ENC:
            iv = os.urandom(IV_LEN)
            sec_hdr = struct.pack(">H", self.spi) + iv + arsn
            ct = AESGCM(self.key).encrypt(iv, payload, primary_header + sec_hdr)
            return sec_hdr + ct  # ciphertext || 16-byte tag (trailer)
        sec_hdr = struct.pack(">H", self.spi) + arsn
        mac = hmac.new(self.key, primary_header + sec_hdr + payload, hashlib.sha256).digest()[:MAC_LEN]
        return sec_hdr + payload + mac

    # ----------------------------------------------------------- receiver
    def _window_check(self, arsn: int) -> Verdict:
        if arsn > self.rx_max:
            return Verdict.ACCEPT
        lag = self.rx_max - arsn
        if lag >= self.window:
            return Verdict.REJECT_STALE
        if self.rx_bitmap >> lag & 1:
            return Verdict.REJECT_REPLAY
        return Verdict.ACCEPT

    def _window_commit(self, arsn: int) -> None:
        if arsn > self.rx_max:
            shift = arsn - self.rx_max if self.rx_max >= 0 else self.window
            self.rx_bitmap = ((self.rx_bitmap << shift) | 1) & ((1 << self.window) - 1)
            self.rx_max = arsn
        else:
            self.rx_bitmap |= 1 << (self.rx_max - arsn)

    def process(self, protected: bytes, primary_header: bytes = b"") -> tuple[Verdict, bytes | None, int | None]:
        """Verify one protected frame. Returns (verdict, payload, arsn).
        The window is only advanced after the MAC verifies, so a forged
        frame cannot poison anti-replay state."""
        enc = self.service is Service.AUTH_ENC
        hdr_len = SPI_LEN + (IV_LEN if enc else 0) + ARSN_LEN
        if len(protected) < hdr_len + MAC_LEN:
            return self._count(Verdict.REJECT_MALFORMED), None, None
        sec_hdr = protected[:hdr_len]
        arsn = struct.unpack(">I", sec_hdr[-ARSN_LEN:])[0]
        if enc:
            iv = sec_hdr[SPI_LEN:SPI_LEN + IV_LEN]
            try:
                payload = AESGCM(self.key).decrypt(iv, protected[hdr_len:], primary_header + sec_hdr)
            except Exception:
                return self._count(Verdict.REJECT_MAC), None, arsn
        else:
            payload, mac = protected[hdr_len:-MAC_LEN], protected[-MAC_LEN:]
            expect = hmac.new(self.key, primary_header + sec_hdr + payload, hashlib.sha256).digest()[:MAC_LEN]
            if not hmac.compare_digest(mac, expect):
                return self._count(Verdict.REJECT_MAC), None, arsn
        verdict = self._window_check(arsn)
        if verdict is Verdict.ACCEPT:
            self._window_commit(arsn)
            return self._count(verdict), payload, arsn
        return self._count(verdict), None, arsn

    def _count(self, v: Verdict) -> Verdict:
        self.stats[v.value] += 1
        return v

    @property
    def overhead_bytes(self) -> int:
        return SPI_LEN + (IV_LEN if self.service is Service.AUTH_ENC else 0) + ARSN_LEN + MAC_LEN


def peek_spi(protected: bytes) -> int:
    return struct.unpack(">H", protected[:SPI_LEN])[0]


class SdlsEndpoint:
    """Receiver holding several SAs, dispatching on SPI."""

    def __init__(self, keystore: KeyStore):
        self.keystore = keystore
        self.sas: dict[int, SecurityAssociation] = {}

    def add_sa(self, spi: int, service: Service = Service.AUTH, window: int = 64) -> SecurityAssociation:
        sa = SecurityAssociation(spi=spi, key=self.keystore.derive(spi), service=service, window=window)
        self.sas[spi] = sa
        return sa

    def process(self, protected: bytes, primary_header: bytes = b"") -> tuple[Verdict, bytes | None, int | None]:
        if len(protected) < SPI_LEN:
            return Verdict.REJECT_MALFORMED, None, None
        sa = self.sas.get(peek_spi(protected))
        if sa is None:
            return Verdict.REJECT_UNKNOWN_SPI, None, None
        return sa.process(protected, primary_header)
