# Deliverable 1 — Threat model and segment analysis

## Segment

The **space–ground link and the ground segment that records it**: RF downlink → receiver/SDR → demodulator →
recording archive → frame decoder → telemetry/EO product pipeline → analyst. Reference system: SatNOGS-style
open ground stations receiving AO-73 (FUNcube-1) DBPSK 1200 Bd telemetry; the same analysis applies to any
cubesat downlink without link-layer authentication.

## Why a silent failure here matters

Downlinked telemetry and EO data are consumed long after reception: housekeeping decides whether a payload is
healthy, frame timing places every measurement on the orbit, and archived recordings are re-processed for products
used in agriculture, insurance, water management and disaster response. A corrupted stretch that still decodes
does not stop that pipeline; it flows on as plausible data. The consequences on this segment:

| Attack | What the analyst sees | Downstream effect |
|---|---|---|
| Replay of 5–20 frames | Nominal housekeeping, correct format, valid FEC | A developing fault (battery, thermal, attitude) is hidden for the replay duration; measurements are tagged with the wrong time and orbit position |
| One injected / reordered frame | A single plausible frame | Corrupts state tracking and time-series products; a single false value can trigger or suppress an operational alarm |
| Narrowband interference | Fewer frames, or none, over part of the pass | Data gaps that look like ordinary fading; a jammer can also mask the moment a replay or injection starts |

**Checksums are not authentication.** AO-73 frames, like most amateur and many EO cubesat downlinks, are protected by
Reed–Solomon FEC and CRCs. These detect channel errors only: the codes are public and keyless, so anyone who forges or
re-encodes a frame recomputes them in microseconds, and a replayed frame carries its original, valid ones. Valid FEC
says nothing about origin or time. This is why the testbed separates *prevention* (SDLS MAC + anti-replay counter on a
link we control) from *detection* (physical and statistical evidence on links that carry no MAC).

## Assets

| Asset | Why it matters |
|---|---|
| Frame content (housekeeping/EO telemetry) | Drives operational and scientific decisions |
| Frame order and timing | Telemetry is interpreted against time (orbit position, eclipse, events) |
| Stored recordings | Re-processed later; evidence for anomaly investigations |
| Detector decisions / audit trail | Must be trustworthy to be acted upon |
| Keys (SDLS SA keys, station signing key) | Root of every cryptographic guarantee |

## Adversary

Capabilities assumed, in increasing strength:

1. **Passive recorder** — has recordings of past passes (public: SatNOGS publishes them).
2. **Replay attacker** — re-transmits or splices previously recorded frames into a live or stored stream.
3. **Signal-level attacker** — adds narrowband interference (CW, narrowband noise, swept or pulsed tones) at a
   chosen power; can splice audio on frame boundaries so replayed frames still decode.
4. **Informed attacker** — knows the frame format, rewrites counters, re-encodes FEC, and knows our detectors.

Out of scope: physical compromise of the spacecraft, insiders holding the station signing key, RF denial of
service so strong that nothing is received (detected but not mitigable in software), radiated attacks (the testbed
is file/conducted only, per the challenge safety rule).

## STRIDE on the link

| Threat | Example on this segment | Control in SENTINEL-LINK |
|---|---|---|
| **S**poofing | Forged frame with plausible content | SDLS MAC (prevented); telemetry + clock heads (detected) |
| **T**ampering | Edited stored recording; altered counter | Signed per-second Merkle manifest (localised); clock head |
| **R**epudiation | "That decision was never made" | Hash-chained ledger, signed checkpoints |
| **I**nformation disclosure | Telemetry readable by anyone | SDLS AUTH_ENC (AES-256-GCM) on our own link |
| **D**enial of service | Narrowband jammer on the downlink | Interference head + excision; frames lost are reported |
| **E**levation | Poisoned anti-replay state via forged frame | Window advanced only after MAC verification |

## Attack tree for the standard test

```
Corrupt what the analyst sees without being noticed
├── Replay valid frames (5–20) ........................ clock head, splice head, manifest, SDLS ARSN
│   ├── from the same pass (short delay) ............. counter lags clock by the delay (≥ 1 frame)
│   ├── from another pass ............................. pass offset of thousands of frames; Doppler mismatch
│   └── with counters rewritten to look fresh ......... telemetry head; splice head; SDLS MAC
├── Inject one sequence anomaly ........................ clock head (duplicate / out-of-order / gap)
└── Hide it under interference at a hidden SNR ......... interference head; excision recovers frames
```

## Residual risk (stated honestly)

* A frame forged with a clock-consistent counter **and** telemetry close to its neighbours, re-modulated with the
  right Doppler and level, is not detectable without cryptography — this is the argument for SDLS on links we
  control and for signed capture at the station.
* Very weak interference (J/S far below the signal) is not detected; it also does not affect decoding (see the
  Pd-vs-J/S curve and the response table in the benchmark).
* The clock model must be re-fitted after an on-board reboot/counter reset; such a pass raises a pass-level offset
  and is routed to *verification*, not silently accepted.
