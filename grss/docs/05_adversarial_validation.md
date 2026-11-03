# Deliverable 5 — Adversarial validation and response

Measured values for every row below are in `results/benchmark.md` (generated) and summarised in the README.

## Attacks applied (all on real SatNOGS audio, then decoded again by the full chain)

| Attack | Implementation (`sentinel/redteam`) | What it models |
|---|---|---|
| Replay of 5–20 frames, same pass | `attacks.replay_overwrite`: earlier frame slots overwrite later ones, cut 0.3 s before a frame start (inside the idle gap) so replayed frames decode cleanly | attacker who records and re-transmits / splices |
| Replay from another pass | same, source audio from a different observation (and station) | archive replay |
| Sequence anomaly | `slot_duplicate` (one frame re-sent in place of the next) or `slot_swap` (two frames out of order) | single injected / reordered frame |
| Narrowband interference at hidden J/S | `add_interference`: CW, narrowband Gaussian noise (20–400 Hz), swept tone, pulsed tone; random frequency (35 % on/near the downlink), random start/duration, J/S −30…+10 dB vs the in-band signal power | digitally added jammer |
| Counter forged +1 / far ahead | `frames_counter_forge` | informed attacker rewriting counters |
| Counter-consistent content forgery | `frames_content_forge`: frame from another pass, counter rewritten to the expected value | strongest frame-level evasion |
| Edited recording vs signed manifest | any of the above against a manifest signed on the clean recording | stored-signal tampering |
| SDLS replay / bit-flip / forged ARSN | `trust` tests, API demo, benchmark | attacks on the authenticated link |

Hidden parameters are drawn with `numpy.random.default_rng([seed, observation_id])`; the detectors never see them.

## Protocol

* Models trained on the 13 training observations only; 17 held-out observations (later dates, unseen stations).
* Per held-out observation: 3 random standard-test draws + 1 cross-pass replay, decoded by gr-satellites; labels are
  the attacked intervals, scored per decoded frame and per event.
* Clean held-out recordings measure false alarms (frames and interference windows).
* Interference: detection = an alarm overlapping the jammer interval; Pd reported vs J/S and vs J/N.

## Response

| Condition | Response |
|---|---|
| p ≥ 0.9 | QUARANTINE: frame withheld from the product pipeline, ledger entry |
| 0.5 ≤ p < 0.9 | VERIFY: request confirmation (e.g. a second station's recording of the same pass) |
| Interference alarm | closed-loop excision: none / band-stop / time–frequency mask, keep the option with most RS-valid frames |
| Frames missing under an alarm | VERIFY: positions the on-board clock says were transmitted but are unaccounted |
| Manifest mismatch | recording flagged tampered, edited seconds listed |
| SDLS failure | frame rejected by the receiver (MAC / replay / stale), counted per SA |

Duplicate-audio head, evasion of the in-pass replay by an attacker who knows it (`sentinel/bench/twin.py`, one draw per
held-out observation): attacked file re-encoded as Ogg Vorbis; fresh white noise over the copy at −6 dB and 0 dB of the
in-band power; copy resampled by 10 and 100 ppm. Measured values are in `results/benchmark.md`.

## Evasion analysis — what still gets through

1. **Counter-consistent forgery with neighbour-consistent telemetry**, re-modulated with the right Doppler and level:
   indistinguishable without cryptography. Mitigation: SDLS on links we control; signed capture at the station.
2. **Very weak interference** (well below the in-band noise): often not detected; at these levels decoding is not
   affected either (no frames lost), which is what the lost-frame accounting checks.
3. **Jammer inside a station's known-RFI range, below that emitter's level**: masked by the site survey by design.
4. **Unknown station with strong recurring spurs**: no site survey yet → more interference false alarms until a few
   passes from that station have been archived.
5. **Clock-model staleness**: an on-board reboot / counter reset moves the whole pass; it is reported as a pass-level
   offset for verification rather than as replay, and the model is refitted.
6. **NASA CryptoLib TM path without anti-replay** (observed in v1.7.5 as shipped with NOS3): a replayed TM frame with a
   valid MAC is accepted by CryptoLib; our receiver's ARSN window rejects it (`tests/test_cryptolib_interop.py`).
7. **Resampled copy against the duplicate-audio head**: stretching the replayed audio by ≈100 ppm decorrelates the
   2 s blocks (2/16 found). The clock and splice heads still see such a replay on AO-73; for other satellites the
   head would need a search over time-scale as well as lag.
