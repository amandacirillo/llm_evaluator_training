"""Evaluation pipeline: two modes, stateless, blinded, multi-sampled.

Phase functions (all generators yielding (event_name, payload) for the SSE layer):

- ``generate`` — output-only mode: call each model once, return outputs. No
  checklist, no scoring.
- ``grade`` — scoring mode phase 2: given the user-approved checklist, call each
  model N times, grade every sample (deterministic auto-checks in code; judged
  criteria by a blinded judge council), and aggregate across samples.

Blinding: each output is graded ALONE (labeled just "OUTPUT", no model name), so a
judge can neither recognize its own output nor confuse it with another model's.
Every (model, sample) output is graded independently — this removes the
cross-output anchoring that made different models score alike.

The pure helpers (`aggregate_samples`, `aggregate_votes`, `council_grade_output`)
are LLM-free and unit-tested with injected fakes. The tool never emits a winner.
"""

from __future__ import annotations

import logging
import random
import statistics
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from .checklist import generate_checklist  # noqa: F401  (re-exported for callers/tests)
from .config import load_evaluator_config
from .council import aggregate_votes, resolve_council
from .autocheck import run_auto_check
from .llm import call_model, get_llm, parse_json_response
from .prompts import CHECKLIST_SCORER_PROMPT

logger = logging.getLogger(__name__)

Event = Tuple[str, dict]
# A judge invoke factory maps a model id -> a callable(prompt) -> raw judge text.
JudgeInvokeFactory = Callable[[str], Callable[[str], str]]


# ---------------------------------------------------------------------------
# Model calls
# ---------------------------------------------------------------------------

