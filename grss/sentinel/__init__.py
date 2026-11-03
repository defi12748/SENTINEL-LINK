"""SENTINEL-LINK — secure ground-link testbed (TSYP14 Track 1)."""

import os
from pathlib import Path

__version__ = "0.2.0"

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DATA_ROOT = Path(os.environ.get("SENTINEL_DATA_ROOT", PROJECT_ROOT / "data")).resolve()
RESULTS_ROOT = Path(os.environ.get("SENTINEL_RESULTS_ROOT", PROJECT_ROOT / "results")).resolve()
