"""Phase functions grade()/generate(): event shapes, modes, edited checklist.

All LLM/network calls are stubbed: sample_models is monkeypatched and the judge
council is driven by an injected invoke_factory.
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import evaluator.pipeline as pipeline  # noqa: E402

# One JSON MCQ item so the auto-check (question_count==1, option_count==4) passes.
ITEM_JSON = json.dumps(
    {"questions": [{"stem": "2+2?", "options": ["3", "4", "5", "6"], "answer": "B"}]}
)

CHECKLIST = [
    {"id": "r1", "text": "Exactly 1 question",
     "tag": "auto", "check": {"kind": "question_count", "expected": 1},
     "source": "quote", "source_quote": "1 question", "spans": [[0, 1]]},
    {"id": "r2", "text": "No factual errors",
     "tag": "judged", "source": "implicit", "source_quote": "", "spans": []},
]


def _fake_sampler(per_model_counts):
    """Return a sample_models stub giving each model N identical ITEM_JSON samples."""
    def _sample(_prompt, models, _n):
        return {m: {"samples": [ITEM_JSON] * per_model_counts.get(m, 0), "errors": []} for m in models}
    return _sample


def _judge_all_pass(_judge):
    def _invoke(_prompt):
        # Single-output scorer: PASS the judged criterion r2.
        return json.dumps({"items": [{"id": "r2", "verdict": "PASS", "note": ""}]})
    return _invoke


def _run(gen):
    return list(gen)


def test_generate_output_only_no_scoring(monkeypatch):
    monkeypatch.setattr(pipeline, "call_models",
                        lambda _p, ms: [{"model": m, "output": f"out-{m}", "error": None} for m in ms])
    events = _run(pipeline.generate("prompt", ["m1", "m2"], title="T"))
    names = [e[0] for e in events]
    assert names == ["outputs", "done"]  # no checklist, no scoring
    done = dict(events)["done"]
    assert done["mode"] == "output_only"
    assert "checklist" not in done
    assert [m["model"] for m in done["models"]] == ["m1", "m2"]


def test_grade_scoring_full_pipeline(monkeypatch):
    monkeypatch.setattr(pipeline, "sample_models", _fake_sampler({"m1": 3, "m2": 3}))
    events = _run(
        pipeline.grade(
            "prompt", ["m1", "m2"], CHECKLIST, title="T",
            samples=3, council=["j1", "j2", "j3"], backup="jb",
            available=["j1", "j2", "j3", "jb"], rng=random.Random(0),
            invoke_factory=_judge_all_pass,
        )
    )
    names = [e[0] for e in events]
    assert names == ["outputs", "scoring", "done"]

    done = dict(events)["done"]
    assert done["mode"] == "scoring"
    assert done["checklist"] is CHECKLIST
    assert done["council"] == ["j1", "j2", "j3"]
    # Council transparency fields present (all judges available here).
    assert done["council_unavailable"] == [] and done["council_excluded"] == []

    for m in done["models"]:
        # r1 auto passes, r2 judged passes -> 2/2
        assert m["pass_count"] == 2 and m["total"] == 2 and m["pass_pct"] == 100
        assert m["sampling"]["generated"] == 3 and m["sampling"]["total_criteria"] == 2
        ids = {it["id"] for it in m["items"]}
        assert ids == {"r1", "r2"}
        for it in m["items"]:
            assert "low_confidence" in it


def test_available_models_uses_full_proxy_not_picker_allowlist(monkeypatch):
    """Judges are resolved against the full proxy list, so a judge that isn't in
    the picker allow-list still counts as available."""
    import evaluator.models as models_mod
    monkeypatch.setattr(
        models_mod, "list_all_proxy_models",
        lambda: ["claude-sonnet-4-6", "gpt-5.4", "gpt-4o", "gpt-5.4-mini"],
    )
    avail = pipeline._available_models(
        ["claude-sonnet-4-6", "gpt-5.4", "gpt-4o"], "gpt-5.4-mini", "claude-sonnet-4-6"
    )
    assert "claude-sonnet-4-6" in avail and "gpt-4o" in avail


def test_available_models_fallback_when_proxy_unreachable(monkeypatch):
    import evaluator.models as models_mod
    monkeypatch.setattr(models_mod, "list_all_proxy_models", lambda: [])
    avail = pipeline._available_models(["j1", "j2"], "backupj", "ckmodel")
    assert set(avail) >= {"j1", "j2", "backupj", "ckmodel"}


def test_score_full_pipeline_generates_then_grades(monkeypatch):
    """score() generates the checklist automatically, then grades — events are
    checklist → outputs → scoring → done."""
    monkeypatch.setattr(pipeline, "generate_checklist", lambda _p: CHECKLIST)
    monkeypatch.setattr(pipeline, "sample_models", _fake_sampler({"m1": 3, "m2": 3}))

    events = _run(
        pipeline.score("prompt", ["m1", "m2"], title="T", samples=3,
                       council=["j1", "j2", "j3"], backup="jb",
                       available=["j1", "j2", "j3", "jb"], rng=random.Random(0),
                       invoke_factory=_judge_all_pass)
    )
    names = [e[0] for e in events]
    assert names == ["checklist", "outputs", "scoring", "done"]
    ev = dict(events)
    assert ev["checklist"]["checklist"] is CHECKLIST
    assert ev["done"]["mode"] == "scoring"


def test_score_surfaces_checklist_generation_error(monkeypatch):
    def boom(_p):
        raise ValueError("no usable items")
    monkeypatch.setattr(pipeline, "generate_checklist", boom)
    events = _run(pipeline.score("prompt", ["m1"]))
    assert events[0][0] == "error"
    assert "no usable items" in events[0][1]["error"]


def test_grade_uses_passed_checklist_not_regenerated(monkeypatch):
    """V7 — grading keys off exactly the checklist handed in (user-edited)."""
    monkeypatch.setattr(pipeline, "sample_models", _fake_sampler({"m1": 1}))
    # A user-edited checklist: renamed id and only one (judged) criterion.
    edited = [
        {"id": "custom-9", "text": "USER EDITED requirement", "priority": "MINOR",
         "tag": "judged", "source": "implicit", "source_quote": "", "spans": []},
    ]

    def judge(_j):
        return lambda _p: json.dumps({"items": [{"id": "custom-9", "verdict": "PASS", "note": ""}]})

    events = _run(
        pipeline.grade("prompt", ["m1"], edited, samples=1,
                       council=["j1"], backup="jb", available=["j1", "jb"],
                       invoke_factory=judge)
    )
    done = dict(events)["done"]
    assert done["checklist"] is edited
    item_ids = {it["id"] for it in done["models"][0]["items"]}
    assert item_ids == {"custom-9"}  # the edited id, nothing regenerated


def test_unparseable_auto_criterion_graded_by_council(monkeypatch):
    """V7 — an auto criterion the parser can't verify is graded by the council
    (fallback), not auto-failed."""
    prose = "Sorry, here is a paragraph with no parseable items whatsoever."
    monkeypatch.setattr(
        pipeline, "sample_models",
        lambda _p, ms, _n: {m: {"samples": [prose], "errors": []} for m in ms},
    )

    def judge(_j):
        # Single-output scorer: PASS both criteria (r1 fell back here, r2 judged).
        return lambda _p: json.dumps({"items": [
            {"id": "r1", "verdict": "PASS", "note": ""},
            {"id": "r2", "verdict": "PASS", "note": ""},
        ]})

    events = _run(
        pipeline.grade("prompt", ["m1", "m2"], CHECKLIST, samples=1,
                       council=["j1", "j2", "j3"], backup="jb",
                       available=["j1", "j2", "j3", "jb"], invoke_factory=judge)
    )
    done = dict(events)["done"]
    for m in done["models"]:
        items = {it["id"]: it for it in m["items"]}
        # r1 is the auto criterion; prose is unparseable, so it fell back to the
        # council, which PASSed it — NOT an auto FAIL.
        assert items["r1"]["verdict"] == "PASS"
        assert items["r2"]["verdict"] == "PASS"


def test_per_model_verdicts_are_independent(monkeypatch):
    """Each output is graded alone, so different models get different verdicts —
    the judge is keyed on the OUTPUT text in the prompt, not a shared label."""
    def sampler(_p, models, _n):
        # m1 always emits a "good" output; m2 always a "bad" one.
        return {
            "m1": {"samples": ["GOOD answer"], "errors": []},
            "m2": {"samples": ["BAD answer"], "errors": []},
        }
    monkeypatch.setattr(pipeline, "sample_models", sampler)

    edited = [{"id": "r1", "text": "quality", "tag": "judged", "source": "implicit",
               "source_quote": "", "spans": []}]

    def judge(_j):
        def _invoke(prompt):
            verdict = "FAIL" if "BAD" in prompt else "PASS"
            note = "the answer is bad" if verdict == "FAIL" else ""
            return json.dumps({"items": [{"id": "r1", "verdict": verdict, "note": note}]})
        return _invoke

    events = _run(
        pipeline.grade("prompt", ["m1", "m2"], edited, samples=1,
                       council=["j1"], backup="jb", available=["j1", "jb"],
                       invoke_factory=judge)
    )
    by_model = {m["model"]: m for m in dict(events)["done"]["models"]}
    v1 = by_model["m1"]["items"][0]
    v2 = by_model["m2"]["items"][0]
    assert v1["verdict"] == "PASS"
    assert v2["verdict"] == "FAIL" and "bad" in v2["note"]


def test_grade_isolates_failed_model(monkeypatch):
    def sampler(_p, models, _n):
        return {
            "m1": {"samples": [ITEM_JSON], "errors": []},
            "broken": {"samples": [], "errors": ["ProxyError: boom"]},
        }
    monkeypatch.setattr(pipeline, "sample_models", sampler)

    events = _run(
        pipeline.grade("prompt", ["m1", "broken"], CHECKLIST, samples=1,
                       council=["j1"], backup="jb", available=["j1", "jb"],
                       rng=random.Random(0), invoke_factory=_judge_all_pass)
    )
    done = dict(events)["done"]
    by_model = {m["model"]: m for m in done["models"]}
    assert by_model["broken"]["error"] == "ProxyError: boom"
    assert by_model["broken"]["items"] == []
    assert by_model["m1"]["error"] is None
