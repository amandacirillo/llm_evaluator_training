"""Blinding (V5) under per-output grading: each judge sees ONE identity-stripped
output, and no model id ever appears in a judge prompt. LLM-free (injected fakes)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from evaluator.pipeline import council_grade_output  # noqa: E402


def test_no_model_id_in_judge_prompt():
    judged = [{"id": "r1", "text": "no factual errors"}]
    seen = []

    def factory(_judge):
        def _invoke(prompt):
            seen.append(prompt)
            return json.dumps({"items": [{"id": "r1", "verdict": "PASS", "note": ""}]})
        return _invoke

    council_grade_output(
        judged, "Some answer text produced by a model.", ["gpt-5.4", "claude-sonnet-4-6"],
        invoke_factory=factory,
    )
    assert seen
    for prompt in seen:
        for model_id in ("gpt-5.4", "claude-sonnet-4-6", "gpt-4o"):
            assert model_id not in prompt
        # The single output is present, labeled generically.
        assert "OUTPUT:" in prompt and "Some answer text" in prompt


def test_council_majority_and_split_per_output():
    judged = [{"id": "r1", "text": "x"}]
    scripts = {"j1": "PASS", "j2": "PASS", "j3": "FAIL"}

    def factory(judge):
        return lambda _p: json.dumps({"items": [{"id": "r1", "verdict": scripts[judge], "note": ""}]})

    res = council_grade_output(judged, "text", ["j1", "j2", "j3"], invoke_factory=factory)
    assert res["r1"]["verdict"] == "PASS"   # 2 PASS vs 1 FAIL
    assert res["r1"]["split"] is True       # not unanimous
    assert res["r1"]["no_votes"] is False


def test_council_unanimous_no_split():
    judged = [{"id": "r1", "text": "x"}]

    def factory(_judge):
        return lambda _p: json.dumps({"items": [{"id": "r1", "verdict": "FAIL", "note": "missing X"}]})

    res = council_grade_output(judged, "text", ["j1", "j2", "j3"], invoke_factory=factory)
    assert res["r1"]["verdict"] == "FAIL"
    assert res["r1"]["split"] is False
    assert res["r1"]["note"] == "missing X"


def test_empty_judges_is_unscored_not_split():
    judged = [{"id": "r1", "text": "x"}]
    res = council_grade_output(judged, "text", [], invoke_factory=lambda m: (lambda p: "{}"))
    assert res["r1"]["verdict"] == "FAIL"
    assert res["r1"]["split"] is False
    assert res["r1"]["no_votes"] is True


def test_id_normalization_and_top_level_list():
    judged = [{"id": "r1", "text": "x"}]

    def factory(_judge):
        # Uppercase id and a top-level list instead of {"items": [...]}.
        return lambda _p: json.dumps([{"id": "R1", "verdict": "PASS", "note": ""}])

    res = council_grade_output(judged, "text", ["j1"], invoke_factory=factory)
    assert res["r1"]["verdict"] == "PASS" and res["r1"]["no_votes"] is False


def test_one_failing_judge_does_not_abort():
    judged = [{"id": "r1", "text": "x"}]

    def factory(judge):
        if judge == "bad":
            def _boom(_p):
                raise RuntimeError("judge exploded")
            return _boom
        return lambda _p: json.dumps({"items": [{"id": "r1", "verdict": "PASS", "note": ""}]})

    res = council_grade_output(judged, "text", ["bad", "good"], invoke_factory=factory)
    assert res["r1"]["verdict"] == "PASS" and res["r1"]["no_votes"] is False
