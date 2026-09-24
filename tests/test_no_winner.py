"""V10 — the tool must never emit a winner / ranking / recommendation.

Scan every payload from both phase generators (and the maker/critic checklist)
for forbidden keys and words.
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import evaluator.pipeline as pipeline  # noqa: E402
import evaluator.checklist as checklist  # noqa: E402

FORBIDDEN_WORDS = ("winner", "ranking", "ranked", "recommend", "best model", "is better", "we suggest")
FORBIDDEN_KEYS = {"winner", "ranking", "rank", "recommendation", "best", "verdict_overall"}

ITEM_JSON = json.dumps({"questions": [{"stem": "q", "options": ["a", "b", "c", "d"], "answer": "A"}]})
CHECKLIST = [
    {"id": "r1", "text": "one question", "priority": "CRITICAL",
     "tag": "auto", "check": {"kind": "question_count", "expected": 1},
     "source": "quote", "source_quote": "one question", "spans": [[0, 1]]},
    {"id": "r2", "text": "no errors", "priority": "CRITICAL",
     "tag": "judged", "source": "implicit", "source_quote": "", "spans": []},
]


def _assert_clean(payload):
    blob = json.dumps(payload).lower()
    for word in FORBIDDEN_WORDS:
        assert word not in blob, f"forbidden phrase {word!r} in payload"

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                assert k.lower() not in FORBIDDEN_KEYS, f"forbidden key {k!r}"
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)


def test_no_winner_in_grade(monkeypatch):
    monkeypatch.setattr(
        pipeline, "sample_models",
        lambda _p, ms, _n: {m: {"samples": [ITEM_JSON], "errors": []} for m in ms},
    )

    def judge(_j):
        return lambda _p: json.dumps(
            {"outputs": {lbl: {"items": [{"id": "r2", "verdict": "PASS", "note": ""}]}
                         for lbl in ("A", "B")}}
        )

    for _name, payload in pipeline.grade(
        "prompt", ["m1", "m2"], CHECKLIST, samples=1,
        council=["j1"], backup="jb", available=["j1", "jb"],
        rng=random.Random(0), invoke_factory=judge,
    ):
        _assert_clean(payload)


def test_no_winner_in_generate(monkeypatch):
    monkeypatch.setattr(
        pipeline, "call_models",
        lambda _p, ms: [{"model": m, "output": "x", "error": None} for m in ms],
    )
    for _name, payload in pipeline.generate("prompt", ["m1", "m2"]):
        _assert_clean(payload)


def test_no_winner_in_checklist():
    made = checklist.generate_checklist(
        "Write one question about x.",
        maker_invoke=lambda _p: json.dumps({"checklist": []}),
        critic_invoke=lambda _p: json.dumps(
            {"checklist": [{"text": "one question present", "priority": "CRITICAL",
                            "tag": "judged", "source": "quote", "source_quote": "one question"}]}
        ),
    )
    _assert_clean({"checklist": made})
