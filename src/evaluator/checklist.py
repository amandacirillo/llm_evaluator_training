"""Two-pass checklist generation (maker -> critic) + grounding gate.

A maker pass drafts binary PASS/FAIL criteria from the prompt; a critic pass
refines them (de-ambiguate, split non-atomic items, strip example-leakage) and
assigns each criterion a grading route (auto/judged), a frozen pass/fail rubric,
and a source (a verbatim prompt quote or "implicit"). Criteria are not labeled by
priority — every requirement comes from the prompt and is in scope.

The app then grounds every non-implicit criterion by locating its source_quote in
the prompt (never trusting model-reported offsets). Any non-implicit criterion
whose quote can't be found is ungrounded and triggers regeneration, bounded to a
few attempts; still-ungrounded criteria are dropped so the UI never highlights a
span that doesn't exist.

There is NO caching — every prompt regenerates its checklist (see SPECS.md).
"""

from __future__ import annotations

import json
import logging
from typing import Callable, List, Optional

from .autocheck import CHECK_KINDS
from .llm import get_llm, judge_model_name, parse_json_response
from .prompts import CHECKLIST_CRITIC_PROMPT, CHECKLIST_MAKER_PROMPT
from .provenance import ground_checklist

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3

# An invoke is a callable taking a prompt string and returning the raw LLM text.
Invoke = Callable[[str], str]


def _llm_invoke(prompt: str) -> str:
    llm = get_llm(model=judge_model_name(), temperature=0.0, json_mode=True)
    response = llm.invoke(prompt)
    return response.content if isinstance(response.content, str) else str(response.content)


def _normalize(raw_items: List[dict]) -> List[dict]:
    """Coerce critic output into clean criteria (ids assigned later).

    Downgrades tag=auto to judged unless it carries a known check kind, so an
    unsupported auto check can never reach the deterministic checker.
    """
    checklist: List[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue

        tag = str(item.get("tag", "judged")).lower().strip()
        check = item.get("check") if isinstance(item.get("check"), dict) else None
        if tag == "auto" and check and str(check.get("kind", "")).strip() in CHECK_KINDS:
            tag = "auto"
        else:
            tag = "judged"
            check = None

        source = str(item.get("source", "quote")).lower().strip()
        if source != "implicit":
            source = "quote"

        criterion = {
            "text": text,
            "tag": tag,
            "pass_means": str(item.get("pass_means", "")).strip(),
            "fail_means": str(item.get("fail_means", "")).strip(),
            "source": source,
            "source_quote": "" if source == "implicit" else str(item.get("source_quote", "") or ""),
        }
        if check is not None:
            criterion["check"] = {
                "kind": str(check["kind"]).strip(),
                **({"expected": check["expected"]} if "expected" in check else {}),
            }
        checklist.append(criterion)
    return checklist


def _assign_ids(checklist: List[dict]) -> List[dict]:
    return [{**c, "id": f"r{i}"} for i, c in enumerate(checklist, start=1)]


def _one_attempt(prompt: str, maker: Invoke, critic: Invoke) -> List[dict]:
    """Run maker -> critic -> normalize for a single attempt."""
    maker_raw = maker(CHECKLIST_MAKER_PROMPT.format(prompt=prompt))
    draft = parse_json_response(maker_raw, fallback={}).get("checklist", [])

    critic_raw = critic(
        CHECKLIST_CRITIC_PROMPT.format(prompt=prompt, draft=json.dumps({"checklist": draft}))
    )
    refined = parse_json_response(critic_raw, fallback={}).get("checklist", [])
    # If the critic returned nothing usable, fall back to the maker's draft so a
    # single flaky pass doesn't wipe the checklist.
    normalized = _normalize(refined) or _normalize(draft)
    return normalized


def generate_checklist(
    prompt: str,
    *,
    model: Optional[str] = None,  # retained for signature compat; model comes from config
    maker_invoke: Optional[Invoke] = None,
    critic_invoke: Optional[Invoke] = None,
    max_attempts: int = _MAX_ATTEMPTS,
) -> List[dict]:
    """Generate a grounded checklist for `prompt`.

    Runs maker->critic, grounds every non-implicit criterion against the prompt,
    and regenerates (bounded) while any criterion is ungrounded. After the last
    attempt, any still-ungrounded criterion is **demoted to implicit** (kept and
    graded, just with no prompt highlight) rather than dropped — so a prompt whose
    quotes can't be located (e.g. the model rewrote the prompt's typography) still
    yields a checklist. Raises ValueError only if the model produced no criteria at
    all.

    `maker_invoke`/`critic_invoke` let tests inject fake LLMs (each takes the
    formatted prompt and returns raw JSON text).
    """
    maker = maker_invoke or _llm_invoke
    critic = critic_invoke or _llm_invoke

    grounded: List[dict] = []
    ungrounded: List[dict] = []
    for attempt in range(1, max_attempts + 1):
        normalized = _one_attempt(prompt, maker, critic)
        grounded, ungrounded = ground_checklist(prompt, normalized)
        if not ungrounded:
            logger.info("Checklist grounded on attempt %d (%d items)", attempt, len(grounded))
            break
        logger.info(
            "Attempt %d: %d ungrounded criterion(s); regenerating", attempt, len(ungrounded)
        )
    else:
        if ungrounded:
            logger.warning(
                "Grounding gate: demoting %d ungrounded criterion(s) to implicit after "
                "%d attempts; unlocated quotes: %s",
                len(ungrounded),
                max_attempts,
                [((u.get("source_quote") or "")[:40]) for u in ungrounded],
            )
            grounded = grounded + [_demote_to_implicit(u) for u in ungrounded]

    if not grounded:
        raise ValueError("Checklist generation returned no usable, grounded items")

    return _assign_ids(grounded)


def _demote_to_implicit(item: dict) -> dict:
    """Keep an ungrounded criterion but as implicit (no source quote / highlight)."""
    return {**item, "source": "implicit", "source_quote": "", "spans": []}