def call_models(prompt: str, models: List[str]) -> List[dict]:
    """Call each model once, in parallel, fault-isolated (output-only mode)."""
    results: List[Optional[dict]] = [None] * len(models)

    def _one(idx: int, model: str) -> None:
        try:
            text = call_model(model, prompt)
            results[idx] = {"model": model, "output": text, "error": None}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Model %s failed: %s", model, exc)
            results[idx] = {"model": model, "output": None, "error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=max(1, len(models))) as pool:
        for idx, model in enumerate(models):
            pool.submit(_one, idx, model)
    return [r for r in results if r is not None]


def sample_models(prompt: str, models: List[str], n: int) -> Dict[str, dict]:
    """Call each model ``n`` times in parallel. Returns per model
    ``{"samples": [text, ...], "errors": [msg, ...]}`` — ragged success tolerated.
    """
    tasks = [(m, i) for m in models for i in range(max(1, n))]
    outcomes: List[Optional[Tuple[str, Optional[str], Optional[str]]]] = [None] * len(tasks)

    def _one(idx: int, model: str) -> None:
        try:
            outcomes[idx] = (model, call_model(model, prompt), None)
        except Exception as exc:  # noqa: BLE001
            outcomes[idx] = (model, None, f"{type(exc).__name__}: {exc}")

    with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as pool:
        for idx, (model, _i) in enumerate(tasks):
            pool.submit(_one, idx, model)

    results: Dict[str, dict] = {m: {"samples": [], "errors": []} for m in models}
    for outcome in outcomes:
        if outcome is None:
            continue
        model, text, err = outcome
        if err is not None:
            results[model]["errors"].append(err)
        else:
            results[model]["samples"].append(text)
    return results


# ---------------------------------------------------------------------------
# Judged grading via the council — ONE identity-stripped output per judge prompt
# ---------------------------------------------------------------------------

def _format_checklist(checklist: List[dict]) -> str:
    return "\n".join(f"[{c['id']}] {c['text']}" for c in checklist)


def _verdicts_by_id(parsed: dict, judged: List[dict]) -> Dict[str, dict]:
    """Parse a single judge's ``{"items": [{id, verdict, note}]}`` into
    ``{id: {verdict, note}}``, restricted to known ids (matched case-insensitively;
    tolerates a top-level list or a `scores` key)."""
    valid_by_lower = {c["id"].lower(): c["id"] for c in judged}
    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        items = parsed.get("items") or parsed.get("scores") or []
    else:
        items = []
    by_id: Dict[str, dict] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        canonical = valid_by_lower.get(str(it.get("id", "")).strip().lower())
        if canonical is None:
            continue
        verdict = "PASS" if str(it.get("verdict", "FAIL")).upper() == "PASS" else "FAIL"
        by_id[canonical] = {"verdict": verdict, "note": str(it.get("note", ""))}
    return by_id


def _judge_llm_factory(model: str) -> Callable[[str], str]:
    def _invoke(prompt: str) -> str:
        llm = get_llm(model=model, temperature=0.0, json_mode=True)
        response = llm.invoke(prompt)
        return response.content if isinstance(response.content, str) else str(response.content)

    return _invoke


def council_grade_output(
    judged: List[dict],
    output_text: str,
    judges: List[str],
    *,
    invoke_factory: Optional[JudgeInvokeFactory] = None,
) -> Dict[str, dict]:
    """Grade ONE identity-stripped output with the council. The output is presented
    alone (labeled just "OUTPUT", no model name) so the judge can't confuse it with
    other outputs or recognize its own. Returns
    ``{id: {verdict, split, no_votes, note}}`` (majority vote per criterion)."""
    if not judged:
        return {}

    factory = invoke_factory or _judge_llm_factory
    prompt = CHECKLIST_SCORER_PROMPT.format(
        checklist=_format_checklist(judged),
        output=output_text,
    )

    per_judge: List[Dict[str, dict]] = []
    for judge in judges:
        # Isolate each judge: one erroring/timing-out judge = no vote, not an abort.
        try:
            raw = factory(judge)(prompt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("judge %s failed: %s", judge, exc)
            per_judge.append({})
            continue
        verdicts = _verdicts_by_id(parse_json_response(raw, fallback={}), judged)
        if not verdicts:
            logger.warning("judge %s returned no parseable verdicts; raw head: %s", judge, str(raw)[:200])
        per_judge.append(verdicts)

    result: Dict[str, dict] = {}
    for c in judged:
        votes = [pj[c["id"]]["verdict"] for pj in per_judge if c["id"] in pj]
        agg = aggregate_votes(votes)
        note = ""
        if agg["verdict"] == "FAIL":
            for pj in per_judge:
                cell = pj.get(c["id"])
                if cell and cell["verdict"] == "FAIL" and cell.get("note"):
                    note = cell["note"]
                    break
        result[c["id"]] = {
            "verdict": agg["verdict"],
            "split": agg["split"],
            "no_votes": agg["no_votes"],
            "note": note,
        }
    return result


# ---------------------------------------------------------------------------
# Aggregation across samples (pure)
# ---------------------------------------------------------------------------

def aggregate_samples(
    model: str,
    samples: List[str],
    errors: List[str],
    per_sample: List[dict],
    checklist: List[dict],
) -> dict:
    """Aggregate a model's N per-sample verdicts into one result entry.

    ``per_sample[i]`` is ``{"verdict": {id: PASS/FAIL}, "split": {id: bool},
    "note": {id: str}}`` for sample i. Grid cell = majority verdict across
    samples (tie -> FAIL). ``low_confidence`` = samples disagree OR the council
    split on at least half the samples. Also computes the variability summary.
    """
    total = len(checklist)
    generated = len(samples)

    if generated == 0:
        return {
            "model": model,
            "output": None,
            "error": errors[0] if errors else "model produced no output",
            "pass_count": 0,
            "total": total,
            "pass_pct": 0,
            "items": [],
            "sampling": {
                "generated": 0, "graded": 0, "total_criteria": total, "scores": [],
                "avg_score": 0.0, "min_score": 0, "max_score": 0, "stdev": 0.0,
            },
        }

    def verdict_of(i: int, cid: str) -> str:
        return per_sample[i]["verdict"].get(cid, "FAIL")

    # Per-sample score = number of criteria passed that sample.
    per_sample_scores = [
        sum(1 for c in checklist if verdict_of(i, c["id"]) == "PASS") for i in range(generated)
    ]

    items: List[dict] = []
    for c in checklist:
        cid = c["id"]
        verdicts = [verdict_of(i, cid) for i in range(generated)]
        passes = verdicts.count("PASS")
        fails = generated - passes
        agg_verdict = "PASS" if passes > fails else "FAIL"  # tie -> FAIL

        # A cell whose samples were predominantly unscored (no judge available) is
        # reported as such — never as a split, never low-confidence.
        no_vote_flags = [bool(per_sample[i].get("no_votes", {}).get(cid, False)) for i in range(generated)]
        predominantly_unscored = any(no_vote_flags) and sum(no_vote_flags) * 2 >= generated

        # Low confidence = the judge council was split on at least half the
        # samples. Sample-to-sample variability alone is NOT low confidence (it is
        # shown by the spread column); purely deterministic auto criteria have
        # split=False on every sample and so are never flagged.
        splits = [bool(per_sample[i]["split"].get(cid, False)) for i in range(generated)]
        low_confidence = (not predominantly_unscored) and any(splits) and sum(splits) * 2 >= generated

        if predominantly_unscored:
            note = "No judge was available to score this criterion."
        else:
            note = ""
            if agg_verdict == "FAIL":
                for i in range(generated):
                    if verdict_of(i, cid) == "FAIL" and per_sample[i]["note"].get(cid):
                        note = per_sample[i]["note"][cid]
                        break

        items.append({
            "id": cid,
            "verdict": agg_verdict,
            "note": note,
            "low_confidence": low_confidence,
            "no_votes": predominantly_unscored,
        })

    pass_count = sum(1 for it in items if it["verdict"] == "PASS")
    pass_pct = round(100 * pass_count / total) if total else 0

    return {
        "model": model,
        "output": samples[0],  # representative sample for the side-by-side column
        "error": None,
        "pass_count": pass_count,
        "total": total,
        "pass_pct": pass_pct,
        "items": items,
        "sampling": {
            "generated": generated,
            "graded": generated,
            "total_criteria": total,
            "scores": list(per_sample_scores),  # one per sample — the dots of the plot
            "avg_score": round(statistics.fmean(per_sample_scores), 2),
            "min_score": min(per_sample_scores),
            "max_score": max(per_sample_scores),
            "stdev": round(statistics.pstdev(per_sample_scores), 2) if generated > 1 else 0.0,
        },
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _available_models(council: List[str], backup: str, checklist_model: str = "") -> List[str]:
    """Model ids usable as judges — the FULL proxy /models list, not the picker
    allow-list (config/models.json), which generally excludes the judge models.
    Falls back to the configured judge ids (assumed available) if the proxy list
    can't be fetched."""
    try:
        from .models import list_all_proxy_models

        models = list_all_proxy_models()
        if models:
            return list(models)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch proxy model list for council: %s", exc)
    fallback = list(council)
    for extra in (backup, checklist_model):
        if extra and extra not in fallback:
            fallback.append(extra)
    return fallback


def generate(prompt: str, models: List[str], *, title: Optional[str] = None) -> Iterator[Event]:
    """Output-only mode: one generation per model, no checklist/scoring."""
    try:
        model_results = call_models(prompt, models)
        outputs = [
            {"model": r["model"], "output": r["output"], "error": r["error"]} for r in model_results
        ]
        yield ("outputs", {"outputs": outputs})
        yield ("done", {"title": title, "mode": "output_only", "models": outputs})
    except Exception as exc:  # noqa: BLE001
        logger.exception("generate failed")
        yield ("error", {"error": f"{type(exc).__name__}: {exc}"})


def grade(
    prompt: str,
    models: List[str],
    checklist: List[dict],
    *,
    title: Optional[str] = None,
    samples: Optional[int] = None,
    council: Optional[List[str]] = None,
    backup: Optional[str] = None,
    available: Optional[List[str]] = None,
    rng: Optional[random.Random] = None,
    invoke_factory: Optional[JudgeInvokeFactory] = None,
) -> Iterator[Event]:
    """Scoring mode phase 2: grade the user-approved checklist by multi-sampling
    each model and combining auto-checks with a blinded judge council."""
    try:
        cfg = load_evaluator_config()
        n = samples if samples is not None else cfg["samples"]
        council_cfg = council if council is not None else cfg["council"]
        backup_cfg = backup if backup is not None else cfg["backup_judge"]
        checklist_model_cfg = cfg["checklist_model"]

        auto_criteria = [c for c in checklist if c.get("tag") == "auto" and c.get("check")]
        judged_criteria = [c for c in checklist if c not in auto_criteria]

        # 1) Sample every model N times.
        sampled = sample_models(prompt, models, n)
        outputs_payload = []
        for m in models:
            s = sampled[m]
            if s["samples"]:
                outputs_payload.append({"model": m, "output": s["samples"][0], "error": None})
            else:
                outputs_payload.append(
                    {"model": m, "output": None, "error": s["errors"][0] if s["errors"] else "model call failed"}
                )
        yield ("outputs", {"outputs": outputs_payload})

        # 2) Resolve the council for the models under test (self-judging safeguard).
        avail = (
            available if available is not None
            else _available_models(council_cfg, backup_cfg, checklist_model_cfg)
        )
        resolved = resolve_council(
            council_cfg, backup_cfg, models, avail, fallback=[checklist_model_cfg]
        )
        judges = resolved["judges"]
        logger.info("council resolved to judges=%s (available=%d)", judges, len(avail))
        for note in resolved["notes"]:
            logger.info("council: %s", note)

        yield ("scoring", {"status": "scoring"})

        # 3) Grade every (model, sample) output INDEPENDENTLY. Each output is sent
        #    to the council alone (identity-stripped), so verdicts don't bleed
        #    across models. Auto criteria are checked in code; one the parser can't
        #    verify for an output falls back to the council for THAT output only.
        auto_by_id = {c["id"]: c for c in auto_criteria}
        per_sample: Dict[str, List[dict]] = {
            m: [{} for _ in sampled[m]["samples"]] for m in models
        }
        missing = {"verdict": "FAIL", "split": False, "no_votes": True, "note": ""}

        def _grade_one(model_name: str, idx: int, text: str) -> Tuple[str, int, dict]:
            slot = {"verdict": {}, "split": {}, "note": {}, "no_votes": {}}
            fallback_ids = set()
            for c in auto_criteria:
                res = run_auto_check(c["check"], text)
                if res["verdict"] == "UNVERIFIABLE":
                    fallback_ids.add(c["id"])
                else:
                    slot["verdict"][c["id"]] = res["verdict"]
                    slot["split"][c["id"]] = False
                    slot["note"][c["id"]] = res["note"]
                    slot["no_votes"][c["id"]] = False

            council_criteria = judged_criteria + [
                auto_by_id[cid] for cid in fallback_ids if cid in auto_by_id
            ]
            cv = council_grade_output(council_criteria, text, judges, invoke_factory=invoke_factory)
            for c in council_criteria:
                d = cv.get(c["id"], missing)
                slot["verdict"][c["id"]] = d["verdict"]
                slot["split"][c["id"]] = d["split"]
                slot["no_votes"][c["id"]] = d.get("no_votes", False)
                slot["note"][c["id"]] = d.get("note", "")
            return model_name, idx, slot

        tasks = [
            (m, i, sampled[m]["samples"][i])
            for m in models
            for i in range(len(sampled[m]["samples"]))
        ]
        if tasks:
            with ThreadPoolExecutor(max_workers=min(16, len(tasks))) as pool:
                for model_name, idx, slot in pool.map(lambda t: _grade_one(*t), tasks):
                    per_sample[model_name][idx] = slot

        # 4) Aggregate across samples per model.
        models_payload = [
            aggregate_samples(m, sampled[m]["samples"], sampled[m]["errors"], per_sample[m], checklist)
            for m in models
        ]

        yield (
            "done",
            {
                "title": title,
                "mode": "scoring",
                "checklist": checklist,
                "council": judges,
                "council_unavailable": resolved.get("unavailable", []),
                "council_excluded": resolved.get("excluded", []),
                "models": models_payload,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("grade failed")
        yield ("error", {"error": f"{type(exc).__name__}: {exc}"})


def score(
    prompt: str,
    models: List[str],
    *,
    title: Optional[str] = None,
    samples: Optional[int] = None,
    council: Optional[List[str]] = None,
    backup: Optional[str] = None,
    available: Optional[List[str]] = None,
    rng: Optional[random.Random] = None,
    invoke_factory: Optional[JudgeInvokeFactory] = None,
) -> Iterator[Event]:
    """Scoring mode (single stateless call): generate the checklist automatically,
    then grade it. Yields ``checklist`` → (grade's) ``outputs`` → ``scoring`` →
    ``done``, or ``error``. There is no human review step — the checklist is not
    editable; to change a requirement, edit the prompt."""
    try:
        checklist = generate_checklist(prompt)
    except Exception as exc:  # noqa: BLE001 — surface a clean error event
        logger.exception("checklist generation failed")
        yield ("error", {"error": f"{type(exc).__name__}: {exc}"})
        return

    yield ("checklist", {"checklist": checklist})
    yield from grade(
        prompt, models, checklist,
        title=title, samples=samples, council=council, backup=backup,
        available=available, rng=rng, invoke_factory=invoke_factory,
    )
