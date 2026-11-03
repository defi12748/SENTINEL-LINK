"""Render results/benchmark.json as Markdown (results/benchmark.md).
README tables are pasted from this output, never typed by hand.

    py -m sentinel.bench.report
"""

from __future__ import annotations

import json

from .. import RESULTS_ROOT


def pct(x, d=1):
    return "—" if x is None else f"{100 * x:.{d}f} %"


def ci(v, d=1):
    """' [lo–hi %]' for a stored 95 % interval, '' when absent."""
    return "" if not v else f" [{100 * v[0]:.{d}f}–{100 * v[1]:.{d}f} %]"


def render(b: dict) -> str:
    fd, it, ev, sd = b["frame_detection"], b["interference"], b["evasion"], b["sdls"]
    ap, cl, co = fd["attacked_passes"], fd["clean_passes"], fd["combined"]
    L = [
        "# Benchmark results",
        "",
        f"Generated {b['generated_utc']} on {b['environment']['platform']} (Python {b['environment']['python']}, "
        f"{b['environment']['cpu_count']} logical CPUs). Satellite: {b['dataset']['satellite']}. "
        f"{len(b['dataset']['held_out_observations'])} held-out SatNOGS observations, seeds {b['dataset']['seeds']}.",
        "",
        "## Frame-level detection (replay + sequence anomaly, decoded from attacked audio)",
        "",
        "Brackets: 95 % Wilson intervals. Seeds share observations, so treat them as optimistic.", "",
        "| Metric | Value |", "|---|---|",
        f"| Attacked frames detected (TPR) | {pct(ap['detection_rate'])} ({ap['tp']}/{ap['attacked']}){ci(ap.get('detection_rate_ci95'))} |",
        f"| False-alarm rate, attacked passes | {pct(ap['false_alarm_rate'], 2)} ({ap['fp']}/{ap['fp'] + ap['tn']}){ci(ap.get('false_alarm_rate_ci95'), 2)} |",
        f"| False-alarm rate, clean passes | {pct(cl['false_alarm_rate'], 2)} ({cl['false_alarms']}/{cl['frames']}) |",
        f"| Precision / F1 (all) | {pct(co['precision'])} / {pct(co['f1'])} |",
        f"| ROC-AUC (all frames) | {co['roc_auc']} |",
        f"| Calibration error (ECE, 10 bins) | {fd['calibration_ece']} |",
        f"| Replay frames detected | {pct(fd['per_kind_detection_rate']['replay'])} |",
        f"| Sequence-anomaly frames detected | {pct(fd['per_kind_detection_rate']['sequence'])} |",
        f"| Decision latency per frame (after decode) | {fd['latency_ms_per_frame']['mean']} ms (p95 {fd['latency_ms_per_frame']['p95']} ms) |",
        "",
        "| Event | Detected |", "|---|---|",
    ]
    for k, v in fd["events"].items():
        if v["n"]:
            L.append(f"| {k} | {v['detected']}/{v['n']} |")
    L += ["", "## Narrowband interference (hidden J/S)", "",
          f"Alarm threshold {it['threshold']:.3f} (set for 0.5 % window false alarms on clean calibration audio). "
          f"A jammer counts as detected only if an alarm overlaps it in time and lies within "
          f"{it.get('frequency_tolerance_hz', '—')} Hz of its frequency.", "",
          "| Metric | Value |", "|---|---|",
          f"| Jammed recordings detected | {pct(it['detection_rate'])} (n={it['recordings_attacked']}){ci(it.get('detection_rate_ci95'))} |",
          f"| Any alarm during the jammer (no frequency match, old criterion) | {pct(it.get('any_alarm_overlap_rate'))} |",
          f"| Clean recordings with any alarm | {it['clean_recordings_with_alarm']}/{it['clean_recordings']}{ci(it.get('clean_recordings_with_alarm_ci95'))} |",
          f"| Clean-window false-alarm rate | {pct(it['clean_window_false_alarm_rate'], 2)} |",
          f"| Median jammer frequency error | {it['freq_error_hz_median']} Hz |",
          f"| Head latency per 6-min recording | {it['latency_ms_per_recording_mean']} ms |",
          "", "| J/S (dB) | n | Pd |", "|---|---|---|"]
    L += [f"| {c['js_db']} | {c['n']} | {pct(c['pd'])} |" for c in it["pd_vs_js"]]
    L += ["", "| Jammer kind | Pd |", "|---|---|"] + [f"| {k} | {pct(v)} |" for k, v in it["pd_by_kind"].items()]
    if it["mitigation"]:
        L += ["", "Response (excision then re-decode):", "", "| Obs | Jammer | J/S | Frames jammed | After excision | Clean reference |",
              "|---|---|---|---|---|---|"]
        L += [f"| {m['obs']} | {m['kind']} | {m['js_db']} | {m['frames_jammed']} | {m['frames_after_excision']} | "
              f"{m['frames_clean_reference']} |" for m in it["mitigation"]]
    L += ["", "## Evasion (frame level, informed attacker)", "", "| Attack | Detected |", "|---|---|"]
    L += [f"| {k} | {v['detected']}/{v['n']} ({pct(v['rate'])}) |" for k, v in ev.items()]
    L += ["", "## Trust anchor (SDLS emulation on real AO-73 frames)", "",
          "| Service | Overhead | Apply | Verify | Replay rejected | Bit-flip rejected |", "|---|---|---|---|---|---|"]
    L += [f"| {k} | {v['overhead_bytes']} B ({v['overhead_pct_of_256B_frame']} %) | {v['apply_us_per_frame']} µs | "
          f"{v['verify_us_per_frame']} µs | {pct(v['replay_rejection_rate'])} | {pct(v['bitflip_rejection_rate'])} |"
          for k, v in sd.items()]
    mf = b["manifest"]
    L += ["", "## Signed capture manifest", "",
          f"Clean recordings authentic: {mf['all_clean_authentic']} · attacked recordings rejected: {mf['all_attacks_detected']}", "",
          "| Obs | Flagged seconds | Replay interval (s) | Sign | Verify | Size |", "|---|---|---|---|---|---|"]
    L += [f"| {c['obs']} | {c['tampered_seconds_flagged']} | {c['replay_interval_s']} | {c['sign_s']} s | {c['verify_s']} s | "
          f"{c['manifest_kb']} kB |" for c in mf["cases"]]
    L += ["", f"Peak RSS {b['resources']['peak_rss_mb']} MB · benchmark wall clock {b['resources']['wall_clock_s']} s.", ""]
    return "\n".join(L)


