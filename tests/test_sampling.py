"""Multi-sample aggregation (V6): majority cell, variability, ragged counts."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from evaluator.pipeline import aggregate_samples  # noqa: E402

CHECKLIST = [
    {"id": "r1", "text": "a", "priority": "CRITICAL"},
    {"id": "r2", "text": "b", "priority": "IMPORTANT"},
]


def _slot(v1, v2, split1=False, split2=False, note1="", note2=""):
    return {
        "verdict": {"r1": v1, "r2": v2},
        "split": {"r1": split1, "r2": split2},
        "note": {"r1": note1, "r2": note2},
    }


def test_majority_cell_across_samples():
    per_sample = [
        _slot("PASS", "FAIL"),
        _slot("PASS", "FAIL"),
        _slot("FAIL", "FAIL"),
    ]
    res = aggregate_samples("m", ["o0", "o1", "o2"], [], per_sample, CHECKLIST)
    items = {it["id"]: it for it in res["items"]}
    assert items["r1"]["verdict"] == "PASS"   # 2/3 PASS
    assert items["r2"]["verdict"] == "FAIL"   # 0/3 PASS
    # No council splits -> not low-confidence even though r1's samples disagree.
    assert items["r1"]["low_confidence"] is False
    assert items["r2"]["low_confidence"] is False


def test_tie_resolves_to_fail():
    per_sample = [_slot("PASS", "PASS"), _slot("FAIL", "FAIL")]
    res = aggregate_samples("m", ["o0", "o1"], [], per_sample, CHECKLIST)
    items = {it["id"]: it for it in res["items"]}
    assert items["r1"]["verdict"] == "FAIL"   # 1-1 tie -> FAIL
    # Sample disagreement without a council split is not low-confidence.
    assert items["r1"]["low_confidence"] is False


def test_sample_disagreement_alone_not_low_confidence():
    # Samples disagree wildly but the council never split -> no asterisk.
    per_sample = [_slot("PASS", "PASS"), _slot("FAIL", "FAIL"), _slot("PASS", "FAIL")]
    res = aggregate_samples("m", ["o0", "o1", "o2"], [], per_sample, CHECKLIST)
    for it in res["items"]:
        assert it["low_confidence"] is False


def test_avg_min_max_stdev():
    # scores per sample: [1, 2, 1]
    per_sample = [
        _slot("PASS", "FAIL"),  # score 1
        _slot("PASS", "PASS"),  # score 2
        _slot("FAIL", "PASS"),  # score 1
    ]
    res = aggregate_samples("m", ["o0", "o1", "o2"], [], per_sample, CHECKLIST)
    s = res["sampling"]
    assert s["generated"] == 3 and s["graded"] == 3 and s["total_criteria"] == 2
    assert s["scores"] == [1, 2, 1]  # one dot per sample, for the beeswarm plot
    assert s["avg_score"] == 1.33
    assert s["min_score"] == 1 and s["max_score"] == 2
    assert s["stdev"] == 0.47


def test_low_confidence_from_council_split_majority():
    # r1 verdicts unanimous PASS but council split on 2 of 3 samples -> low conf.
    per_sample = [
        _slot("PASS", "PASS", split1=True),
        _slot("PASS", "PASS", split1=True),
        _slot("PASS", "PASS", split1=False),
    ]
    res = aggregate_samples("m", ["o0", "o1", "o2"], [], per_sample, CHECKLIST)
    items = {it["id"]: it for it in res["items"]}
    assert items["r1"]["verdict"] == "PASS"
    assert items["r1"]["low_confidence"] is True


def test_unscored_cell_is_not_low_confidence():
    # r1 got no judge votes across samples -> unscored, not a split.
    per_sample = [
        {"verdict": {"r1": "FAIL", "r2": "PASS"}, "split": {}, "note": {}, "no_votes": {"r1": True}},
        {"verdict": {"r1": "FAIL", "r2": "PASS"}, "split": {}, "note": {}, "no_votes": {"r1": True}},
    ]
    res = aggregate_samples("m", ["o0", "o1"], [], per_sample, CHECKLIST)
    items = {it["id"]: it for it in res["items"]}
    assert items["r1"]["no_votes"] is True
    assert items["r1"]["low_confidence"] is False
    assert "No judge was available" in items["r1"]["note"]
    assert items["r2"]["no_votes"] is False


def test_ragged_sample_counts():
    # Only one successful sample.
    per_sample = [_slot("PASS", "PASS")]
    res = aggregate_samples("m", ["only"], ["err on another call"], per_sample, CHECKLIST)
    assert res["sampling"]["generated"] == 1
    assert res["sampling"]["stdev"] == 0.0
    assert res["pass_count"] == 2 and res["pass_pct"] == 100


def test_no_successful_samples_reports_error():
    res = aggregate_samples("m", [], ["boom"], [], CHECKLIST)
    assert res["error"] == "boom"
    assert res["output"] is None
    assert res["sampling"]["generated"] == 0
    assert res["items"] == []


def test_representative_note_on_fail():
    per_sample = [_slot("FAIL", "PASS", note1="only 2 items")]
    res = aggregate_samples("m", ["o"], [], per_sample, CHECKLIST)
    items = {it["id"]: it for it in res["items"]}
    assert items["r1"]["note"] == "only 2 items"
    assert items["r2"]["note"] == ""  # PASS -> no note
