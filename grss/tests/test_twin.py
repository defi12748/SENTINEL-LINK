import numpy as np

from sentinel.detect import twin

FS = 48000
FC = 11500.0


def _recording(seconds: float = 90.0, seed: int = 0) -> np.ndarray:
    """Noise plus a slowly drifting carrier, like a Doppler-tracked downlink."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * FS)) / FS
    carrier = 0.3 * np.cos(2 * np.pi * (FC + 20 * np.sin(2 * np.pi * t / 600)) * t)
    return (carrier + rng.standard_normal(len(t))).astype(np.float32)


def test_clean_recording_has_no_twins():
    r = twin.detect(_recording(), FS, FC)
    assert r.matches == []
    assert r.block_ncc.max() < 0.2


def test_copied_stretch_is_found_and_located():
    x = _recording()
    src, dst, length = 10.0, 50.0, 25.0
    x[int(dst * FS):int((dst + length) * FS)] = x[int(src * FS):int((src + length) * FS)]
    x += 0.05 * np.random.default_rng(1).standard_normal(len(x)).astype(np.float32)   # added interference/noise
    r = twin.detect(x, FS, FC)
    assert len(r.matches) == 1
    m = r.matches[0]
    assert abs(m.start_s - dst) < twin.BLOCK_S and abs(m.end_s - (dst + length)) < twin.BLOCK_S
    assert abs(m.src_start_s - src) < twin.BLOCK_S and abs(m.lag_s - (dst - src)) < 0.01
    assert r.covers(np.array([dst + 5, src + 5, 80.0])).tolist() == [True, True, False]


def test_swapped_slots_are_not_a_copy():
    x = _recording()
    a, b, n = int(20 * FS), int(30 * FS), int(5 * FS)
    x[a:a + n], x[b:b + n] = x[b:b + n].copy(), x[a:a + n].copy()
    assert twin.detect(x, FS, FC).matches == []


def test_digital_silence_is_not_a_twin():
    x = _recording()
    x[int(30 * FS):int(40 * FS)] = 0.0
    x[int(60 * FS):int(70 * FS)] = 0.0
    assert twin.detect(x, FS, FC).matches == []


def test_steady_tone_near_the_downlink_is_not_a_twin():
    x = _recording()
    t = np.arange(len(x)) / FS
    x += (3.0 * np.cos(2 * np.pi * (FC + 150) * t)).astype(np.float32)   # strong CW jammer in band
    assert twin.detect(x, FS, FC).matches == []
