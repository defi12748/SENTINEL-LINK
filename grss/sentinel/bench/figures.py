"""Report figures, all computed from real data and the benchmark output."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..data.corpus import corpus_root, load_corpus  # noqa: E402
from ..detect.clock import ClockModel  # noqa: E402
from ..pipeline import analyse_pass  # noqa: E402
from ..redteam import scenario  # noqa: E402

INK, MUTED, GRID = "#17171b", "#58585b", "#d1d1d1"
BLUE, AMBER, RED = "#1c67e3", "#e0a100", "#f64137"
DEC_COLOR = {"ACCEPT": BLUE, "VERIFY": AMBER, "QUARANTINE": RED}
DEC_MARK = {"ACCEPT": "o", "VERIFY": "D", "QUARANTINE": "s"}


def _style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def fig_clock_archive(out: Path) -> None:
    """Counter-minus-clock residual of every authentic frame, all passes."""
    passes = load_corpus()
    data = []
    for p in passes:
        parsed = p.parsed()
        idx = [i for i, f in enumerate(parsed) if f]
        data.append((p.t_utc[idx], np.array([parsed[i].position for i in idx])))
    fig, ax = plt.subplots(figsize=(6.4, 2.6), dpi=200)
    for k, (t, P) in enumerate(data):  # leave-one-pass-out residuals
        m = ClockModel.fit([d for j, d in enumerate(data) if j != k])
        r = m.residuals(t, P)
        ax.scatter((t - t.min()) / 60, r - np.median(r), s=4, color=BLUE, alpha=0.5, linewidths=0)
    ax.axhspan(-1, 1, color=GRID, alpha=0.35, zorder=0)
    ax.set_ylim(-2, 2)
    ax.set_xlabel("minutes into pass", fontsize=8, color=MUTED)
    ax.set_ylabel("counter − clock (frames)", fontsize=8, color=MUTED)
    _style(ax)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def fig_attacked_pass(models, out: Path, obs: str = "obs_15123656", seed: int = 1000) -> dict:
    ap = scenario.build(corpus_root() / obs, seed, "standard")
    rep = analyse_pass(models, ap.pass_)
    fig, ax = plt.subplots(figsize=(6.4, 2.8), dpi=200)
    pts = [(r.t_rec, r.position, r.decision) for r in rep if r.position is not None]
    p0 = models.clock.predict(np.array([ap.pass_.start_utc]))[0]
    t_end = max(t for t, _, _ in pts) + 5
    ax.plot([0, t_end], [0, models.clock.b * t_end], "--", color=INK, linewidth=1, label="clock model")
    for kind, color, key in (("replay", RED, "replay"), ("sequence anomaly", AMBER, "sequence")):
        tr = ap.truth.get(key)
        if tr:
            ax.axvspan(tr["dst_start_s"], tr["dst_end_s"], color=color, alpha=0.12, linewidth=0)
            ax.text(tr["dst_start_s"] + 2, 2, kind, fontsize=7, color=color)
    offset = np.median([pos - p0 - models.clock.b * t for t, pos, _ in pts])
    for dec in ("ACCEPT", "VERIFY", "QUARANTINE"):
        sel = [(t, pos - p0 - offset) for t, pos, d in pts if d == dec]
        if sel:
            ax.scatter(*zip(*sel), s=14, marker=DEC_MARK[dec], color=DEC_COLOR[dec], label=dec.lower(), zorder=3,
                       edgecolors="white", linewidths=0.4)
    ax.set_xlabel("seconds into recording", fontsize=8, color=MUTED)
    ax.set_ylabel("frame counter (relative)", fontsize=8, color=MUTED)
    ax.legend(fontsize=7, frameon=False, loc="upper left")
    _style(ax)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    lab = ap.labels
    flag = np.array([r.decision != "ACCEPT" for r in rep])
    return {"obs": obs, "seed": seed, "attacked": int(lab.sum()), "caught": int((flag & lab).sum()),
            "false_alarms": int((flag & ~lab).sum()), "frames": len(rep), "truth": ap.truth}


def fig_pd(bench: dict, out: Path) -> None:
    cases = bench["interference"]["cases"]
    bins = [(-40, -20), (-20, -10), (-10, 0), (0, 10), (10, 40)]
    fig, ax = plt.subplots(figsize=(6.4, 2.4), dpi=200)
    labels, vals, ns = [], [], []
    for lo, hi in bins:
        s = [c for c in cases if lo <= c["jn_db"] < hi]
        labels.append(f"[{lo},{hi})")
        vals.append(np.mean([c["detected"] for c in s]) if s else 0)
        ns.append(len(s))
    bars = ax.bar(labels, vals, color=BLUE, width=0.6)
    for b, v, n in zip(bars, vals, ns):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.03, f"{v:.0%}\nn={n}", ha="center", fontsize=7, color=INK)
    ax.set_ylim(0, 1.25)
    ax.set_yticks([0, 0.5, 1])
    ax.set_yticklabels(["0%", "50%", "100%"])
    ax.set_xlabel("jammer-to-noise ratio in the 2.4 kHz signal band (dB)", fontsize=8, color=MUTED)
    ax.set_ylabel("detection probability", fontsize=8, color=MUTED)
    _style(ax)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def fig_spectrum(out: Path, obs: str = "obs_15123656") -> None:
    from scipy.signal import stft

    from ..dsp.audio import load_audio
    d = corpus_root() / obs
    x, fs = load_audio(d / "audio.ogg")
    fc = json.loads((d / "decoded.json").read_text())["f_offset_hz"]
    f, t, Z = stft(x, fs=fs, nperseg=2048, noverlap=0)
    sel = np.abs(f - fc) < 2500
    db = 10 * np.log10(np.abs(Z[sel]) ** 2 + 1e-20)
    fig, ax = plt.subplots(figsize=(6.4, 2.2), dpi=200)
    ax.imshow(db, aspect="auto", origin="lower", cmap="Blues_r",
              extent=[t[0], t[-1], f[sel][0] / 1e3, f[sel][-1] / 1e3],
              vmin=np.percentile(db, 5), vmax=np.percentile(db, 99.7))
    ax.set_xlabel("seconds", fontsize=8, color=MUTED)
    ax.set_ylabel("audio kHz", fontsize=8, color=MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def response_example(models, obs: str = "obs_15254375", seed: int = 1) -> dict:
    """Closed-loop excision on a fixed, reproducible strong swept jammer."""
    from ..data.corpus import iso_to_unix
    from ..pipeline import analyse_recording
    d = corpus_root() / obs
    fc = json.loads((d / "decoded.json").read_text())["f_offset_hz"]
    ov = {"replay": False, "sequence": False, "jam_kind": "chirp", "js_db": 6.0, "jam_freq_hz": fc - 900.0}
    ap = scenario.build(d, seed, "standard", keep_audio=True, overrides=ov)
    rec = json.loads((d / "record.json").read_text())
    rr = analyse_recording(models, ap.audio, ap.fs, iso_to_unix(rec["start"]), {"station": rec["station_name"]})
    return {"obs": obs, "jammer": "swept tone, J/S +6 dB, 900 Hz below the carrier",
            "frames_by_response": rr.response_frames, "chosen": rr.response,
            "clean_reference": len(json.loads((d / "decoded.json").read_text())["frames"])}


def all_figures(models, bench: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_clock_archive(out_dir / "fig_clock_archive.png")
    example = fig_attacked_pass(models, out_dir / "fig_attacked_pass.png")
    fig_pd(bench, out_dir / "fig_pd.png")
    fig_spectrum(out_dir / "fig_spectrum.png")
    return {"example": example, "response": response_example(models)}

