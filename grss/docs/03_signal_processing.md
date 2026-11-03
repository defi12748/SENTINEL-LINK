# Deliverable 3 — Signal processing

## Input

SatNOGS audio recordings (Ogg Vorbis, 48 kHz mono) of AO-73's 145.935 MHz DBPSK 1200 Bd downlink, after the
station's SSB demodulation and Doppler tuning. The BPSK signal sits at an audio offset that depends on the station
(≈ 11.4–11.8 kHz in our corpus), with a residual Doppler drift of tens of Hz over a pass.

## 1. Carrier estimation (`dsp/audio.estimate_bpsk_center`)

NRZ BPSK shows two spectral lobes at `fc ± baud/2`. Over a Welch PSD (16 384-point segments) we choose the `fc`
that maximises the *smaller* of the two lobe excesses over the median floor, so a jammer next to one lobe cannot
pull the estimate. Measured offsets match the ±600 Hz lines in the waterfall (e.g. 11 705 Hz for obs 15261075).

## 2. Demodulation and decoding (`decode/grsat.py`, `decode/wsl_ao40_blocks.py`)

* gr-satellites `FUNcube-1` flowgraph: frequency translation to `fc`, AGC, FLL (band-edge), polyphase clock
  recovery, then **differential** detection `Re(s[n]·s*[n−1])` (AO-73 is DBPSK).
* We run it once with `--dump_path` and read back the symbol stream (`clock_recovery_out`), the FLL frequency
  (`fll_freq`) and the AGC input level.
* **Per-block AO-40 FEC with timing.** gr-satellites' own KISS timestamps are wall-clock, useless for files
  processed at 70× real time. We search the 65-bit distributed syncword (one sync bit every 80 symbols) in the
  hard symbols, and feed each 5 200-symbol block on its own through gr-satellites' `ao40_fec_deframer`
  (de-interleave 80×65 → Viterbi r=½ k=7 → CCSDS descrambler → two interleaved RS(160,128)). Every decoded frame is
  bound to its sync symbol index → start time = index × duration / n_symbols.
* Result: **1 226 frames recovered from the 30 recordings vs 1 143 decoded live by the stations** (+7 %), and on
  obs 15261075 all 59 frames we decode are bit-identical to SatNOGS' own decodes (the station had 63; 4 were not
  recovered from the archived audio — not yet investigated).

## 3. Frame parsing (`decode/funcube.py`)

256 bytes: header (2-bit satellite id, 6-bit frame type 0–23), 55 bytes real-time telemetry, 200 bytes payload.
Offsets verified on real frames: photovoltages, photocurrent, battery voltage (~7.9 V), system current, reboot
counter, software errors, boost/battery temperatures, **24-bit sequence counter at bytes 50–52** (increments once
per 24-frame set). `position = 24·seq + type` advances once per frame.

## 4. Physical-layer tracks (10 Hz)

* **Carrier**: `f_c(t) = f_offset − FLL(t)·fs/2π` (sign checked against the Welch spectrum; the FLL reports its
  correction). It follows the residual Doppler of the pass.
* **Level**: power of the AGC input.

Used by the splice head: median carrier/level 0.4–2.9 s either side of each frame boundary, normalised by the
track's own MAD of first differences; and each frame's offset from a robust cubic fit of the whole-pass carrier.

## 5. Spectral evidence for interference (`dsp/spectral.py`)

STFT, 4 096-point Hann, hop 2 048 (11.7 Hz bins, 43 ms). Per 5 s window (hop 2.5 s), per bin:

| Feature | Meaning |
|---|---|
| prominence | mean power over a 129-bin running median baseline (dB) |
| spectral kurtosis `E[P²]/E[P]² − 2` | −1 constant-envelope tone, 0 Gaussian noise |
| persistence | fraction of frames ≥ 6 dB above baseline |
| −3 dB width | separates tones from narrowband noise |
| BPSK line imbalance | |prom(fc−600) − prom(fc+600)|: a jammer parked on a natural line |
| in-band excess, flatness | interference hidden under the signal |

The ±600 Hz BPSK lines are excluded from the "strongest peak" search but reported separately, so the natural
structure of the downlink is not mistaken for a jammer, while a jammer hiding on it still shows as imbalance.

## 6. Response: excision (`dsp/mitigate.py`)

For each alarm: estimate the −3 dB width around the detected frequency; IIR notch (Q = f₀/30) for tone-like
interferers (≤ 40 Hz), 6th-order Butterworth band-stop for wider ones; zero-phase filtering over the alarm interval
± 1 s; then re-decode. Recovered frame counts are in the benchmark (*Response* table).

## 7. Pass geometry (`geo.py`)

SGP4 on the observation's own TLE → sub-satellite track, station azimuth/elevation and range rate (Doppler).
Checked against SatNOGS metadata: max elevation 44.5° vs 45° reported; rise azimuth 183° vs 183°.
