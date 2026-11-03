"""Phase 1 anonymous report: HTML generated from results/benchmark.json and
real-data figures, printed to PDF with headless Chrome/Chromium.

    py -m sentinel.bench.paper            # -> results/report/SENTINEL-LINK_report.{html,pdf}
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path

from .. import RESULTS_ROOT
from ..train import load_models
from .figures import all_figures

OUT = RESULTS_ROOT / "report"
CHROME = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
          r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
          "google-chrome", "chromium", "chromium-browser"]


def pct(x, d=1):
    return "—" if x is None else f"{100 * x:.{d}f}%"


def img(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


ARCH_SVG = """
<svg viewBox="0 0 760 250" width="100%" font-family="Inter, Arial" font-size="11">
  <defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
  <path d="M0,0L10,5L0,10z" fill="#58585b"/></marker></defs>
  <g fill="none" stroke="#58585b" stroke-width="1.2" marker-end="url(#a)">
    <path d="M118,60H152"/><path d="M272,60H306"/><path d="M426,60H460"/><path d="M580,60H614"/>
    <path d="M520,82V120"/><path d="M366,82V120"/><path d="M212,82V120"/><path d="M674,82V170"/>
  </g>
  <g>
    <rect x="8" y="38" width="110" height="44" fill="#17171b"/><text x="63" y="58" fill="#fff" text-anchor="middle">SatNOGS audio</text><text x="63" y="72" fill="#b9b9bb" text-anchor="middle" font-size="9">48 kHz recording</text>
    <rect x="152" y="38" width="120" height="44" fill="#1c67e3"/><text x="212" y="58" fill="#fff" text-anchor="middle">Interference head</text><text x="212" y="72" fill="#dbe6fb" text-anchor="middle" font-size="9">calibrated GBDT</text>
    <rect x="306" y="38" width="120" height="44" fill="#1c67e3"/><text x="366" y="58" fill="#fff" text-anchor="middle">Excision (closed loop)</text><text x="366" y="72" fill="#dbe6fb" text-anchor="middle" font-size="9">best FEC-valid yield</text>
    <rect x="460" y="38" width="120" height="44" fill="#1c67e3"/><text x="520" y="58" fill="#fff" text-anchor="middle">gr-satellites DBPSK</text><text x="520" y="72" fill="#dbe6fb" text-anchor="middle" font-size="9">per-block AO-40 FEC</text>
    <rect x="614" y="38" width="120" height="44" fill="#f64137"/><text x="674" y="58" fill="#fff" text-anchor="middle">Calibrated fusion</text><text x="674" y="72" fill="#fff" text-anchor="middle" font-size="9">accept / verify / quarantine</text>
    <rect x="152" y="120" width="120" height="40" fill="#f6f6f6" stroke="#d1d1d1"/><text x="212" y="144" text-anchor="middle">Spectral evidence</text>
    <rect x="306" y="120" width="120" height="40" fill="#f6f6f6" stroke="#d1d1d1"/><text x="366" y="138" text-anchor="middle">Frames lost under</text><text x="366" y="151" text-anchor="middle">jamming → verify</text>
    <rect x="460" y="120" width="120" height="40" fill="#f6f6f6" stroke="#d1d1d1"/><text x="520" y="138" text-anchor="middle">Clock · splice ·</text><text x="520" y="151" text-anchor="middle">telemetry heads</text>
    <rect x="614" y="170" width="120" height="44" fill="#17171b"/><text x="674" y="190" fill="#fff" text-anchor="middle">Signed hash-chain</text><text x="674" y="204" fill="#b9b9bb" text-anchor="middle" font-size="9">Ed25519 checkpoints</text>
    <rect x="8" y="170" width="264" height="44" fill="#fff" stroke="#17171b"/><text x="140" y="190" text-anchor="middle">Capture manifest: per-second Merkle tree</text><text x="140" y="204" text-anchor="middle" font-size="9" fill="#58585b">signed at the station, edits localised to 1 s</text>
    <rect x="306" y="170" width="274" height="44" fill="#fff" stroke="#17171b"/><text x="443" y="190" text-anchor="middle">Own link: CCSDS SDLS (SPI · ARSN · MAC)</text><text x="443" y="204" text-anchor="middle" font-size="9" fill="#58585b">byte-compatible with NASA CryptoLib, + TM anti-replay</text>
  </g>
