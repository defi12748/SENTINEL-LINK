"""Interoperability with NASA CryptoLib (CCSDS SDLS) on real AO-73 frames.

Requires the bridge: bash sentinel/trust/cryptolib_bridge/build.sh (Linux/WSL).
"""

import pytest

from sentinel.data.corpus import corpus_root, load_pass
from sentinel.trust.ccsds_tm import TmSdlsLink, cryptolib, cryptolib_available
from sentinel.trust.sdls import Verdict

pytestmark = pytest.mark.skipif(not cryptolib_available(), reason="NASA CryptoLib bridge not built")
KEY = bytes(range(32))


@pytest.fixture(scope="module")
def frames():
    return load_pass(corpus_root() / "obs_15261075").payloads[:20]


def test_cryptolib_apply_is_byte_identical_to_ours(frames):
    nasa = cryptolib("apply", KEY, [f.hex() for f in frames])
    ours = TmSdlsLink(KEY)
    assert nasa == [ours.apply(f).hex() for f in frames]


def test_cryptolib_accepts_our_frames(frames):
    ours = TmSdlsLink(KEY)
    out = cryptolib("process", KEY, [ours.apply(f).hex() for f in frames])
    assert [ln.split()[0] for ln in out] == ["0"] * len(frames)
    assert [bytes.fromhex(ln.split()[1]) for ln in out] == frames


def test_cryptolib_rejects_our_forgery(frames):
    ours = TmSdlsLink(KEY)
    good = bytearray(ours.apply(frames[0]))
    good[100] ^= 0x01                                  # flip a telemetry bit, keep CRC valid
    from sentinel.trust.ccsds_tm import crc16_ccitt
    good[-2:] = crc16_ccitt(bytes(good[:-2])).to_bytes(2, "big")
    status = cryptolib("process", KEY, [bytes(good).hex()])[0].split()[0]
    assert status != "0"                               # MAC validation error inside CryptoLib


def test_tm_replay_cryptolib_vs_sentinel(frames):
    """CryptoLib 1.7.5 performs anti-replay on TC only: a replayed TM frame
    with a valid MAC is accepted. Our receiver rejects it."""
    nasa_frames = cryptolib("apply", KEY, [f.hex() for f in frames[:5]])
    replayed = nasa_frames + [nasa_frames[1]]
    nasa_status = [ln.split()[0] for ln in cryptolib("process", KEY, replayed)]
    assert nasa_status[-1] == "0"                      # documented gap

    rx = TmSdlsLink(KEY)
    verdicts = [rx.process(bytes.fromhex(h))[0] for h in replayed]
    assert verdicts[:5] == [Verdict.ACCEPT] * 5 and verdicts[-1] is Verdict.REJECT_REPLAY
