# Deliverable 4 — AI and statistical detection

Five heads produce evidence; a calibrated fusion turns the first four into a probability and a response, and the
fifth (duplicate audio) raises any frame it covers to at least a verification request. Numbers quoted here
come from `results/benchmark.md` (held-out observations only).

## Head 1 — Clock consistency (statistical, physics-based)

AO-73's frame position `P = 24·seq + type` advances once per transmitted frame. A robust (iteratively trimmed)
linear model `P = a + b·t` is fitted on training passes:

* on-board frame period `1/b = 4.9885 s` (the spacecraft oscillator runs ≈0.23 % fast against the nominal 5 s);
* leave-one-pass-out on all 30 observations: every authentic frame of an unseen pass within **one frame**.

Per pass: offset `c = median(P − model)`. Per frame: `u = P − model − c`, split into
`u_behind` (counter lags the clock: replay) and `u_ahead` (counter leads: forged counter or audio dropout), both in
units of the in-pass σ; plus counter regression, duplicate positions and counter/time step error. The pass offset
only counts beyond a 10-frame tolerance (`pass_offset_excess`), the drift of a model extrapolated to later dates;
cross-pass replays sit hundreds to thousands of frames off.

## Head 2 — Physical splice

Carrier (FLL, residual Doppler) and level tracks at 10 Hz. Per frame boundary: step of the median over
0.4–2.9 s either side, scaled by the track's MAD of first differences. Per frame: offset of its median carrier
from a robust cubic fit of the whole-pass Doppler curve. Replayed audio carries the Doppler and level of the
moment it was recorded.

## Head 3 — Telemetry content (PyOD)

For each frame, the deviation of 12 housekeeping channels from the median of its ±4 in-pass neighbours, scaled by
per-channel noise learned on clean training passes. Score: **ECOD** (PyOD, parameter-free empirical-CDF outlier
detector) fitted on clean frames; reported as −log10 of the empirical tail probability. This head is what
remains when an informed attacker rewrites the counter of a frame taken from another pass.

## Head 4 — Interference (machine learning, calibrated)

Per 5 s window (hop 2.5 s): spectral evidence from `dsp/spectral.py` — strongest narrow excess and its spectral
kurtosis, persistence and width, number of elevated bins, BPSK-line imbalance and in-band excess, plus 30 s
context evidence: stable-line strength and duty (frequency-static emitters), narrowband plateau, BPSK spectral
asymmetry. Classifier: histogram gradient boosting, **isotonic calibration** (3-fold), class-balanced weights,
trained on real clean windows vs the same windows with synthetic jammers (CW, narrowband noise, swept, pulsed;
random frequency, bandwidth, timing; J/S −30…+10 dB). The alarm threshold is set on separate clean calibration
recordings for a target window false-alarm rate.

**Persistence rule (studied, not adopted).** An alarm could be required to last several windows, since a jammer
lasts while a passing spur does not (`alarm_runs(min_windows, freq_tol_hz)`). The rule was chosen in advance on the
three calibration recordings only (`py -m sentinel.bench.persistence`): keep jammer detection within 5 points of the
single-window rule and minimise clean alarm episodes per hour. On 24 calibration jammers every longer rule lost more
than 5 points, so the single-window rule stays. On the held-out recordings the trade-off is real: two windows would cut
clean recordings with an alarm from 7/17 to 2/17 at a cost of 26→23 of 48 jammers (`results/interference_persistence.json`).
We report this but do not switch, because picking the rule from held-out results would be tuning on the test set; a
larger calibration set is the honest way to decide.

## Head 5 — Duplicate audio (format-independent)

A genuine recording never contains the same stretch of receiver noise twice, while audio replayed inside a file is a
sample-for-sample copy of an earlier stretch, noise included. The head mixes the downlink band to a 1 kHz complex
baseband, whitens it with the file's own long-term spectrum (one fixed filter, so copies stay copies, but steady
tones such as a CW jammer or a station birdie no longer make distant blocks look alike), and cross-correlates 2 s
blocks against the whole recording by FFT. Blocks that match at the same lag form one duplicated segment; the later
copy is reported as the replay. The threshold (normalised correlation 0.5) was fixed before the benchmark; it is not
fitted.

It needs no decoder, frame format or training, so it still works when the held-out recording is not AO-73 and the
other heads have no frames. On the held-out set (`results/twin_benchmark.json`, `py -m sentinel.bench.twin`):
48/48 in-pass replays and 22/22 duplicated slots found, no match on any of the 30 clean recordings (highest clean
correlation 0.27, lowest replay 0.69), 4.7 s per recording. What it cannot see: a **swapped** pair of slots (a
permutation copies nothing), a **cross-pass** replay (the source is another file; an archive index would be needed),
and a copy **resampled by ≈100 ppm** (2/16 found), since a time-stretch decorrelates 2 s blocks. Vorbis re-encoding
(16/16), fresh noise at the in-band signal power (15/16) and a 10 ppm stretch (16/16) do not hide it.

## Fusion and response

Logistic regression on log-scaled, clipped evidence (11 inputs), trained on attacked and clean training passes
plus frame-level forgeries. No class re-weighting, so the output is a calibrated probability (ECE in the
benchmark). Decisions: `p < 0.5` ACCEPT · `0.5 ≤ p < 0.9` VERIFY · `p ≥ 0.9` QUARANTINE.

Learned weights (from `models/model_card.json`) are the explanation: counter-behind-clock and telemetry outlier
evidence dominate; splice evidence contributes where the clock is silent.

Additional responses:

* **Interference** → closed-loop excision: candidate responses (none, band-stop at the alarmed frequency,
  time–frequency mask) are each decoded and the one with the most Reed–Solomon-valid frames is kept.
* **Frames lost under interference** → the clock gives every position that should have been received; positions
  missing inside an alarm are reported as *unaccounted*, a verification request (a jammer can hide an injection).
* Every non-accepted frame and every run is appended to the signed hash-chained ledger.

## Evaluation protocol

Held-out observations (later dates / unseen stations), three random draws of the standard scenario per
observation plus one cross-pass replay, all applied to the real audio and **decoded again** by the full chain;
labels come from the attack intervals. Clean passes measure false alarms. Frame-level evasion uses informed
forgeries. Latency is measured after decoding (decoding itself runs at ≈35–70× real time).