def render_twin(t: dict) -> str:
    c, ev = t["clean"], t["evasion"]
    L = ["## Duplicate-audio head (audio only, any satellite)", "",
         f"Generated {t['generated_utc']}. Fixed threshold {t['threshold']} (normalised correlation of "
         f"{t['block_s']:g} s blocks at {t['baseband_hz']:g} Hz complex baseband), not fitted. "
         "Same held-out draws as above (seeds " + ", ".join(map(str, t["seeds"])) + ").", "",
         "| Metric | Value |", "|---|---|",
         f"| In-pass replay detected | {t['replay']['detected']}/{t['replay']['n']}{ci(t['replay']['ci95'])} |",
         f"| Duplicated-slot anomaly detected | {t['sequence_duplicate']['detected']}/{t['sequence_duplicate']['n']}"
         f"{ci(t['sequence_duplicate']['ci95'])} |",
         f"| Swapped-slot anomaly (copies nothing, not expected) | {t['sequence_swap']['detected']}/{t['sequence_swap']['n']} |",
         f"| Clean recordings with a match (all {c['recordings']}) | {c['with_match']}/{c['recordings']}{ci(c['with_match_ci95'])} |",
         f"| False matches on attacked recordings | {t['attacked_false_matches']} |",
         f"| Highest correlation on clean audio (held-out · all) | {c['held_out_max_ncc']} · {c['max_ncc']} |",
         f"| Latency per recording | {t['latency_ms_per_recording_mean']} ms |",
         "", "| Evasion of the replay | Detected |", "|---|---|"]
    L += [f"| {k} | {v['detected']}/{v['n']} ({pct(v['rate'])}) |" for k, v in ev.items()]
    return "\n".join(L + [""])


def render_persistence(r: dict) -> str:
    sel = (r["selected"]["min_windows"], r["selected"]["freq_tol_hz"])
    L = ["## Interference persistence rule", "",
         f"Selected on the {len(r['calibration_observations'])} calibration recordings only "
         f"({r['criterion']}): min_windows={sel[0]}, frequency stability "
         f"{'off' if sel[1] is None else f'±{sel[1]:g} Hz'}. Held-out results for every rule:", "",
         "| Rule | Clean recordings alarmed | Alarm episodes / h | Jammers detected |", "|---|---|---|---|"]
    for h in r["held_out"]:
        name = f"{h['min_windows']} window(s)" + ("" if h["freq_tol_hz"] is None else f", ±{h['freq_tol_hz']:g} Hz")
        mark = " **(selected)**" if (h["min_windows"], h["freq_tol_hz"]) == sel else ""
        L.append(f"| {name}{mark} | {h['clean_recordings_with_alarm']}/{h['clean_recordings']} | "
                 f"{h['clean_alarm_episodes_per_hour']} | {h['jammed_detected']}/{h['jammed']}{ci(h['detection_rate_ci95'])} |")
    return "\n".join(L + [""])


