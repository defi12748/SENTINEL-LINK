"""NASA OnAIR integration on real AO-73 passes (skipped if OnAIR is not installed)."""

import pytest

from sentinel.data.corpus import corpus_root, load_pass
from sentinel.nasa import onair_bridge

pytestmark = pytest.mark.skipif(not onair_bridge.available(), reason="NASA OnAIR checkout not found")


def test_onair_clean_pass_is_green():
    recs = onair_bridge.run(load_pass(corpus_root() / "obs_15261075"))
    assert recs and all(r["status"] == "GREEN" for r in recs)
    assert all(r["clock"]["status"] == "GREEN" for r in recs)


def test_onair_clock_plugin_flags_replayed_frames():
    from sentinel.redteam import scenario
    ap = scenario.build(corpus_root() / "obs_15123656", 1000, "standard")
    recs = onair_bridge.run(ap.pass_)
    red = [r["clock"]["status"] == "RED" for r in recs]
    caught = sum(r and l for r, l in zip(red, ap.labels))
    false_alarms = sum(r and not l for r, l in zip(red, ap.labels))
    assert caught >= 0.9 * ap.labels.sum() and false_alarms == 0
