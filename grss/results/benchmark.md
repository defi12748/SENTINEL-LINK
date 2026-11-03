# Benchmark results

Generated 2026-10-23T14:07:52+00:00 on Windows-10-10.0.19045-SP0 (Python 3.13.1, 12 logical CPUs). Satellite: AO-73 / FUNcube-1 (NORAD 39444). 17 held-out SatNOGS observations, seeds [1000, 1001, 1002].

## Frame-level detection (replay + sequence anomaly, decoded from attacked audio)

Brackets: 95 % Wilson intervals. Seeds share observations, so treat them as optimistic.

| Metric | Value |
|---|---|
| Attacked frames detected (TPR) | 99.3 % (581/585) [98.3–99.7 %] |
| False-alarm rate, attacked passes | 0.85 % (17/1989) [0.53–1.36 %] |
| False-alarm rate, clean passes | 0.29 % (2/695) |
| Precision / F1 (all) | 96.8 % / 98.1 % |
| ROC-AUC (all frames) | 0.9996 |
| Calibration error (ECE, 10 bins) | 0.0231 |
| Replay frames detected | 100.0 % |
| Sequence-anomaly frames detected | 93.3 % |
| Decision latency per frame (after decode) | 2.414 ms (p95 6.977 ms) |

| Event | Detected |
|---|---|
| standard/replay | 44/44 |
| standard/sequence | 41/41 |
| cross_pass_replay/replay | 16/16 |

## Narrowband interference (hidden J/S)

Alarm threshold 0.979 (set for 0.5 % window false alarms on clean calibration audio). A jammer counts as detected only if an alarm overlaps it in time and lies within 100 (+ half the bandwidth for nbnoise/chirp) Hz of its frequency.

| Metric | Value |
|---|---|
| Jammed recordings detected | 54.2 % (n=48) [40.3–67.4 %] |
| Any alarm during the jammer (no frequency match, old criterion) | 77.1 % |
| Clean recordings with any alarm | 7/17 [21.6–64.0 %] |
| Clean-window false-alarm rate | 0.88 % |
| Median jammer frequency error | 3.7 Hz |
| Head latency per 6-min recording | 13835.5 ms |

| J/S (dB) | n | Pd |
|---|---|---|
| [-40,-25) | 7 | 0.0 % |
| [-25,-20) | 2 | 50.0 % |
| [-20,-15) | 2 | 50.0 % |
| [-15,-10) | 10 | 40.0 % |
| [-10,-5) | 7 | 57.1 % |
| [-5,0) | 9 | 77.8 % |
| [0,10) | 11 | 81.8 % |

| Jammer kind | Pd |
|---|---|
| cw | 50.0 % |
| nbnoise | 50.0 % |
| chirp | 66.7 % |
| pulsed | 55.6 % |

Response (excision then re-decode):

| Obs | Jammer | J/S | Frames jammed | After excision | Clean reference |
|---|---|---|---|---|---|
| 15123656 | pulsed | -4.6 | 82 | 82 | 82 |
| 15211184 | pulsed | 0.7 | 0 | 12 | 32 |
| 15211184 | cw | -0.1 | 31 | 32 | 32 |
| 15211247 | nbnoise | 0.2 | 1 | 4 | 15 |
| 15222456 | pulsed | 9.6 | 3 | 5 | 37 |
| 15228452 | nbnoise | -1.4 | 34 | 34 | 43 |
| 15230978 | nbnoise | 4.5 | 38 | 38 | 37 |
| 15230978 | cw | -4.0 | 36 | 36 | 37 |

## Evasion (frame level, informed attacker)

| Attack | Detected |
|---|---|
| counter_forge_plus1 | 15/17 (88.2 %) |
| counter_forge_far | 17/17 (100.0 %) |
| content_forge_counter_consistent | 11/17 (64.7 %) |

## Trust anchor (SDLS emulation on real AO-73 frames)