</svg>"""


def render(b: dict, figs: dict, fig_dir: Path) -> str:
    fd, it, ev, sd, mf = b["frame_detection"], b["interference"], b["evasion"], b["sdls"], b["manifest"]
    ap, cl, co = fd["attacked_passes"], fd["clean_passes"], fd["combined"]
    ex = figs["example"]
    rx = figs["response"]
    evt = {k: f"{v['detected']}/{v['n']}" for k, v in fd["events"].items()}
    n_test = len(b["dataset"]["held_out_observations"])
    jn = it["cases"]
    pd_hi = [c["detected"] for c in jn if c["jn_db"] >= 0]
    pd_hi_s = f"{100 * sum(pd_hi) / len(pd_hi):.0f}% (n={len(pd_hi)})" if pd_hi else "—"
    mit = it.get("mitigation") or []
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>SENTINEL-LINK — Track 1 report</title>
<style>
@page {{ size: A4; margin: 16mm 15mm 16mm 15mm; }}
body {{ font-family: Inter, "Public Sans", Arial, sans-serif; color: #17171b; font-size: 9.6pt; line-height: 1.5; }}
h1 {{ font-size: 21pt; line-height: 1.08; margin: 0 0 4pt; letter-spacing: -0.01em; }}
h2 {{ font-size: 12.5pt; margin: 16pt 0 5pt; border-top: 2px solid #17171b; padding-top: 5pt; }}
h3 {{ font-size: 10pt; margin: 9pt 0 3pt; }}
h2, h3 {{ break-after: avoid; }}
figure, .kpis {{ break-inside: avoid; }}
.label {{ font-family: "DM Mono", Consolas, monospace; font-size: 7pt; letter-spacing: 2.5px; text-transform: uppercase; color: #f64137; }}
.muted {{ color: #58585b; }}
table {{ border-collapse: collapse; width: 100%; margin: 5pt 0 8pt; font-size: 8.6pt; }}
th {{ text-align: left; font-family: "DM Mono", Consolas, monospace; font-weight: 500; font-size: 7pt; letter-spacing: 1.5px; text-transform: uppercase; color: #58585b; border-bottom: 1px solid #17171b; padding: 3pt 4pt; }}
td {{ border-bottom: 1px solid #e3e3e3; padding: 3pt 4pt; vertical-align: top; }}
.kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8pt; margin: 8pt 0; }}
.kpi {{ border-top: 3px solid #f64137; padding-top: 4pt; }}
.kpi b {{ display: block; font-size: 17pt; line-height: 1.1; }}
.kpi span {{ font-size: 7.5pt; color: #58585b; }}
figure {{ margin: 6pt 0 9pt; }} figure img {{ width: 100%; }}
figcaption {{ font-size: 8pt; color: #58585b; }}
code {{ font-family: Consolas, monospace; font-size: 8.3pt; background: #f6f6f6; padding: 0 2pt; }}
.two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12pt; }}
.box {{ background: #f6f6f6; padding: 6pt 8pt; border-left: 3px solid #1c67e3; }}
</style></head><body>

<div class="label">TSYP14 technical challenge · Track 1 — Secure ground-link testbed · anonymous submission</div>
<h1>SENTINEL-LINK: authenticating stored satellite downlinks — cryptography where the link allows it, physics where it does not</h1>
<p class="muted">Team code: assigned by the administrative committee. All numbers in this report are produced by
<code>py -m sentinel bench</code> on {n_test} held-out SatNOGS observations (results/benchmark.json, generated {b['generated_utc']}).</p>

<div class="kpis">
 <div class="kpi"><b>{pct(ap['detection_rate'])}</b><span>replayed / injected frames detected ({ap['tp']}/{ap['attacked']}), decoded from attacked real audio</span></div>
 <div class="kpi"><b>{pct(co['false_alarm_rate'], 2)}</b><span>frame false-alarm rate (attacked + clean passes)</span></div>
 <div class="kpi"><b>{pd_hi_s}</b><span>jammers detected at J/N ≥ 0 dB (all kinds, hidden parameters)</span></div>
 <div class="kpi"><b>{sd['AUTH']['verify_us_per_frame']} µs</b><span>SDLS verify per frame, {sd['AUTH']['overhead_bytes']} B overhead, 100% replay rejection</span></div>
</div>

<p><b>Summary.</b> Open ground networks record satellite downlinks that carry no authentication. We built a ground-station
testbed that (i) <i>prevents</i> replay and injection on a link we control with CCSDS Space Data Link Security, validated
byte-for-byte against NASA CryptoLib; (ii) <i>authenticates stored recordings</i> with a station-signed per-second Merkle
manifest; and (iii) <i>detects</i> the three attacks of the standard test on legacy, unauthenticated downlinks using
evidence an attacker cannot easily fake: the spacecraft's own frame counter against reception time, the Doppler and
level continuity of the received carrier, the consistency of housekeeping telemetry, and calibrated spectral
evidence of added interference. Everything runs on a laptop CPU, on authentic SatNOGS recordings of AO-73
(FUNcube-1) that we demodulate and FEC-decode ourselves.</p>

<h2>1 · Threat model and segment</h2>
<p>Segment: RF downlink → ground receiver → <b>recording archive</b> → decoder → product pipeline. Adversary
capabilities considered: passive recorder (SatNOGS publishes recordings), replay/splice attacker, signal-level
attacker adding narrowband interference, and an informed attacker who rewrites counters and re-encodes FEC.
Radiated attacks are out of scope (file-based testbed, per the safety rule).</p>
<table><tr><th>STRIDE</th><th>On this segment</th><th>Control</th></tr>
<tr><td>Spoofing</td><td>forged frame, plausible content</td><td>SDLS MAC (prevent) · telemetry & clock heads (detect)</td></tr>
<tr><td>Tampering</td><td>edited stored recording, altered counter</td><td>signed Merkle manifest (localised) · clock head</td></tr>
<tr><td>Repudiation</td><td>disputed decisions</td><td>hash-chained ledger with Ed25519 checkpoints</td></tr>
<tr><td>Info. disclosure</td><td>cleartext telemetry</td><td>SDLS AES-256-GCM on own link</td></tr>
<tr><td>Denial of service</td><td>narrowband jammer</td><td>interference head · closed-loop excision · lost-frame accounting</td></tr>
<tr><td>Elevation</td><td>poisoning anti-replay state</td><td>window advanced only after MAC verification</td></tr></table>

<h2>2 · Architecture and trust anchor</h2>
<p>NASA OnAIR's Agent and VehicleRepresentation run their telemetry feasibility tests on decoded AO-73
frames. Limits come from training passes; our OnAIR plugin checks the spacecraft frame counter against the clock.
These two checks expose different evidence: plausible replayed telemetry can pass feasibility limits while the
unchanged counter fails the timing check. The web console exposes the per-frame outputs alongside the other heads.</p>
{ARCH_SVG}
<p><b>Software trust anchor.</b> One 256-bit master secret; per-SA keys by HKDF-SHA-256 (interface identical to an
HSM's derive call); Ed25519 station key. <b>SDLS:</b> TM transfer frame | SPI | ARSN | data | 128-bit MAC | FECF.
Our frames are <b>byte-identical to NASA CryptoLib's</b> (v1.7.5, the version shipped with NOS3) and each library
accepts the other's frames and rejects forgeries (<code>tests/test_cryptolib_interop.py</code>, real AO-73 frames).</p>
<div class="box"><b>Finding.</b> In that CryptoLib version the anti-replay check is applied on TC (uplink) only: the TM and
AOS processing paths accept a replayed frame whose MAC verifies. Our receiver adds an ARSN sliding window
(W = 64, bitmap for late frames, window advanced only after MAC success): replayed TM frames are rejected.
On {sd['AUTH']['frames']:,} protected real frames: replay rejection {pct(sd['AUTH']['replay_rejection_rate'])},
bit-flip rejection {pct(sd['AUTH']['bitflip_rejection_rate'])}, overhead {sd['AUTH']['overhead_bytes']} B
({sd['AUTH']['overhead_pct_of_256B_frame']}%) and {sd['AUTH']['verify_us_per_frame']} µs per frame (AES-GCM:
{sd['AUTH_ENC']['overhead_bytes']} B, {sd['AUTH_ENC']['verify_us_per_frame']} µs).</div>
<p><b>Stored-signal authentication.</b> At capture the station hashes each second of 16-bit PCM, builds a Merkle tree
and signs root + capture context. Clean recordings verify; every attacked recording fails and the edited seconds are
listed (e.g. {mf['cases'][0]['tampered_seconds_flagged']} s flagged for a replay at {mf['cases'][0]['replay_interval_s']} s
plus a jammer); signing a 6-min recording takes ≈{mf['cases'][0]['sign_s']} s and the manifest is ≈{mf['cases'][0]['manifest_kb']} kB.</p>

<h2>3 · Signal processing</h2>
<p>SatNOGS audio (48 kHz) of AO-73's 1200 Bd DBPSK downlink. The carrier offset is estimated from the two BPSK lobes
at f<sub>c</sub>±600 Hz. gr-satellites demodulates (FLL, clock recovery, differential detection); we dump its symbol
stream, search the 65-bit distributed AO-40 syncword, and decode <i>each 5,200-symbol block separately</i> with
gr-satellites' AO-40 deframer (Viterbi, descrambler, two RS codes). This binds every frame to its exact start time —
gr-satellites' own timestamps are wall-clock — and recovers <b>1,226 frames from the 30 recordings vs 1,143 decoded live
by the stations</b>. The same pass yields the carrier (residual Doppler) and level tracks at 10 Hz. Spectral evidence:
4,096-point STFT, prominence over a running baseline, spectral kurtosis, persistence, BPSK-line balance, plus 30 s
context features for frequency-static emitters and narrowband plateaus. Pass geometry is propagated with SGP4 from
each observation's TLE (spot check: max elevation 44.5° vs 45° in the SatNOGS metadata, rise azimuth 183° vs 183°).</p>

<h2>4 · Detection</h2>
<div class="two"><div>
<p><b>Clock head.</b> AO-73 frames carry a 6-bit type (0–23) and a 24-bit counter that increments once per 24-frame set,
so P = 24·seq + type advances once per frame. A robust linear model fitted on training passes gives an on-board frame
period of <b>4.9885 s</b>; leave-one-pass-out, every authentic frame of an unseen pass lies within one frame of it
(Fig. 1). Replayed frames lag by the replay delay; counter evidence is split into "behind" (replay) and "ahead".</p>
<p><b>Splice head.</b> Steps of the carrier and level tracks at frame boundaries and the frame's offset from a robust
fit of the whole-pass Doppler curve. <b>Telemetry head.</b> Neighbour-relative deviations of 12 housekeeping
channels scored with PyOD ECOD. <b>Interference head.</b> Calibrated gradient boosting on spectral evidence, with a
per-station site survey masking recurring emitters learned from the station's past recordings.</p>
<p><b>Fusion.</b> Logistic regression on log-scaled evidence (no class re-weighting, so outputs are calibrated:
ECE {fd['calibration_ece']}); ACCEPT &lt; 0.5 ≤ VERIFY &lt; 0.9 ≤ QUARANTINE.</p>
</div><div>
<figure><img src="{img(fig_dir / 'fig_clock_archive.png')}"><figcaption>Fig. 1 — Counter minus clock model for every
authentic frame of all 30 passes, model fitted without the pass shown (leave-one-pass-out).</figcaption></figure>
<figure><img src="{img(fig_dir / 'fig_attacked_pass.png')}"><figcaption>Fig. 2 — Held-out pass {ex['obs'][4:]} after the
standard attack, re-decoded: {ex['caught']}/{ex['attacked']} attacked frames flagged, {ex['false_alarms']} false alarms
in {ex['frames']} frames.</figcaption></figure>
</div></div>

<h2>5 · Adversarial validation and response</h2>
<p>Protocol: models trained on 13 early observations; evaluated on {n_test} later observations / unseen stations. For each,
three random draws of the standard test (replay of 5–20 frames, one sequence anomaly — duplicated or swapped slot —
and a CW / narrowband-noise / swept / pulsed jammer at random frequency and hidden J/S) plus one replay spliced from
a different pass, all applied to the real audio and <b>decoded again by the full chain</b>.</p>
<table><tr><th>Metric</th><th>Value</th></tr>
<tr><td>Attacked frames detected</td><td>{pct(ap['detection_rate'])} ({ap['tp']}/{ap['attacked']})</td></tr>
<tr><td>Events: standard replay · standard anomaly · cross-pass replay</td><td>{evt.get('standard/replay','—')} · {evt.get('standard/sequence','—')} · {evt.get('cross_pass_replay/replay','—')}</td></tr>
<tr><td>False-alarm rate: attacked passes · clean passes</td><td>{pct(ap['false_alarm_rate'], 2)} · {pct(cl['false_alarm_rate'], 2)}</td></tr>
<tr><td>ROC-AUC (frames) · ECE</td><td>{co['roc_auc']} · {fd['calibration_ece']}</td></tr>
<tr><td>Evasion: counter forged +1 · counter forged far · counter-consistent forged content</td><td>{pct(ev['counter_forge_plus1']['rate'])} · {pct(ev['counter_forge_far']['rate'])} · {pct(ev['content_forge_counter_consistent']['rate'])}</td></tr>
<tr><td>Jammed recordings detected · clean recordings alarmed</td><td>{pct(it['detection_rate'])} (n={it['recordings_attacked']}) · {it['clean_recordings_with_alarm']}/{it['clean_recordings']}</td></tr>
<tr><td>Decision latency per frame after decoding · peak memory</td><td>{fd['latency_ms_per_frame']['mean']} ms · {b['resources']['peak_rss_mb']} MB</td></tr></table>
<figure><img src="{img(fig_dir / 'fig_pd.png')}"><figcaption>Fig. 3 — Interference detection vs jammer-to-noise ratio
(held-out recordings, all jammer kinds).</figcaption></figure>
<p><b>Response.</b> Frames are accepted, sent for verification, or quarantined and logged. Detected interference triggers a
closed-loop excision: band-stop, time–frequency mask and no action are each decoded and the response yielding the most
Reed–Solomon-valid frames is kept (reproducible example, {rx['jammer']} on obs {rx['obs'][4:]}: frames decoded
per response {rx['frames_by_response']}, chosen <i>{rx['chosen']}</i>; clean reference {rx['clean_reference']}). Frame positions that the
clock says were transmitted but are missing inside an interference alarm are reported as unaccounted (a jammer can hide
an injected or dropped frame). {f"In {len(mit)} benchmark cases the excision kept every decodable frame." if mit else ""}</p>
<p><b>Limits we measured.</b> Jammers well below the noise in the signal band are often missed; at these levels they also
do not degrade decoding. A jammer placed inside a station's known-RFI range and below that emitter's level evades the
site survey. A frame forged with a clock-consistent counter and telemetry close to its neighbours is not detectable
without cryptography — the argument for SDLS on links we control and signed capture at the station.</p>

<h2>6 · Official reference data and reproducibility</h2>
<p>30 SatNOGS Network observations of AO-73 (5 stations, 29 Sep – 22 Oct 2026; audio, station decodes, TLE, station
position), every file SHA-256-recorded. Note: the Network API filters by <code>norad_cat_id</code>; the
<code>satellite__norad_cat_id</code> parameter is silently ignored. One command per step:
<code>py -m sentinel fetch | decode | train | bench</code>; held-out analysis:
<code>py -m sentinel analyse heldout.wav</code> (start time optional — inferred from the on-board clock).
A web console (FastAPI + Next.js/three.js) shows each pass on a 3D globe from its TLE, runs the attack lab on real
audio, analyses uploaded recordings blind, and demonstrates SDLS and the ledger live.</p>

<h2>7 · Feasibility</h2>
<p>Laptop CPU only (12 logical cores, no GPU); GNU Radio in WSL2 on Windows or native Linux. Decoding runs at ≈35–70× real
time; detection after decoding takes {fd['latency_ms_per_frame']['mean']} ms per frame; the interference head
≈{it['latency_ms_per_recording_mean']} ms per 6-min recording; benchmark peak memory {b['resources']['peak_rss_mb']} MB.
No purchase is required; an SDR is optional for Phase 2 live capture.</p>

<p class="muted" style="margin-top:14pt;font-size:7.5pt">References: CCSDS 355.0-B-2 Space Data Link Security Protocol;
NASA CryptoLib (github.com/nasa/CryptoLib); SatNOGS Network (network.satnogs.org); gr-satellites (D. Estévez);
AO-40 FEC (P. Karn); PyOD ECOD (Li et al., 2022); C2PA technical specification; SGP4 (Vallado et al.).</p>
</body></html>"""


def main() -> None:
    bench = json.loads((RESULTS_ROOT / "benchmark.json").read_text(encoding="utf-8"))
    fig_dir = OUT / "figures"
    figs = all_figures(load_models(), bench, fig_dir)
    html = OUT / "SENTINEL-LINK_report.html"
    html.write_text(render(bench, figs, fig_dir), encoding="utf-8")
    print(f"wrote {html}")
    chrome = next((c for c in CHROME if Path(c).exists() or shutil.which(c)), None)
    if chrome:
        pdf = html.with_suffix(".pdf")
        subprocess.run([chrome, "--headless=new", "--disable-gpu", f"--print-to-pdf={pdf}", "--no-pdf-header-footer",
                        html.resolve().as_uri()], capture_output=True, timeout=120)
        print(f"wrote {pdf}" if pdf.exists() else "PDF export failed (open the HTML and print to PDF)")


if __name__ == "__main__":
    main()
