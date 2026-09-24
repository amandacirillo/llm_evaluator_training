"""Criterion provenance: locate each criterion's source quote in the prompt.

The app — never the model — computes character offsets, by finding the model's
``source_quote`` inside the prompt text the UI actually renders. This is the
grounding gate: a non-implicit criterion whose quote cannot be found is ungrounded
and must be regenerated (and, if it still can't be grounded after the bounded
retries, is demoted to implicit — kept but with no highlight) so the UI never
highlights a span that doesn't exist.

Matching is whitespace-flexible (a run of whitespace in the quote matches any run
of whitespace in the prompt) and **typography-tolerant**: before matching, both the
prompt and the quote are normalized char-for-char so that typographic Unicode maps
to its ASCII equivalent (the hyphen family and smart quotes → ``-`` / ``"`` / ``'``,
non-breaking/narrow spaces → space). The normalization is length-preserving, so the
returned offsets are still valid indices into the *raw* prompt. This matters because
LLMs routinely copy a quote but rewrite the prompt's fancy dashes/quotes as ASCII,
which would otherwise never be found verbatim. Multiple matches are returned in full.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

Span = List[int]  # [start, end) offsets into the raw prompt

# Length-preserving typography folding: each key maps to a single ASCII char, so a
# normalized string has the same length as the original and offsets line up 1:1.
_TYPOGRAPHY = {
    # hyphen / dash family → "-"
    0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-", 0x2014: "-", 0x2015: "-",
    0x2212: "-", 0x00AD: "-",
    # double smart quotes → '"'
    0x201C: '"', 0x201D: '"',
    # single smart quotes / apostrophes → "'"
    0x2018: "'", 0x2019: "'",
    # non-breaking / narrow / thin / figure spaces → " "
    0x00A0: " ", 0x2007: " ", 0x2009: " ", 0x202F: " ",
}


def _fold_typography(s: str) -> str:
    """Fold typographic Unicode to ASCII, preserving length (offset-safe)."""
    return s.translate(_TYPOGRAPHY)


def find_quote(prompt: str, quote: str) -> List[Span]:
    """Return [start, end) offsets of every (whitespace-flexible, typography-tolerant)
    match of ``quote`` in ``prompt``.

    Empty list means the quote is not present (ungrounded). An empty/blank quote
    yields an empty list. Offsets index the raw ``prompt`` (folding is length-safe).
    """
    if not prompt or not quote or not quote.strip():
        return []

    folded_prompt = _fold_typography(prompt)
    folded_quote = _fold_typography(quote)
    tokens = re.split(r"\s+", folded_quote.strip())
    pattern = r"\s+".join(re.escape(tok) for tok in tokens)
    return [[m.start(), m.end()] for m in re.finditer(pattern, folded_prompt)]


def ground_checklist(
    prompt: str, checklist: List[dict]
) -> Tuple[List[dict], List[dict]]:
    """Attach ``spans`` to each criterion and split grounded from ungrounded.

    - Implicit criteria (``source == "implicit"``) are always grounded, with
      ``source_quote == ""`` and ``spans == []`` (they highlight nothing).
    - Non-implicit criteria are grounded only if their ``source_quote`` is found
      verbatim; the located offsets become ``spans``.
    - Non-implicit criteria whose quote is not found are returned in the second
      list (ungrounded) for the caller's grounding gate to regenerate, then demote
      to implicit if still unfound after the retry cap.

    Returns ``(grounded, ungrounded)``.
    """
    grounded: List[dict] = []
    ungrounded: List[dict] = []

    for item in checklist:
        source = str(item.get("source", "")).strip().lower()
        if source == "implicit":
            grounded.append({**item, "source": "implicit", "source_quote": "", "spans": []})
            continue

        quote = str(item.get("source_quote", "") or "")
        spans = find_quote(prompt, quote)
        if spans:
            grounded.append({**item, "source": "quote", "source_quote": quote, "spans": spans})
        else:
            ungrounded.append(item)

    return grounded, ungrounded
