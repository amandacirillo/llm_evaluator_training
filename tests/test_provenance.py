"""Provenance: find_quote offsets, multi-match, grounding gate, implicit items."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from evaluator.provenance import find_quote, ground_checklist  # noqa: E402


def test_find_quote_offsets():
    prompt = "Generate 5 questions for 6th graders."
    spans = find_quote(prompt, "5 questions")
    assert len(spans) == 1
    s, e = spans[0]
    assert prompt[s:e] == "5 questions"


def test_multi_match_returns_all():
    prompt = "four options. Each item has four options labeled A-D."
    spans = find_quote(prompt, "four options")
    assert len(spans) == 2
    for s, e in spans:
        assert prompt[s:e] == "four options"


def test_whitespace_flexible_match_maps_to_raw_offsets():
    # Quote uses single spaces; prompt has a newline + extra spaces.
    prompt = "Each question has exactly\n   four   options."
    spans = find_quote(prompt, "four options")
    assert len(spans) == 1
    s, e = spans[0]
    # Offsets index the RAW prompt (including the original whitespace).
    assert prompt[s:e] == "four   options"


def test_missing_quote_returns_empty():
    assert find_quote("A short prompt.", "not in the prompt") == []
    assert find_quote("A short prompt.", "") == []
    assert find_quote("A short prompt.", "   ") == []


def test_ground_checklist_sets_spans_and_splits():
    prompt = "Write exactly 5 multiple-choice questions with 4 options each."
    checklist = [
        {"id": "r1", "source": "quote", "source_quote": "exactly 5"},
        {"id": "r2", "source": "quote", "source_quote": "4 options"},
        {"id": "r3", "source": "quote", "source_quote": "no factual errors"},  # absent
    ]
    grounded, ungrounded = ground_checklist(prompt, checklist)

    ids_grounded = {i["id"] for i in grounded}
    ids_ungrounded = {i["id"] for i in ungrounded}
    assert ids_grounded == {"r1", "r2"}
    assert ids_ungrounded == {"r3"}

    r1 = next(i for i in grounded if i["id"] == "r1")
    s, e = r1["spans"][0]
    assert prompt[s:e] == "exactly 5"


def test_typography_tolerant_match_maps_to_raw_offsets():
    # Prompt uses non-breaking hyphen (U+2011), en-dash (U+2013), and smart quotes;
    # the model's quote copies them as plain ASCII. They must still match, and the
    # offsets must slice the RAW (fancy) prompt exactly.
    prompt = "Target CEFR A1–B1 with a 2‑item set. “Questions 1–2.”"
    for ascii_quote, expected_raw in [
        ("A1-B1", "A1–B1"),
        ("2-item", "2‑item"),
        ('"Questions 1-2."', "“Questions 1–2.”"),
    ]:
        spans = find_quote(prompt, ascii_quote)
        assert len(spans) == 1, ascii_quote
        s, e = spans[0]
        assert prompt[s:e] == expected_raw


def test_typography_folding_is_length_preserving():
    # Folding must not change string length, or offsets would drift.
    from evaluator.provenance import _fold_typography

    raw = "A1–B1 2‑item “q” ‘x’ a b"
    assert len(_fold_typography(raw)) == len(raw)


def test_implicit_item_grounded_with_no_spans():
    prompt = "Write 5 questions."
    checklist = [{"id": "r1", "source": "implicit", "source_quote": "ignored"}]
    grounded, ungrounded = ground_checklist(prompt, checklist)
    assert ungrounded == []
    assert grounded[0]["spans"] == []
    assert grounded[0]["source_quote"] == ""
    assert grounded[0]["source"] == "implicit"
