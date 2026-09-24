"""Judge council: resolve the panel for a run, and aggregate its votes.

The council grades only ``judged`` criteria, and only ever sees blinded outputs
(handled in the pipeline). Two responsibilities live here:

* ``resolve_council`` — pick the panel for a specific run. Members the proxy
  doesn't serve are dropped; a lost second claude-sonnet is auto-replaced to keep
  family diversity; and the **self-judging safeguard** drops any judge that is
  also a model under test, substituting the configured backup to keep the council
  odd-sized. If no substitute is available the council may end up even (ties then
  count as low-confidence) or, in the worst case, empty (judged criteria become
  low-confidence).
* ``aggregate_votes`` — majority vote across judges for one criterion, flagging a
  split (non-unanimous, including even-council ties) as low-confidence.
"""

from __future__ import annotations

from typing import Dict, List


def _is_sonnet(model_id: str) -> bool:
    return "claude-sonnet" in model_id.lower()


def resolve_council(
    configured: List[str],
    backup: str,
    models_under_test: List[str],
    available: List[str],
    *,
    fallback: List[str] = None,
) -> Dict[str, object]:
    """Resolve the judge panel for a run.

    Args:
        configured: the default council from config.
        backup: backup judge id for the self-judging safeguard.
        models_under_test: ids of the models being graded this run.
        available: ids the proxy actually serves (canonical casing).
        fallback: ordered extra judge candidates (e.g. the checklist model) tried,
            after `backup`, when the council would otherwise be empty.

    Returns ``{"judges": [...], "notes": [...], "unavailable": [...],
    "excluded": []}``. The council is only ever empty when the proxy serves no
    models at all.
    """
    notes: List[str] = []
    avail_by_lower = {a.lower(): a for a in available}
    fallback = fallback or []
    # `models_under_test` is accepted for signature stability but no longer used:
    # there is no self-judging safeguard — blinding is the sole protection, so a
    # configured judge may also be a model under test.
    _ = models_under_test

    def canon(model_id: str):
        return avail_by_lower.get(model_id.lower())

    def eligible(model_id: str, kept: List[str]):
        """A canonical, available judge not already kept."""
        c = canon(model_id) if model_id else None
        if c is not None and c not in kept:
            return c
        return None

    # 1) Resolve configured members against proxy availability.
    resolved: List[str] = []
    unavailable: List[str] = []  # configured judges the proxy doesn't serve
    for m in configured:
        c = canon(m)
        if c is None:
            notes.append(f"council member {m!r} is not served by the proxy; dropped")
            unavailable.append(m)
        elif c not in resolved:
            resolved.append(c)

    # 2) Preserve claude-sonnet diversity: if a configured sonnet was dropped,
    #    auto-pick another claude-sonnet the proxy serves.
    want_sonnets = min(2, sum(1 for m in configured if _is_sonnet(m)))
    if sum(1 for m in resolved if _is_sonnet(m)) < want_sonnets:
        for a in available:
            if _is_sonnet(a) and a not in resolved:
                resolved.append(a)
                notes.append(f"auto-added second claude-sonnet {a!r} for family diversity")
                break

    # 3) No self-judging safeguard: a configured judge is kept even when it is a
    #    model under test (blinding prevents it from recognizing its own output).
    kept: List[str] = list(resolved)
    excluded: List[str] = []  # retained for payload shape; always empty now

    # 4) Ensure the council is non-empty and (where possible) odd-sized.
    if not kept:
        # Fall back to a single default judge: backup, then the fallback chain
        # (e.g. the checklist model), then any available model.
        for cand in [backup, *fallback]:
            e = eligible(cand, kept)
            if e is not None:
                kept.append(e)
                notes.append(f"council empty; falling back to default judge {e!r}")
                break
        if not kept and available:
            kept.append(available[0])
            notes.append(f"council empty; using available judge {available[0]!r}")
        if not kept:
            notes.append("no judge available (the proxy serves no models)")
    elif len(kept) % 2 == 0:
        # Restore an odd-sized council with the backup judge if a drop made it even.
        b = eligible(backup, kept)
        if b is not None:
            kept.append(b)
            notes.append(f"added backup judge {b!r} to keep an odd-sized council")
        else:
            notes.append(
                "no eligible substitute available; council is even — ties are low-confidence"
            )

    return {"judges": kept, "notes": notes, "unavailable": unavailable, "excluded": excluded}


def aggregate_votes(votes: List[str]) -> Dict[str, object]:
    """Majority verdict across judges for one criterion.

    Returns ``{"verdict": "PASS"|"FAIL", "split": bool, "no_votes": bool}``.
    ``split`` marks genuine disagreement (non-unanimous, incl. an even-council
    tie). **Zero votes is NOT a split** — it returns ``no_votes: True`` (an
    unscored cell), so an empty/failed council never masquerades as "judges
    split." Ties resolve to FAIL ("when in doubt, FAIL").
    """
    normalized = [str(v).upper() for v in votes if v]
    if not normalized:
        return {"verdict": "FAIL", "split": False, "no_votes": True}

    passes = normalized.count("PASS")
    fails = len(normalized) - passes
    verdict = "PASS" if passes > fails else "FAIL"
    split = passes > 0 and fails > 0
    return {"verdict": verdict, "split": split, "no_votes": False}
