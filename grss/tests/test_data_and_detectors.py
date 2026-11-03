import json

import numpy as np
import pytest

from sentinel.data.corpus import corpus_root, load_corpus
from sentinel.decode import funcube
from sentinel.decode.kiss import KissFrame, read_kiss, write_kiss
from sentinel.detect.clock import ClockModel, frame_features
from sentinel.redteam import attacks

ROOT = corpus_root()
needs_corpus = pytest.mark.skipif(not (ROOT / "manifest.json").exists(), reason="SatNOGS corpus not fetched")


def test_kiss_roundtrip_with_escapes():
    frames = [KissFrame(bytes([0xC0, 0xDB, 1, 2]), 1_790_000_000_000), KissFrame(b"\x00" * 10, None)]
    back = read_kiss(write_kiss(frames))
    assert [f.payload for f in back] == [f.payload for f in frames]
    assert back[0].timestamp_ms == frames[0].timestamp_ms


@needs_corpus
def test_funcube_parser_on_real_frames():
    rec = json.loads((ROOT / "obs_15261075" / "record.json").read_text())
    raw = (ROOT / rec["frames"][0]["file"]).read_bytes()
    f = funcube.parse(raw)
    assert f is not None and 0 <= f.frame_type < 24
    assert 6000 < f.telemetry["battery_voltage_mv"] < 9000          # 2S Li-ion pack
    forged = funcube.with_position(raw, f.sequence + 3, (f.frame_type + 1) % 24)
    g = funcube.parse(forged)
    assert g.sequence == f.sequence + 3 and g.frame_type == (f.frame_type + 1) % 24


@needs_corpus
def test_clock_model_generalises_across_passes():
    passes = load_corpus()
    data = []
    for p in passes:
        parsed = p.parsed()
        idx = [i for i, fr in enumerate(parsed) if fr]
        data.append((p.t_utc[idx], np.array([parsed[i].position for i in idx])))
    worst = 0.0
    for k in range(len(data)):
        m = ClockModel.fit([d for j, d in enumerate(data) if j != k])
        worst = max(worst, float(np.abs(frame_features(m, *data[k])["u_frames"]).max()))
    assert 4.9 < m.period_s < 5.0
    assert worst < 1.0          # every authentic frame of an unseen pass within one frame


def test_interference_hits_requested_js():
    fs, fc = 48000, 11700.0
    rng = np.random.default_rng(0)
    t = np.arange(fs * 20) / fs
    bits = np.repeat(rng.choice([-1.0, 1.0], size=int(20 * 1200) + 1), 40)[: len(t)]
    x = (0.3 * bits * np.cos(2 * np.pi * fc * t) + 0.05 * rng.standard_normal(len(t))).astype(np.float32)
    spec = attacks.Interference(kind="cw", freq_hz=5000.0, js_db=-10.0)
    y, truth = attacks.add_interference(x, fs, fc, spec, rng)
    j = y - x
    measured = 10 * np.log10(np.mean(j.astype(float) ** 2) / truth["signal_power"])
    assert abs(measured - (-10.0)) < 0.5


def test_replay_labels_cover_overwritten_frames():
    fs = 1000
    t = np.arange(20) * attacks.SLOT_S + 0.5
    x = np.arange(int(t[-1] * fs) + 10 * fs, dtype=np.float32)
    y, tr = attacks.replay_overwrite(x, fs, t, n_frames=6, src_idx=2, dst_idx=10)
    lab = attacks.labels_for_interval(t, tr["dst_start_s"], tr["dst_end_s"])
    assert list(np.flatnonzero(lab)) == list(range(10, 16))
    assert np.array_equal(y[int(tr["dst_start_s"] * fs): int(tr["dst_start_s"] * fs) + 100],
                          x[int(tr["src_start_s"] * fs): int(tr["src_start_s"] * fs) + 100])


def test_pipeline_handles_pass_with_no_decoded_frames():
    """A jammer can destroy every frame; analysis must still return cleanly."""
    from sentinel.data.corpus import Pass
    from sentinel.pipeline import analyse_pass
    from sentinel.train import MODEL_PATH, load_models
    if not MODEL_PATH.exists():
        pytest.skip("models not trained")
    empty = Pass(observation_id=0, station="", start_utc=1.79e9, t_rec=np.zeros(0), payloads=[],
                 track_t=np.zeros(0), carrier_hz=np.zeros(0), level_db=np.zeros(0), tle=("", ""),
                 station_lla=(0.0, 0.0, 0.0))
    assert analyse_pass(load_models(), empty) == []
