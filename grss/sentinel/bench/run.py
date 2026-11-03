"""Benchmark on held-out observations. Every number in the README/report
comes from ``results/benchmark.json`` written here.

    py -m sentinel.bench.run [--seeds 3] [--quick]
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from datetime import datetime, timezone

import numpy as np
import psutil
from sklearn.metrics import roc_auc_score

from .. import RESULTS_ROOT
from ..data.corpus import iso_to_unix, load_pass
from ..decode import grsat
from ..dsp.audio import load_audio
from ..dsp.mitigate import estimate_width, excise
from ..pipeline import analyse_pass
from ..redteam import attacks, scenario
from ..train import load_models
from ..trust.manifest import StationKey, create_manifest, verify_manifest
from ..trust.sdls import KeyStore, SdlsEndpoint, SecurityAssociation, Service, Verdict


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def wilson(num: int, den: int, z: float = 1.96) -> list[float] | None:
    """95 % Wilson score interval for a proportion."""
    if not den:
        return None
    p = num / den
    centre = (p + z * z / (2 * den)) / (1 + z * z / den)
    half = z * np.sqrt(p * (1 - p) / den + z * z / (4 * den * den)) / (1 + z * z / den)
    return [round(max(0.0, float(centre - half)), 4), round(min(1.0, float(centre + half)), 4)]


# An interference alarm counts as a detection only if it overlaps the jammer in
# time *and* points at it in frequency; an unrelated alarm elsewhere in the
# band during the jammer interval is a false alarm, not a detection.
FREQ_TOL_HZ = 100.0


def freq_tolerance(kind: str, bw_hz: float | None) -> float:
    spread = (bw_hz or 0.0) / 2 if kind in ("nbnoise", "chirp") else 0.0
    return FREQ_TOL_HZ + spread


def interference_summary(rows: list[dict]) -> dict:
    """Detection metrics from per-recording rows (``detected`` = time and
    frequency match, ``any_overlap`` = any alarm during the jammer)."""
    bins = [(-40, -25), (-25, -20), (-20, -15), (-15, -10), (-10, -5), (-5, 0), (0, 10)]
    curve = []
    for lo, hi in bins:
        sel = [r for r in rows if lo <= r["js_db"] < hi]
        curve.append({"js_db": f"[{lo},{hi})", "n": len(sel), "pd": _rate(sum(r["detected"] for r in sel), len(sel))})
    by_kind = {k: _rate(sum(r["detected"] for r in rows if r["kind"] == k), sum(r["kind"] == k for r in rows))
               for k in ("cw", "nbnoise", "chirp", "pulsed")}
    hits = sum(r["detected"] for r in rows)
    overlap = sum(r.get("any_overlap", r["detected"]) for r in rows)
    errs = [r["freq_error_hz"] for r in rows if r["detected"] and r["freq_error_hz"] is not None]
    return {
        "recordings_attacked": len(rows),
        "detection_rate": _rate(hits, len(rows)), "detection_rate_ci95": wilson(hits, len(rows)),
        "any_alarm_overlap_rate": _rate(overlap, len(rows)),
        "pd_vs_js": curve, "pd_by_kind": by_kind,
        "freq_error_hz_median": round(float(np.median(errs)), 1) if errs else None,
    }


def frame_metrics(y: np.ndarray, p: np.ndarray, flag: np.ndarray) -> dict:
    tp = int((flag & y).sum()); fp = int((flag & ~y).sum())
    fn = int((~flag & y).sum()); tn = int((~flag & ~y).sum())
    prec = _rate(tp, tp + fp)
    rec = _rate(tp, tp + fn)
    f1 = round(2 * prec * rec / (prec + rec), 4) if prec and rec else None
    auc = round(float(roc_auc_score(y, p)), 4) if 0 < y.sum() < len(y) else None
    return {"frames": int(len(y)), "attacked": int(y.sum()), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "detection_rate": rec, "detection_rate_ci95": wilson(tp, tp + fn),
            "false_alarm_rate": _rate(fp, fp + tn), "false_alarm_rate_ci95": wilson(fp, fp + tn),
            "precision": prec, "f1": f1, "roc_auc": auc}


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    err = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi) if hi < 1 else (p >= lo) & (p <= hi)
        if m.any():
            err += m.mean() * abs(p[m].mean() - y[m].mean())
    return round(float(err), 4)


def bench_frames(models, test_dirs, seeds) -> dict:
    Y, P, F, kinds, lat, events = [], [], [], [], [], []
    clean_Y, clean_P, clean_F = [], [], []
    for k, d in enumerate(test_dirs):
        clean = load_pass(d)
        t0 = time.perf_counter()
        rep = analyse_pass(models, clean)
        lat.append((time.perf_counter() - t0) * 1e3 / max(1, len(rep)))
        clean_Y.append(np.zeros(len(rep), bool))
        clean_P.append(np.array([r.probability for r in rep]))
        clean_F.append(np.array([r.decision != "ACCEPT" for r in rep], dtype=bool))
        runs = [("standard", s, None) for s in seeds]
        runs.append(("cross_pass_replay", 100 + seeds[0], test_dirs[(k + 5) % len(test_dirs)]))
        for variant, seed, donor in runs:
            ap = scenario.build(d, seed, variant, donor_dir=donor)
            rep = analyse_pass(models, ap.pass_)
            p = np.array([r.probability for r in rep])
            flag = np.array([r.decision != "ACCEPT" for r in rep], dtype=bool)
            Y.append(ap.labels); P.append(p); F.append(flag); kinds += ap.label_kind
            for kind in ("replay", "sequence"):
                m = np.array([kk == kind for kk in ap.label_kind], dtype=bool)
                if kind in ap.truth or (kind == "replay" and "replay" in ap.truth):
                    events.append({"variant": variant, "kind": kind, "frames": int(m.sum()),
                                   "detected": bool((flag & m).any()), "observation": ap.truth["observation_id"]})
        print(f"  frames: {d.name} done")
    y, p, f = np.concatenate(Y), np.concatenate(P), np.concatenate(F)
    cy, cp, cf = np.concatenate(clean_Y), np.concatenate(clean_P), np.concatenate(clean_F)
    kinds = np.array(kinds)
    out = {
        "attacked_passes": frame_metrics(y, p, f),
        "clean_passes": {"frames": int(len(cy)), "false_alarms": int(cf.sum()),
                         "false_alarm_rate": _rate(int(cf.sum()), len(cy))},
        "combined": frame_metrics(np.concatenate([y, cy]), np.concatenate([p, cp]), np.concatenate([f, cf])),
        "per_kind_detection_rate": {k: _rate(int((f & (kinds == k)).sum()), int((kinds == k).sum()))
                                    for k in ("replay", "sequence")},
        "events": {
            f"{v}/{k}": {"n": sum(1 for e in events if e["variant"] == v and e["kind"] == k and e["frames"] > 0),
                         "detected": sum(1 for e in events if e["variant"] == v and e["kind"] == k
                                         and e["frames"] > 0 and e["detected"])}
            for v in ("standard", "cross_pass_replay") for k in ("replay", "sequence")},
        "calibration_ece": ece(np.concatenate([y, cy]).astype(float), np.concatenate([p, cp])),
        "latency_ms_per_frame": {"mean": round(float(np.mean(lat)), 3), "p95": round(float(np.percentile(lat, 95)), 3)},
    }
    return out


def bench_interference(models, test_dirs, seeds, mitigation_cases: int = 8) -> dict:
    rows, clean_windows, clean_alarm_recordings = [], 0, 0
    clean_false_windows = 0
    mitig = []
    for d in test_dirs:
        x, fs = load_audio(d / "audio.ogg")
        fc = json.loads((d / "decoded.json").read_text())["f_offset_hz"]
        station = json.loads((d / "record.json").read_text())["station_name"]
        r = models.interference.detect(x, fs, fc, station=station)
        clean_windows += len(r.prob)
        clean_false_windows += int((r.prob >= models.interference.threshold).sum())
        clean_alarm_recordings += int(bool(r.alarms))
        for seed in seeds:
            ap = scenario.build(d, seed, "standard", keep_audio=True)
            ti = ap.truth.get("interference")
            if not ti:
                continue
            t0 = time.perf_counter()
            res = models.interference.detect(ap.audio, fs, fc, station=station)
            ms = (time.perf_counter() - t0) * 1e3
            s, e = ti["start_s"], ti["start_s"] + ti["dur_s"]
            overlap = [a for a in res.alarms if a.end_s > s and a.start_s < e]
            tol = freq_tolerance(ti["kind"], ti.get("bw_hz"))
            hit = [a for a in overlap if abs(a.freq_hz - ti["freq_hz"]) <= tol]
            freq_err = min((abs(a.freq_hz - ti["freq_hz"]) for a in overlap), default=None)
            rows.append({"kind": ti["kind"], "js_db": round(ti["js_db"], 2), "jn_db": round(ti["jn_db"], 2),
                         "bw_hz": round(ti["bw_hz"], 1), "detected": bool(hit), "any_overlap": bool(overlap),
                         "freq_error_hz": freq_err, "ms": round(ms, 1), "obs": ap.truth["observation_id"]})
            if hit and len(mitig) < mitigation_cases and ti["js_db"] > -5:
                start = iso_to_unix(json.loads((d / "record.json").read_text())["start"])
                before = len(ap.pass_.payloads)
                y = ap.audio
                for a in hit:
                    y = excise(y, fs, a.freq_hz, estimate_width(y, fs, a.freq_hz, a.start_s, a.end_s),
                               a.start_s, a.end_s)
                after = len(grsat.decode_audio(y, fs, start, f_offset=fc).frames)
                mitig.append({"obs": ap.truth["observation_id"], "kind": ti["kind"], "js_db": round(ti["js_db"], 1),
                              "frames_jammed": before, "frames_after_excision": after,
                              "frames_clean_reference": len(load_pass(d).payloads)})
        print(f"  interference: {d.name} done")
    return {
        "threshold": models.interference.threshold,
        "frequency_tolerance_hz": f"{FREQ_TOL_HZ:g} (+ half the bandwidth for nbnoise/chirp)",
        **interference_summary(rows),
        "clean_recordings": len(test_dirs), "clean_recordings_with_alarm": clean_alarm_recordings,
        "clean_recordings_with_alarm_ci95": wilson(clean_alarm_recordings, len(test_dirs)),
        "clean_window_false_alarm_rate": _rate(clean_false_windows, clean_windows),
        "latency_ms_per_recording_mean": round(float(np.mean([r["ms"] for r in rows])), 1) if rows else None,
        "mitigation": mitig, "cases": rows,
    }


def bench_evasion(models, test_dirs, seed: int = 7) -> dict:
    """Frame-level evasions an informed attacker would try."""
    rng = np.random.default_rng(seed)
    res = {"counter_forge_plus1": [0, 0], "counter_forge_far": [0, 0], "content_forge_counter_consistent": [0, 0]}
    clean = [load_pass(d) for d in test_dirs]
    for k, p in enumerate(clean):
        n = len(p.payloads)
        if n < 6:
            continue
        idx = int(rng.integers(2, n - 2))
        cases = {
            "counter_forge_plus1": scenario.attacks.frames_counter_forge(p.payloads, idx, 1),
            "counter_forge_far": scenario.attacks.frames_counter_forge(p.payloads, idx, int(rng.integers(30, 500))),
            "content_forge_counter_consistent": scenario.attacks.frames_content_forge(
                p.payloads, idx, clean[(k + 3) % len(clean)].payloads[0]),
        }
        for name, (payloads, lab) in cases.items():
            q = type(p)(**{**p.__dict__, "payloads": payloads})
            rep = analyse_pass(models, q)
            res[name][0] += int(rep[idx].decision != "ACCEPT")
            res[name][1] += 1
    return {k: {"detected": v[0], "n": v[1], "rate": _rate(*v)} for k, v in res.items()}


def bench_sdls(test_dirs, reps: int = 3) -> dict:
    frames = [pl for d in test_dirs for pl in load_pass(d).payloads]
    out = {}
    for service in (Service.AUTH, Service.AUTH_ENC):
        ks = KeyStore(b"\x01" * 32)
        tx = SecurityAssociation(spi=0x73, key=ks.derive(0x73), service=service)
        rx = SdlsEndpoint(ks); rx.add_sa(0x73, service=service, window=64)
        t0 = time.perf_counter()
        prot = [tx.apply(f) for f in frames * reps]
        t_apply = (time.perf_counter() - t0) / len(prot) * 1e6
        t0 = time.perf_counter()
        verdicts = [rx.process(f)[0] for f in prot]
        t_proc = (time.perf_counter() - t0) / len(prot) * 1e6
        accepted = sum(v is Verdict.ACCEPT for v in verdicts)
        rng = np.random.default_rng(0)
        replays = [prot[i] for i in rng.integers(0, len(prot), 500)]
        rejected = sum(rx.process(f)[0] is not Verdict.ACCEPT for f in replays)
        forged = 0
        for f in replays[:200]:
            b = bytearray(f); b[len(b) // 2] ^= 0x40
            forged += rx.process(bytes(b))[0] is Verdict.REJECT_MAC
        out[service.value] = {
            "frames": len(prot), "accepted_fresh": accepted, "overhead_bytes": tx.overhead_bytes,
            "overhead_pct_of_256B_frame": round(100 * tx.overhead_bytes / 256, 2),
            "apply_us_per_frame": round(t_apply, 2), "verify_us_per_frame": round(t_proc, 2),
            "replay_rejection_rate": _rate(rejected, len(replays)),
            "bitflip_rejection_rate": _rate(forged, 200),
        }
    return out


def bench_manifest(test_dirs, seeds) -> dict:
    key = StationKey.generate()
    rows = []
    for d in test_dirs[:6]:
        x, fs = load_audio(d / "audio.ogg")
        t0 = time.perf_counter()
        m = create_manifest(x, fs, {"observation_id": d.name}, key)
        t_sign = time.perf_counter() - t0
        t0 = time.perf_counter()
        ok = verify_manifest(m, x, fs, key.public_b64()).authentic
        t_ver = time.perf_counter() - t0
        ap = scenario.build(d, seeds[0], "standard", keep_audio=True)
        chk = verify_manifest(m, ap.audio, fs, key.public_b64())
        rep = ap.truth.get("replay", {})
        tampered_s = len(chk.tampered_chunks)
        rows.append({"obs": d.name, "clean_authentic": ok, "attacked_authentic": chk.authentic,
                     "tampered_seconds_flagged": tampered_s,
                     "replay_interval_s": [round(rep.get("dst_start_s", 0), 1), round(rep.get("dst_end_s", 0), 1)],
                     "sign_s": round(t_sign, 3), "verify_s": round(t_ver, 3),
                     "manifest_kb": round(len(json.dumps(m)) / 1024, 1)})
    return {"cases": rows,
            "all_clean_authentic": all(r["clean_authentic"] for r in rows),
            "all_attacks_detected": not any(r["attacked_authentic"] for r in rows)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--quick", action="store_true", help="first 5 held-out observations only")
    args = ap.parse_args()
    seeds = list(range(1000, 1000 + args.seeds))
    models = load_models()
    _, test_dirs = scenario.split()
    if args.quick:
        test_dirs = test_dirs[:5]
    proc = psutil.Process()
    t0 = time.time()
    results = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "cpu_count": psutil.cpu_count()},
        "dataset": {"satellite": "AO-73 / FUNcube-1 (NORAD 39444)", "source": "SatNOGS Network",
                    "held_out_observations": [d.name for d in test_dirs], "seeds": seeds},
    }
    print("SDLS ..."); results["sdls"] = bench_sdls(test_dirs)
    print("frames ..."); results["frame_detection"] = bench_frames(models, test_dirs, seeds)
    print("interference ..."); results["interference"] = bench_interference(models, test_dirs, seeds)
    print("evasion ..."); results["evasion"] = bench_evasion(models, test_dirs)
    print("manifest ..."); results["manifest"] = bench_manifest(test_dirs, seeds)
    results["resources"] = {"peak_rss_mb": round(proc.memory_info().rss / 2 ** 20, 1),
                            "wall_clock_s": round(time.time() - t0, 1)}
    RESULTS_ROOT.mkdir(exist_ok=True)
    out = RESULTS_ROOT / ("benchmark_quick.json" if args.quick else "benchmark.json")
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
