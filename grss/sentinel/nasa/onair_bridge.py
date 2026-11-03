"""Run NASA OnAIR (On-board AI Research platform, GSFC; shipped in NOS3 as
components/onair) on decoded AO-73 telemetry.

OnAIR is used as-is: its ``Agent`` and ``VehicleRepresentation`` evaluate each
frame with OnAIR's telemetry test suite (FEASIBILITY limits → GREEN / YELLOW /
RED with Dempster–Shafer confidence) and run knowledge-representation plugins.
We supply three things: a data source that streams our frames, a telemetry
config whose limits are learned from the training passes, and an OnAIR plugin
for the frame-counter clock check.

OnAIR is not vendored. Point ``SENTINEL_ONAIR_PATH`` at an OnAIR checkout
(github.com/nasa/OnAIR, NOSA licence); by default the NOS3 copy next to this
repository is used.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np

from .. import PROJECT_ROOT
from ..cache import fingerprint
from ..data.corpus import Pass, load_pass
from ..decode import funcube
from ..detect.telemetry import FIELDS

PLUGIN_DIR = Path(__file__).with_name("onair_plugins") / "sentinel_clock"
HEADERS = ["Time", *[f.upper() for f in FIELDS], "FRAME_POSITION"]
CANDIDATES = [
    os.environ.get("SENTINEL_ONAIR_PATH", ""),
    str(PROJECT_ROOT.parent.parent.parent / "tsyp-grss" / "nos3-1_07_05" / "components" / "onair" / "fsw"),
    str(Path.home() / ".sentinel" / "OnAIR" / "fsw"),
    str(Path.home() / ".sentinel" / "OnAIR"),
]


def onair_path() -> Path | None:
    for c in CANDIDATES:
        if c and (Path(c) / "onair" / "src" / "reasoning" / "agent.py").exists():
            return Path(c)
    return None


def available() -> bool:
    return onair_path() is not None


def _import_onair():
    path = onair_path()
    if path is None:
        raise RuntimeError("NASA OnAIR not found: set SENTINEL_ONAIR_PATH to an OnAIR checkout")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    from onair.data_handling.on_air_data_source import OnAirDataSource
    from onair.data_handling.parser_util import extract_meta_data_handle_ss_breakdown
    from onair.src.reasoning.agent import Agent
    from onair.src.systems.vehicle_rep import VehicleRepresentation
    return OnAirDataSource, extract_meta_data_handle_ss_breakdown, Agent, VehicleRepresentation


def learn_limits(passes: list[Pass]) -> dict[str, list[float]]:
    """FEASIBILITY limits [red|yellow, yellow|green, green|yellow, yellow|red]
    per telemetry channel, from clean training passes."""
    rows = []
    for p in passes:
        for f in p.parsed():
            if f:
                rows.append([f.telemetry[k] for k in FIELDS])
    M = np.array(rows, float)
    limits = {}
    for j, name in enumerate(FIELDS):
        lo, hi = np.percentile(M[:, j], [0.5, 99.5])
        span = max(hi - lo, 1.0)
        limits[name.upper()] = [round(float(lo - 0.6 * span), 3), round(float(lo - 0.15 * span), 3),
                                round(float(hi + 0.15 * span), 3), round(float(hi + 0.6 * span), 3)]
    return limits


def telemetry_config(limits: dict[str, list[float]]) -> dict:
    """OnAIR telemetry configuration (same schema as OnAIR's own configs)."""
    subsystems = {"NONE": {"Time": {"conversion": "", "tests": {"NOOP": "[]"}, "description": "Frame start, s"}},
                  "POWER": {}, "THERMAL": {}, "OBC": {}}
    for name in HEADERS[1:]:
        ss = "THERMAL" if "TEMP" in name else "OBC" if name in ("REBOOT_COUNT", "SOFTWARE_ERRORS", "FRAME_POSITION") else "POWER"
        tests = {"NOOP": "[]"} if name == "FRAME_POSITION" else {"FEASIBILITY": json.dumps(limits[name])}
        subsystems[ss][name] = {"conversion": "", "tests": tests, "description": f"AO-73 {name.lower()}"}
    return {"subsystems": subsystems, "order": HEADERS}


def training_limits() -> dict[str, list[float]]:
    from ..redteam import scenario
    train, _ = scenario.split()
    version = tuple((str(d), fingerprint(d / "decoded.json")) for d in train)
    return _training_limits(version)


@lru_cache(maxsize=1)
def _training_limits(version: tuple) -> dict[str, list[float]]:
    return learn_limits([load_pass(Path(directory)) for directory, _ in version])


def run(p: Pass, limits: dict[str, list[float]] | None = None, period_s: float = 4.9885) -> list[dict]:
    """Stream one pass through OnAIR. Returns one record per decoded frame."""
    OnAirDataSource, extract_meta, Agent, VehicleRepresentation = _import_onair()
    os.environ["SENTINEL_FRAME_PERIOD_S"] = str(period_s)
    limits = limits or training_limits()

    frames = []
    for t, payload in zip(p.t_rec, p.payloads):
        f = funcube.parse(payload)
        if f:
            frames.append([float(t), *[f.telemetry[k] for k in FIELDS], float(f.position)])

    class PassSource(OnAirDataSource):
        def parse_meta_data_file(self, meta_data_file, ss_breakdown):
            return extract_meta(meta_data_file, ss_breakdown)

        def process_data_file(self, data_file):
            self.frames, self.index = data_file, 0

        def get_vehicle_metadata(self):
            return self.all_headers, self.binning_configs["test_assignments"]

        def get_next(self):
            self.index += 1
            return self.frames[self.index - 1]

        def has_more(self):
            return self.index < len(self.frames)

    with tempfile.TemporaryDirectory() as tmp:
        meta = Path(tmp) / "ao73_TLM_CONFIG.json"
        meta.write_text(json.dumps(telemetry_config(limits)), encoding="utf-8")
        source = PassSource(frames, str(meta), ss_breakdown=True)
        headers, tests = source.get_vehicle_metadata()
        vehicle = VehicleRepresentation(headers, tests, {"Sentinel Clock": str(PLUGIN_DIR)})
        agent = Agent(vehicle, {}, {}, {})
        out = []
        while source.has_more():
            frame = source.get_next()
            agent.reason(frame)
            status, conf = vehicle.get_status(), vehicle.get_bayesian_status()
            out.append({
                "t_rec": frame[0],
                "status": status,
                "confidence": round(float(conf[1] if isinstance(conf, (list, tuple)) else conf), 3),
                "faulting": [m for m in vehicle.get_current_faulting_mnemonics() if m != "Time"],
                "clock": vehicle.get_state_information().get("Sentinel Clock", {}),
            })
    return out
