"""FUNcube-1 (AO-73, NORAD 39444) telemetry frame parser.

A decoded frame is 256 bytes: a 1-byte header (2-bit satellite id, 6-bit
frame type), 55 bytes of real-time telemetry, and 200 bytes of payload
(whole-orbit, high-resolution or fitter data depending on the frame type).

The frame type cycles 0..23, one frame every ~5 s, so a full frame set lasts
two minutes. The 24-bit sequence counter (bytes 50..52) increments once per
frame set. ``position = sequence * 24 + frame_type`` therefore advances by
exactly one per transmitted frame and is the on-board clock that the replay
detector checks against wall-clock reception time.

Field offsets below were verified against SatNOGS observations of AO-73
(e.g. obs 15261075): battery ≈ 7.9 V, reboot count stable, temperatures
≈ 20 °C, counter incrementing at frame type 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FRAME_LEN = 256
FRAMES_PER_SET = 24
NOMINAL_PERIOD_S = 5.0


@dataclass
class FuncubeFrame:
    raw: bytes
    sat_id: int
    frame_type: int
    sequence: int
    telemetry: dict[str, float] = field(default_factory=dict)

    @property
    def position(self) -> int:
        return self.sequence * FRAMES_PER_SET + self.frame_type


def _u16(b: bytes, i: int) -> int:
    return int.from_bytes(b[i:i + 2], "big")


def parse(raw: bytes) -> FuncubeFrame | None:
    if len(raw) != FRAME_LEN:
        return None
    hdr = raw[0]
    frame_type = hdr & 0x3F
    if frame_type >= FRAMES_PER_SET:
        return None
    telemetry = {
        "photo_voltage_x_mv": _u16(raw, 1),
        "photo_voltage_y_mv": _u16(raw, 3),
        "photo_voltage_z_mv": _u16(raw, 5),
        "photo_current_ma": _u16(raw, 7),
        "battery_voltage_mv": _u16(raw, 9),
        "system_current_ma": _u16(raw, 11),
        "reboot_count": _u16(raw, 13),
        "software_errors": _u16(raw, 15),
        "boost_temp_1_c": raw[17],
        "boost_temp_2_c": raw[18],
        "boost_temp_3_c": raw[19],
        "battery_temp_c": raw[20],
    }
    return FuncubeFrame(
        raw=raw,
        sat_id=hdr >> 6,
        frame_type=frame_type,
        sequence=int.from_bytes(raw[50:53], "big"),
        telemetry={k: float(v) for k, v in telemetry.items()},
    )


def with_position(raw: bytes, sequence: int, frame_type: int) -> bytes:
    """Return a copy of ``raw`` with header/counter rewritten (red-team use:
    models an attacker who forges the counter of a replayed frame)."""
    b = bytearray(raw)
    b[0] = (b[0] & 0xC0) | (frame_type & 0x3F)
    b[50:53] = (sequence & 0xFFFFFF).to_bytes(3, "big")
    return bytes(b)