| Service | Overhead | Apply | Verify | Replay rejected | Bit-flip rejected |
|---|---|---|---|---|---|
| AUTH | 22 B (8.59 %) | 4.37 µs | 7.06 µs | 100.0 % | 100.0 % |
| AUTH_ENC | 34 B (13.28 %) | 4.55 µs | 4.12 µs | 100.0 % | 100.0 % |

## Signed capture manifest

Clean recordings authentic: True · attacked recordings rejected: True

| Obs | Flagged seconds | Replay interval (s) | Sign | Verify | Size |
|---|---|---|---|---|---|
| obs_15081287 | 86 | [312.1, 347.0] | 0.26 s | 0.283 s | 47.9 kB |
| obs_15123656 | 434 | [255.8, 320.7] | 0.168 s | 0.164 s | 29.3 kB |
| obs_15208319 | 72 | [70.0, 134.8] | 0.115 s | 0.107 s | 18.2 kB |
| obs_15211184 | 310 | [226.9, 276.8] | 0.183 s | 0.18 s | 30.9 kB |
| obs_15211247 | 135 | [54.7, 79.6] | 0.117 s | 0.113 s | 20.1 kB |
| obs_15222456 | 171 | [207.9, 282.7] | 0.188 s | 0.188 s | 31.4 kB |

Peak RSS 43.8 MB · benchmark wall clock 2674.3 s.

## Duplicate-audio head (audio only, any satellite)

Generated 2026-10-28T18:50:54+00:00. Fixed threshold 0.5 (normalised correlation of 2 s blocks at 1000 Hz complex baseband), not fitted. Same held-out draws as above (seeds 1000, 1001, 1002).

| Metric | Value |
|---|---|
| In-pass replay detected | 48/48 [92.6–100.0 %] |
| Duplicated-slot anomaly detected | 22/22 [85.1–100.0 %] |
| Swapped-slot anomaly (copies nothing, not expected) | 0/26 |
| Clean recordings with a match (all 30) | 0/30 [0.0–11.3 %] |
| False matches on attacked recordings | 0 |
| Highest correlation on clean audio (held-out · all) | 0.272 · 0.272 |
| Latency per recording | 4706.0 ms |

| Evasion of the replay | Detected |
|---|---|
| vorbis_reencode | 16/16 (100.0 %) |
| inband_noise_-6db | 16/16 (100.0 %) |
| inband_noise_0db | 15/16 (93.8 %) |
| stretch_1e-5 | 16/16 (100.0 %) |
| stretch_1e-4 | 2/16 (12.5 %) |

## Interference persistence rule

Selected on the 3 calibration recordings only (detection within 5 points of the single-window rule; fewest clean alarm episodes per hour): min_windows=1, frequency stability off. Held-out results for every rule:

| Rule | Clean recordings alarmed | Alarm episodes / h | Jammers detected |
|---|---|---|---|
| 1 window(s) **(selected)** | 7/17 | 7.63 | 26/48 [40.3–67.4 %] |
| 2 window(s) | 2/17 | 2.54 | 23/48 [34.5–61.7 %] |
| 3 window(s) | 1/17 | 1.53 | 22/48 [32.6–59.7 %] |
| 4 window(s) | 1/17 | 1.02 | 22/48 [32.6–59.7 %] |
| 6 window(s) | 0/17 | 0.0 | 17/48 [23.4–49.6 %] |
| 1 window(s), ±50 Hz | 7/17 | 7.13 | 26/48 [40.3–67.4 %] |
| 2 window(s), ±50 Hz | 2/17 | 2.04 | 23/48 [34.5–61.7 %] |
| 3 window(s), ±50 Hz | 1/17 | 0.51 | 22/48 [32.6–59.7 %] |
| 4 window(s), ±50 Hz | 1/17 | 0.51 | 21/48 [30.7–57.7 %] |
| 6 window(s), ±50 Hz | 0/17 | 0.0 | 14/48 [18.2–43.2 %] |