def readme_table(b: dict, tw: dict | None = None) -> str:
    fd, it, ev, sd = b["frame_detection"], b["interference"], b["evasion"], b["sdls"]
    ap, cl, co = fd["attacked_passes"], fd["clean_passes"], fd["combined"]
    ev_rate = {k: f"{v['detected']}/{v['n']}" for k, v in fd["events"].items() if v["n"]}
    rows = [
        ("Replay + sequence-anomaly frames detected",
         f"{pct(ap['detection_rate'])} ({ap['tp']}/{ap['attacked']}){ci(ap.get('detection_rate_ci95'))}"),
        ("Events detected (standard replay · standard anomaly · cross-pass replay)",
         " · ".join(ev_rate.get(k, "—") for k in ("standard/replay", "standard/sequence", "cross_pass_replay/replay"))),
        ("Frame false-alarm rate (attacked + clean passes)", pct(co["false_alarm_rate"], 2) + ci(co.get("false_alarm_rate_ci95"), 2)),
        ("Frame ROC-AUC · calibration error (ECE)", f"{co['roc_auc']} · {fd['calibration_ece']}"),
        ("Evasion: counter-consistent forged frame detected", pct(ev["content_forge_counter_consistent"]["rate"])),
    ]
    if tw:
        rows.append(("Duplicate-audio head, no decoder: in-pass replays · duplicated slots · clean files matched",
                     f"{tw['replay']['detected']}/{tw['replay']['n']} · {tw['sequence_duplicate']['detected']}/"
                     f"{tw['sequence_duplicate']['n']} · {tw['clean']['with_match']}/{tw['clean']['recordings']}"))
    rows += [
        ("Jammed recordings detected, alarm at the jammer frequency (hidden J/S −30…+10 dB)",
         f"{pct(it['detection_rate'])} (n={it['recordings_attacked']}){ci(it.get('detection_rate_ci95'))}"),
        ("Clean recordings with an interference alarm", f"{it['clean_recordings_with_alarm']}/{it['clean_recordings']}"),
        ("SDLS replay / bit-flip rejection", f"{pct(sd['AUTH']['replay_rejection_rate'])} / {pct(sd['AUTH']['bitflip_rejection_rate'])}"),
        ("SDLS overhead per 256 B frame", f"{sd['AUTH']['overhead_bytes']} B, {sd['AUTH']['verify_us_per_frame']} µs verify"),
        ("Decision latency per frame (after decode)", f"{fd['latency_ms_per_frame']['mean']} ms"),
        ("Peak memory (benchmark process)", f"{b['resources']['peak_rss_mb']} MB"),
    ]
    head = (f"Held-out SatNOGS observations: {len(b['dataset']['held_out_observations'])} · "
            f"generated {b['generated_utc']}\n\n| Metric | Value |\n|---|---|\n")
    return head + "\n".join(f"| {k} | {v} |" for k, v in rows)


def main() -> None:
    src = RESULTS_ROOT / "benchmark.json"
    if not src.exists():
        src = RESULTS_ROOT / "benchmark_quick.json"
    b = json.loads(src.read_text(encoding="utf-8"))
    out = src.with_suffix(".md")
    md = render(b)
    for name, fn in (("twin_benchmark.json", render_twin), ("interference_persistence.json", render_persistence)):
        extra = RESULTS_ROOT / name
        if extra.exists():
            md += "\n" + fn(json.loads(extra.read_text(encoding="utf-8")))
    out.write_text(md, encoding="utf-8")
    print(f"wrote {out}")
    readme = RESULTS_ROOT.parent.parent / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        start, end = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
        if start in text and end in text:
            pre, rest = text.split(start, 1)
            _, post = rest.split(end, 1)
            tw_path = RESULTS_ROOT / "twin_benchmark.json"
            tw = json.loads(tw_path.read_text(encoding="utf-8")) if tw_path.exists() else None
            readme.write_text(f"{pre}{start}\n{readme_table(b, tw)}\n{end}{post}", encoding="utf-8")
            print(f"updated {readme}")


if __name__ == "__main__":
    main()
