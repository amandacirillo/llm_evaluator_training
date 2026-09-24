"""Two-pass checklist generation: maker->critic, grounding gate, no cache."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import evaluator.checklist as checklist  # noqa: E402

PROMPT = "Write exactly 5 multiple-choice questions with 4 options each. No factual errors."


def _maker_returns(items):
    return lambda _p: json.dumps({"checklist": items})


def _critic_returns(items):
    return lambda _p: json.dumps({"checklist": items})


def test_two_pass_produces_grounded_criteria():
    maker = _maker_returns(
        [
            {"text": "5 questions", "priority": "CRITICAL", "source": "quote", "source_quote": "exactly 5"},
        ]
    )
    critic = _critic_returns(
        [
            {
                "text": "Exactly 5 questions are produced.",
                "priority": "CRITICAL",
                "tag": "auto",
                "check": {"kind": "question_count", "expected": 5},
                "pass_means": "There are exactly five questions.",
                "fail_means": "There are more or fewer than five.",
                "source": "quote",
                "source_quote": "exactly 5",
            },
            {
                "text": "No factual errors in any item.",
                "priority": "CRITICAL",
                "tag": "judged",
                "pass_means": "All facts correct.",
                "fail_means": "Any factual error.",
                "source": "implicit",
                "source_quote": "",
            },
        ]
    )
    result = checklist.generate_checklist(PROMPT, maker_invoke=maker, critic_invoke=critic)

    assert [c["id"] for c in result] == ["r1", "r2"]
    auto = result[0]
    assert auto["tag"] == "auto" and auto["check"]["kind"] == "question_count"
    assert auto["source"] == "quote" and auto["spans"]  # located in the prompt
    s, e = auto["spans"][0]
    assert PROMPT[s:e] == "exactly 5"

    implicit = result[1]
    assert implicit["source"] == "implicit"
    assert implicit["spans"] == [] and implicit["source_quote"] == ""


def test_unknown_auto_kind_downgraded_to_judged():
    critic = _critic_returns(
        [
            {
                "text": "Options are pedagogically sound.",
                "priority": "MINOR",
                "tag": "auto",
                "check": {"kind": "vibes"},
                "source": "implicit",
                "source_quote": "",
            }
        ]
    )
    result = checklist.generate_checklist(PROMPT, maker_invoke=_maker_returns([]), critic_invoke=critic)
    assert result[0]["tag"] == "judged"
    assert "check" not in result[0]


def test_grounding_gate_regenerates_then_keeps_grounded_attempt():
    """An ungrounded quote on attempt 1; a fully grounded set on attempt 2 wins."""
    calls = {"n": 0}

    def critic(_p):
        calls["n"] += 1
        if calls["n"] == 1:
            items = [
                {"text": "Bad", "priority": "MINOR", "tag": "judged",
                 "source": "quote", "source_quote": "this phrase is not in the prompt"},
            ]
        else:
            items = [
                {"text": "Four options each.", "priority": "CRITICAL", "tag": "auto",
                 "check": {"kind": "option_count", "expected": 4},
                 "source": "quote", "source_quote": "4 options"},
            ]
        return json.dumps({"checklist": items})

    result = checklist.generate_checklist(PROMPT, maker_invoke=_maker_returns([]), critic_invoke=critic)
    assert calls["n"] == 2  # regenerated once
    assert len(result) == 1 and result[0]["source_quote"] == "4 options"


def test_grounding_gate_demotes_ungrounded_after_max_attempts():
    """Persistently ungrounded item is demoted to implicit (kept), grounded ones stay."""
    def critic(_p):
        return json.dumps(
            {
                "checklist": [
                    {"text": "Grounded", "priority": "CRITICAL", "tag": "judged",
                     "source": "quote", "source_quote": "4 options each"},
                    {"text": "Never grounded", "priority": "MINOR", "tag": "judged",
                     "source": "quote", "source_quote": "phrase absent from prompt"},
                ]
            }
        )

    result = checklist.generate_checklist(
        PROMPT, maker_invoke=_maker_returns([]), critic_invoke=critic, max_attempts=3
    )
    by_text = {c["text"]: c for c in result}
    assert set(by_text) == {"Grounded", "Never grounded"}  # both kept
    assert by_text["Grounded"]["source"] == "quote" and by_text["Grounded"]["spans"]
    # the unlocatable one is demoted to implicit: still graded, but no highlight
    demoted = by_text["Never grounded"]
    assert demoted["source"] == "implicit"
    assert demoted["source_quote"] == "" and demoted["spans"] == []


def test_all_ungrounded_demoted_not_raised():
    """When every quote is unlocatable, items are demoted to implicit, not dropped."""
    critic = _critic_returns(
        [{"text": "x", "priority": "MINOR", "tag": "judged",
          "source": "quote", "source_quote": "definitely not present"}]
    )
    result = checklist.generate_checklist(
        PROMPT, maker_invoke=_maker_returns([]), critic_invoke=critic
    )
    assert len(result) == 1
    assert result[0]["source"] == "implicit" and result[0]["spans"] == []


def test_no_criteria_at_all_raises():
    """A genuinely empty model response (no criteria) still raises."""
    with pytest.raises(ValueError):
        checklist.generate_checklist(
            PROMPT, maker_invoke=_maker_returns([]), critic_invoke=_critic_returns([])
        )


def test_no_cache_symbols_remain():
    assert not hasattr(checklist, "_CACHE")
    assert not hasattr(checklist, "prompt_hash")
    assert not hasattr(checklist, "clear_cache")
