"""Auto-checks: determinism (V1) and each check kind (V2)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from evaluator.autocheck import parse_items, run_auto_check  # noqa: E402


JSON_OUTPUT = json.dumps(
    {
        "questions": [
            {"stem": "2+2?", "options": ["3", "4", "5", "6"], "answer": "B"},
            {"stem": "Capital of France?", "options": ["Paris", "Rome", "Bonn", "Madrid"], "answer": "A"},
        ]
    }
)

TEXT_OUTPUT = """\
1. What is 2+2?
   A) 3
   B) 4
   C) 5
   D) 6
   Answer: B

2. Capital of France?
   A) Paris
   B) Rome
   C) Bonn
   D) Madrid
   Answer: A
"""

MULTI_SELECT = json.dumps(
    {"questions": [{"stem": "Pick primes", "options": ["2", "3", "4", "9"], "answers": ["A", "B"]}]}
)


def test_parses_json_and_text_to_same_structure():
    j = parse_items(JSON_OUTPUT)
    t = parse_items(TEXT_OUTPUT)
    assert len(j) == len(t) == 2
    assert j[0].options == t[0].options == ["3", "4", "5", "6"]
    assert j[0].keys == t[0].keys == [1]


def test_repeat_identical_all_kinds():
    """V1 — same output twice yields identical verdicts for every kind."""
    checks = [
        {"kind": "question_count", "expected": 2},
        {"kind": "option_count", "expected": 4},
        {"kind": "key_count", "expected": 1},
        {"kind": "no_duplicate_options"},
        {"kind": "stem_present"},
        {"kind": "schema_valid"},
    ]
    for output in (JSON_OUTPUT, TEXT_OUTPUT):
        for chk in checks:
            first = run_auto_check(chk, output)
            second = run_auto_check(chk, output)
            assert first == second


def test_question_count():
    assert run_auto_check({"kind": "question_count", "expected": 2}, JSON_OUTPUT)["verdict"] == "PASS"
    assert run_auto_check({"kind": "question_count", "expected": 5}, JSON_OUTPUT)["verdict"] == "FAIL"


def test_option_count():
    assert run_auto_check({"kind": "option_count", "expected": 4}, JSON_OUTPUT)["verdict"] == "PASS"
    three = json.dumps({"questions": [{"stem": "q", "options": ["a", "b", "c"], "answer": "A"}]})
    assert run_auto_check({"kind": "option_count", "expected": 4}, three)["verdict"] == "FAIL"


def test_key_count_single():
    assert run_auto_check({"kind": "key_count", "expected": 1}, JSON_OUTPUT)["verdict"] == "PASS"
    assert run_auto_check({"kind": "key_count", "expected": 2}, JSON_OUTPUT)["verdict"] == "FAIL"


def test_key_count_multi():
    assert run_auto_check({"kind": "key_count", "expected": 2}, MULTI_SELECT)["verdict"] == "PASS"
    assert run_auto_check({"kind": "key_count", "expected": 1}, MULTI_SELECT)["verdict"] == "FAIL"


def test_no_duplicate_options():
    assert run_auto_check({"kind": "no_duplicate_options"}, JSON_OUTPUT)["verdict"] == "PASS"
    dup = json.dumps({"questions": [{"stem": "q", "options": ["a", "a", "b", "c"], "answer": "A"}]})
    assert run_auto_check({"kind": "no_duplicate_options"}, dup)["verdict"] == "FAIL"


def test_stem_present():
    assert run_auto_check({"kind": "stem_present"}, JSON_OUTPUT)["verdict"] == "PASS"
    nostem = json.dumps({"questions": [{"stem": "", "options": ["a", "b", "c", "d"], "answer": "A"}]})
    assert run_auto_check({"kind": "stem_present"}, nostem)["verdict"] == "FAIL"


def test_schema_valid():
    assert run_auto_check({"kind": "schema_valid"}, JSON_OUTPUT)["verdict"] == "PASS"
    # No items at all -> UNVERIFIABLE (defer to judge), not FAIL.
    assert run_auto_check({"kind": "schema_valid"}, "just some prose, no items")["verdict"] == "UNVERIFIABLE"


def test_unparseable_output_is_unverifiable_and_deterministic():
    prose = "I cannot help with that."
    r1 = run_auto_check({"kind": "question_count", "expected": 2}, prose)
    r2 = run_auto_check({"kind": "question_count", "expected": 2}, prose)
    assert r1["verdict"] == "UNVERIFIABLE" and r1 == r2


def test_unknown_kind_is_unverifiable():
    assert run_auto_check({"kind": "vibes"}, JSON_OUTPUT)["verdict"] == "UNVERIFIABLE"


MARKDOWN_OUTPUT = """\
### Question 1
What is 2+2?
- **A)** 3
- **B)** 4
- **C)** 5
- **D)** 6

**Answer:** B

### Question 2
Capital of France?
- (A) Paris
- (B) Rome
- (C) Bonn
- (D) Madrid

Correct answer: A
"""


def test_hardened_markdown_format_parses():
    items = parse_items(MARKDOWN_OUTPUT)
    assert len(items) == 2
    assert items[0].options == ["3", "4", "5", "6"]
    assert items[0].keys == [1]  # B
    assert items[1].keys == [0]  # A
    assert run_auto_check({"kind": "question_count", "expected": 2}, MARKDOWN_OUTPUT)["verdict"] == "PASS"
    assert run_auto_check({"kind": "option_count", "expected": 4}, MARKDOWN_OUTPUT)["verdict"] == "PASS"
    assert run_auto_check({"kind": "key_count", "expected": 1}, MARKDOWN_OUTPUT)["verdict"] == "PASS"
