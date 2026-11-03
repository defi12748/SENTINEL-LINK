import numpy as np
import pytest

from sentinel.trust import ledger, merkle
from sentinel.trust.manifest import StationKey, create_manifest, verify_manifest
from sentinel.trust.sdls import KeyStore, SdlsEndpoint, SecurityAssociation, Service, Verdict


@pytest.fixture(params=[Service.AUTH, Service.AUTH_ENC])
def link(request):
    ks = KeyStore(b"k" * 32)
    rx = SdlsEndpoint(ks)
    rx.add_sa(0x0101, service=request.param, window=16)
    tx = SecurityAssociation(spi=0x0101, key=ks.derive(0x0101), service=request.param)
    return tx, rx


def test_sdls_accepts_fresh_frames(link):
    tx, rx = link
    for i in range(10):
        v, payload, arsn = rx.process(tx.apply(f"tlm-{i}".encode()))
        assert v is Verdict.ACCEPT and payload == f"tlm-{i}".encode() and arsn == i + 1


def test_sdls_rejects_replay_and_stale(link):
    tx, rx = link
    frames = [tx.apply(f"tlm-{i}".encode()) for i in range(40)]
    for f in frames[:30]:
        rx.process(f)
    assert rx.process(frames[25])[0] is Verdict.REJECT_REPLAY      # inside window
    assert rx.process(frames[5])[0] is Verdict.REJECT_STALE        # older than window


def test_sdls_accepts_reordered_once(link):
    tx, rx = link
    a, b, c = (tx.apply(bytes([i])) for i in range(3))
    assert rx.process(a)[0] is Verdict.ACCEPT
    assert rx.process(c)[0] is Verdict.ACCEPT
    assert rx.process(b)[0] is Verdict.ACCEPT       # late but new
    assert rx.process(b)[0] is Verdict.REJECT_REPLAY


def test_sdls_rejects_tamper_and_forged_counter(link):
    tx, rx = link
    good = bytearray(tx.apply(b"battery=7.9V"))
    tampered = bytes(good[:-20]) + bytes([good[-20] ^ 1]) + bytes(good[-19:])
    assert rx.process(tampered)[0] is Verdict.REJECT_MAC
    forged = bytearray(good)
    hdr = 2 + (12 if tx.service is Service.AUTH_ENC else 0)
    forged[hdr:hdr + 4] = (999).to_bytes(4, "big")        # attacker bumps ARSN
    assert rx.process(bytes(forged))[0] is Verdict.REJECT_MAC
    assert rx.process(bytes(good))[0] is Verdict.ACCEPT    # forged frame did not move the window


def test_sdls_unknown_spi():
    ks = KeyStore(b"k" * 32)
    rx = SdlsEndpoint(ks)
    tx = SecurityAssociation(spi=7, key=ks.derive(7))
    assert rx.process(tx.apply(b"x"))[0] is Verdict.REJECT_UNKNOWN_SPI


def test_merkle_proofs():
    leaves = [merkle.leaf_hash(bytes([i])) for i in range(13)]
    r = merkle.root(leaves)
    for i in range(13):
        assert merkle.verify_proof(leaves[i], merkle.proof(leaves, i), r)
    assert not merkle.verify_proof(merkle.leaf_hash(b"x"), merkle.proof(leaves, 3), r)


def test_manifest_localises_tampering():
    fs = 8000
    rng = np.random.default_rng(0)
    x = (0.1 * rng.standard_normal(fs * 10)).astype(np.float32)
    key = StationKey.generate()
    m = create_manifest(x, fs, {"observation_id": 1}, key)
    assert verify_manifest(m, x, fs, key.public_b64()).authentic

    y = x.copy()
    y[3 * fs + 100: 5 * fs - 100] = y[0: 2 * fs - 200]       # splice inside seconds 3-4
    chk = verify_manifest(m, y, fs, key.public_b64())
    assert not chk.authentic and chk.tampered_chunks == [3, 4]
    assert chk.tampered_intervals(1.0) == [(3.0, 5.0)]

    other = StationKey.generate()
    assert not verify_manifest(m, x, fs, other.public_b64()).signature_valid


def test_ledger_detects_rewrite():
    key = StationKey.generate()
    lg = ledger.Ledger(key, checkpoint_every=4)
    for i in range(10):
        lg.append("frame", {"i": i, "verdict": "ACCEPT"})
    entries = [dict(e) for e in lg.entries]
    assert ledger.verify(entries, key.public_b64()).valid

    entries[3] = {**entries[3], "data": {"i": 3, "verdict": "QUARANTINE"}}
    chk = ledger.verify(entries, key.public_b64())
    assert not chk.valid and chk.first_broken == 3


def test_ledger_rejects_foreign_checkpoint_key():
    lg = ledger.Ledger(StationKey.generate(), checkpoint_every=2)
    for i in range(4):
        lg.append("frame", {"i": i})
    assert not ledger.verify(lg.entries, StationKey.generate().public_b64()).valid
