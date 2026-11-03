"""KISS framing (as written by gr-satellites ``--kiss_out``).

gr-satellites emits a timestamp record (command 0x09, 8-byte big-endian
milliseconds since the Unix epoch) before each data frame (command 0x00).
"""

from __future__ import annotations

from dataclasses import dataclass

FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD
CMD_DATA, CMD_TIMESTAMP = 0x00, 0x09


@dataclass
class KissFrame:
    payload: bytes
    timestamp_ms: int | None


def _records(raw: bytes) -> list[bytes]:
    out: list[bytes] = []
    cur: bytearray | None = None
    esc = False
    for b in raw:
        if b == FEND:
            if cur:
                out.append(bytes(cur))
            cur = bytearray()
            continue
        if cur is None:
            continue
        if esc:
            cur.append(FEND if b == TFEND else FESC if b == TFESC else b)
            esc = False
        elif b == FESC:
            esc = True
        else:
            cur.append(b)
    return out


def read_kiss(raw: bytes) -> list[KissFrame]:
    frames: list[KissFrame] = []
    pending_ts: int | None = None
    for rec in _records(raw):
        cmd, body = rec[0] & 0x0F, rec[1:]
        if cmd == CMD_TIMESTAMP and len(body) == 8:
            pending_ts = int.from_bytes(body, "big")
        elif cmd == CMD_DATA:
            frames.append(KissFrame(body, pending_ts))
            pending_ts = None
    return frames


def write_kiss(frames: list[KissFrame]) -> bytes:
    def esc(data: bytes) -> bytes:
        return data.replace(bytes([FESC]), bytes([FESC, TFESC])).replace(bytes([FEND]), bytes([FESC, TFEND]))

    out = bytearray()
    for f in frames:
        if f.timestamp_ms is not None:
            out += bytes([FEND, CMD_TIMESTAMP]) + esc(f.timestamp_ms.to_bytes(8, "big")) + bytes([FEND])
        out += bytes([FEND, CMD_DATA]) + esc(f.payload) + bytes([FEND])
    return bytes(out)
