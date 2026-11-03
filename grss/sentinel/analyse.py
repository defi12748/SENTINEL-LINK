"""Analyse a held-out recording or an organizer-supplied frame file.

    py -m sentinel analyse recording.ogg [--start 2026-10-22T06:29:05Z] [--obs observation.json]
    py -m sentinel analyse frames.kss                 # gr-satellites KISS (with timestamps)
    py -m sentinel analyse frames.txt                 # lines: "<ISO-8601 UTC> <hex frame>"
    options: --manifest m.json --pubkey <b64>  verify a signed capture manifest
             --out report.json                 full machine-readable report
             --no-mitigate                     do not excise detected interferers

If the absolute start time is unknown, it is inferred from the on-board
clock; in-pass replay/injection checks are unaffected, but the cross-pass
(clock offset) check is then reported as unavailable.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .data.corpus import Pass, iso_to_unix
from .decode import funcube
from .decode.kiss import read_kiss
from .ledger_store import ledger_for_run
from .pipeline import analyse_pass, analyse_recording, flag_duplicates
from .train import load_models
from .trust.manifest import verify_manifest

AUDIO_EXT = {".ogg", ".wav", ".flac"}


def _infer_start(models, t_rec: np.ndarray, payloads: list[bytes]) -> float | None:
    """Start time that puts the pass on the archive clock line (median)."""
    est = []
    for t, p in zip(t_rec, payloads):
        f = funcube.parse(p)
        if f:
            est.append((f.position - models.clock.a) / models.clock.b + 1.79e9 - t)
    return float(np.median(est)) if est else None


def _read_frames(path: Path) -> tuple[np.ndarray, list[bytes]]:
    if path.suffix.lower() in {".kss", ".kiss"}:
        ks = read_kiss(path.read_bytes())
        t = np.array([k.timestamp_ms / 1000 if k.timestamp_ms else np.nan for k in ks])
        return t, [k.payload for k in ks]
    t, payloads = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            t.append(iso_to_unix(parts[0]))
            payloads.append(bytes.fromhex(parts[-1]))
    return np.array(t), payloads


def _summary(frames, intf=None) -> dict:
    dec = [f.decision for f in frames]
    out = {"frames": len(frames), "accept": dec.count("ACCEPT"), "verify": dec.count("VERIFY"),
           "quarantine": dec.count("QUARANTINE")}
    if intf is not None:
        out["interference_alarms"] = [{k: round(v, 2) for k, v in a.__dict__.items()} for a in intf.alarms]
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="sentinel analyse")
    ap.add_argument("input")
    ap.add_argument("--start", help="recording start, ISO-8601 UTC")
    ap.add_argument("--obs", help="SatNOGS observation JSON (start time, station, TLE)")
    ap.add_argument("--manifest")
    ap.add_argument("--pubkey")
    ap.add_argument("--out")
    ap.add_argument("--no-mitigate", action="store_true")
    a = ap.parse_args(argv)

    models = load_models()
    path = Path(a.input)
    meta: dict = {}
    if a.obs:
        o = json.loads(Path(a.obs).read_text(encoding="utf-8"))
        meta = {"observation_id": o.get("id") or o.get("observation_id", 0),
                "station": o.get("station_name", ""), "tle": (o.get("tle1", ""), o.get("tle2", "")),
                "station_lla": (o.get("station_lat", 0), o.get("station_lng", 0), o.get("station_alt", 0))}
        a.start = a.start or o.get("start")
    start = iso_to_unix(a.start) if a.start else None
    report: dict = {"input": path.name, "analysed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    t0 = time.perf_counter()

    if path.suffix.lower() in AUDIO_EXT:
        from .dsp.audio import load_audio
        x, fs = load_audio(path)
        if a.manifest:
            chk = verify_manifest(json.loads(Path(a.manifest).read_text(encoding="utf-8")), x, fs, a.pubkey)
            report["manifest"] = {"authentic": chk.authentic, "signature_valid": chk.signature_valid,
                                  "tampered_intervals_s": chk.tampered_intervals(1.0)}
        rr = analyse_recording(models, x, fs, start or 0.0, meta, mitigate=not a.no_mitigate)
        p, frames = rr.pass_, rr.frames
        if start is None:
            inferred = _infer_start(models, p.t_rec, p.payloads)
            if inferred is not None:
                p.start_utc = inferred
                frames = flag_duplicates(analyse_pass(models, p), rr.duplicates)
                for f in frames:
                    f.evidence["pass_offset_sigma"] = float("nan")
        report["interference"] = _summary(frames, rr.interference)["interference_alarms"]
        report["missing_frames"] = rr.missing
        report["audio_duplicates"] = [{k: round(v, 3) if isinstance(v, float) else v for k, v in m.__dict__.items()}
                                      for m in rr.duplicates.matches]
        report["response"] = {"chosen": rr.response, "frames_decoded": rr.response_frames}
        report["carrier_hz"] = round(rr.f_offset_hz, 1)
        report["timings_ms"] = {k: round(v, 1) for k, v in rr.timings_ms.items()}
        report["peak_mem_mb"] = round(rr.peak_mem_mb, 1)
    else:
        t_abs, payloads = _read_frames(path)
        if np.isnan(t_abs).all():
            raise SystemExit("frame file has no timestamps")
        s = start if start is not None else float(np.nanmin(t_abs))
        p = Pass(observation_id=meta.get("observation_id", 0), station=meta.get("station", ""), start_utc=s,
                 t_rec=t_abs - s, payloads=payloads, track_t=np.zeros(0), carrier_hz=np.zeros(0),
                 level_db=np.zeros(0), tle=("", ""), station_lla=(0.0, 0.0, 0.0))
        frames = analyse_pass(models, p)

    report["absolute_time"] = "given" if start is not None else "inferred from on-board clock (cross-pass check unavailable)"
    report["summary"] = _summary(frames)
    report["frames"] = [{"index": f.index, "t_rec": round(f.t_rec, 2), "type": f.frame_type, "sequence": f.sequence,
                         "p_not_authentic": round(f.probability, 4), "decision": f.decision, "sha256": f.sha256,
                         "evidence": {k: (None if v != v else round(v, 3)) for k, v in f.evidence.items()}}
                        for f in frames]
    report["wall_clock_s"] = round(time.perf_counter() - t0, 2)
    report["ledger"] = ledger_for_run(path.name, frames)

    s = report["summary"]
    print(f"{path.name}: {s['frames']} frames -> ACCEPT {s['accept']} | VERIFY {s['verify']} | QUARANTINE {s['quarantine']}")
    for f in frames:
        if f.decision != "ACCEPT":
            ev = f.evidence
            print(f"  frame {f.index:3d} t={f.t_rec:7.2f}s type={f.frame_type} seq={f.sequence} "
                  f"p={f.probability:.3f} {f.decision:10s} clock={ev['u_sigma']:+.1f}sigma tele={ev['tele_ecod_tail']:.1f}")
    for al in report.get("interference") or []:
        print(f"  INTERFERENCE {al['start_s']:.1f}-{al['end_s']:.1f}s near {al['freq_hz']:.0f} Hz (p={al['peak_prob']:.3f})")
    for m in report.get("audio_duplicates") or []:
        print(f"  DUPLICATED AUDIO {m['start_s']:.1f}-{m['end_s']:.1f}s is a copy of {m['src_start_s']:.1f}s "
              f"(correlation {m['ncc']:.2f}) - replayed recording")
    if report.get("response", {}).get("frames_decoded"):
        print(f"  response: {report['response']['chosen']}  (FEC-valid frames per option: {report['response']['frames_decoded']})")
    jam_missing = [m for m in report.get("missing_frames", []) if m["under_interference"]]
    if jam_missing:
        print(f"  VERIFY: {len(jam_missing)} transmitted frame(s) unaccounted under interference "
              f"(positions {[m['position'] % 100000 for m in jam_missing][:8]}...) - jamming can hide injection")
    if "manifest" in report:
        print(f"  capture manifest: {'AUTHENTIC' if report['manifest']['authentic'] else 'TAMPERED'} "
              f"{report['manifest']['tampered_intervals_s']}")
    print(f"  absolute time: {report['absolute_time']} · {report['wall_clock_s']} s")
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(f"  report -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
