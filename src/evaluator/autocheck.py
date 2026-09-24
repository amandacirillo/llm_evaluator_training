"""Deterministic auto-checks for structural/format criteria — no LLM.

An ``auto`` criterion carries a ``check`` descriptor ({"kind": ..., params}). We
parse the model's item output into a normalized structure and evaluate the check
in pure Python, so the same output text always yields the same verdict (this is
the determinism guarantee the spec pins with a test).

Two output shapes are understood, best-effort:
  * JSON — a top-level list of items, or a dict with a list under a common key
    ("questions"/"items"/"mcqs"), each item carrying a stem, options, and the
    correct key(s).
  * Numbered text — "1. <stem>" blocks with "A) <option>" lines and an
    "Answer: B" (or "Correct: A, C") line.

When the output cannot be parsed into items, structural checks FAIL with a clear
note rather than raising — the verdict stays deterministic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Fixed registry — the critic may only assign these kinds; anything else is
# treated as "judged" upstream and should never reach run_auto_check.
CHECK_KINDS = frozenset(
    {
        "question_count",
        "option_count",
        "key_count",
        "no_duplicate_options",
        "stem_present",
        "schema_valid",
    }
)


@dataclass
class Item:
    stem: str = ""
    options: List[str] = field(default_factory=list)
    keys: List[int] = field(default_factory=list)  # indices into options


# ---------------------------------------------------------------------------
# Parsing (pure, deterministic)
# ---------------------------------------------------------------------------

def _loads_json(text: str) -> Optional[Any]:
    """json.loads tolerating a single ```json code fence. None on failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
    return None


_ITEM_LIST_KEYS = ("questions", "items", "mcqs", "questions_list", "data")
_STEM_KEYS = ("stem", "question", "prompt", "text", "q")
_OPTION_KEYS = ("options", "choices", "answers_options", "distractors_plus_key")
_OPTION_TEXT_KEYS = ("text", "label", "option", "value", "content")
_CORRECT_FLAG_KEYS = ("correct", "is_correct", "isCorrect", "key")
_ANSWER_KEYS = ("answer", "answers", "correct", "correct_answer", "key", "keys", "correct_options")


def _letter_to_index(token: Any) -> Optional[int]:
    """Map 'A'/'a'/'B'.. to 0/0/1.., or an int-like to itself. None otherwise."""
    if isinstance(token, bool):
        return None
    if isinstance(token, int):
        return token
    if isinstance(token, str):
        t = token.strip()
        if len(t) == 1 and t.isalpha():
            return ord(t.upper()) - ord("A")
        if t.isdigit():
            return int(t)
    return None


def _extract_keys(raw_item: dict, options: List[str]) -> List[int]:
    """Correct-option indices, from option 'correct' flags or an answer field."""
    # 1) options that carry their own correctness flag
    flagged: List[int] = []
    src_opts = None
    for k in _OPTION_KEYS:
        if isinstance(raw_item.get(k), list):
            src_opts = raw_item[k]
            break
    if src_opts is not None:
        for i, opt in enumerate(src_opts):
            if isinstance(opt, dict) and any(bool(opt.get(fk)) for fk in _CORRECT_FLAG_KEYS):
                flagged.append(i)
    if flagged:
        return sorted(set(flagged))

    # 2) an explicit answer field (letter(s), index(es), or option text)
    for k in _ANSWER_KEYS:
        if k not in raw_item:
            continue
        val = raw_item[k]
        tokens = val if isinstance(val, list) else [val]
        idxs: List[int] = []
        for tok in tokens:
            idx = _letter_to_index(tok)
            if idx is None and isinstance(tok, str) and tok in options:
                idx = options.index(tok)
            if idx is not None and 0 <= idx < len(options):
                idxs.append(idx)
        if idxs:
            return sorted(set(idxs))
    return []


def _option_text(opt: Any) -> str:
    if isinstance(opt, str):
        return opt.strip()
    if isinstance(opt, dict):
        for k in _OPTION_TEXT_KEYS:
            if isinstance(opt.get(k), str):
                return opt[k].strip()
    return ""


def _parse_json_items(data: Any) -> List[Item]:
    if isinstance(data, dict):
        seq = None
        for k in _ITEM_LIST_KEYS:
            if isinstance(data.get(k), list):
                seq = data[k]
                break
        if seq is None:
            # A single item dict?
            if any(k in data for k in _STEM_KEYS):
                seq = [data]
            else:
                return []
    elif isinstance(data, list):
        seq = data
    else:
        return []

    items: List[Item] = []
    for raw in seq:
        if not isinstance(raw, dict):
            return []  # not an item structure
        stem = ""
        for k in _STEM_KEYS:
            if isinstance(raw.get(k), str):
                stem = raw[k].strip()
                break
        options: List[str] = []
        for k in _OPTION_KEYS:
            if isinstance(raw.get(k), list):
                options = [_option_text(o) for o in raw[k]]
                break
        keys = _extract_keys(raw, options)
        items.append(Item(stem=stem, options=options, keys=keys))
    return items


# Question header: optional markdown heading/emphasis/bullet, optional
# "Question"/"Q" keyword, a number, optional . ) : — e.g. "1.", "1)",
# "### Question 3", "**Q2.**", "Question 1". Accepted when the keyword OR the
# punctuation is present (a bare "12 monkeys" line is not a question header).
_Q_LINE = re.compile(
    r"^\s*(?:#{1,6}\s*)?[*_>\s]*(?P<kw>question|q)?\s*(?P<num>\d+)\s*(?P<punct>[.):])?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
# Option line: optional bullet/emphasis/paren, a single letter, then . ) or : —
# e.g. "A)", "A.", "(A)", "- A)", "* **B.**", "a) ".
_OPT_LINE = re.compile(
    r"^\s*(?:[-*+]\s*)?[*_(\[\s]*([A-Ha-h])[*_)\].:]+\s+(.*)$"
)
# Answer line: optional emphasis, one of several labels, a separator, then value(s).
_ANS_LINE = re.compile(
    r"^\s*[*_>\s]*(?:answer\s*key|correct\s*answer|correct\s*option|answer|correct|key|ans)"
    r"[*_\s]*[:\-–]\s*(.+)$",
    re.IGNORECASE,
)


def _clean_value(text: str) -> str:
    """Strip surrounding markdown emphasis/space from a captured value."""
    return text.strip().strip("*_ ").strip()


def _parse_text_items(text: str) -> List[Item]:
    items: List[Item] = []
    current: Optional[Item] = None
    for line in text.splitlines():
        ans = _ANS_LINE.match(line)
        if ans and current is not None and current.options:
            for tok in re.split(r"[,\s/]+", _clean_value(ans.group(1))):
                idx = _letter_to_index(tok.strip("*_().:"))
                if idx is not None and 0 <= idx < len(current.options):
                    current.keys.append(idx)
            current.keys = sorted(set(current.keys))
            continue
        opt = _OPT_LINE.match(line)
        if opt and current is not None:
            current.options.append(_clean_value(opt.group(2)))
            continue
        q = _Q_LINE.match(line)
        if q and (q.group("kw") or q.group("punct")):
            current = Item(stem=_clean_value(q.group("rest")))
            items.append(current)
            continue
        # A continuation line before any option is treated as more of the stem
        # (stems that wrap across lines).
        stripped = line.strip()
        if current is not None and stripped and not current.options:
            current.stem = (current.stem + " " + _clean_value(stripped)).strip()
    return items


def parse_items(output_text: str) -> List[Item]:
    """Parse model output into normalized items (JSON first, then numbered text)."""
    if not output_text or not output_text.strip():
        return []
    data = _loads_json(output_text)
    if data is not None:
        items = _parse_json_items(data)
        if items:
            return items
    return _parse_text_items(output_text)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def _fail(note: str) -> Dict[str, str]:
    return {"verdict": "FAIL", "note": note}


def _pass() -> Dict[str, str]:
    return {"verdict": "PASS", "note": ""}


def _unverifiable(note: str) -> Dict[str, str]:
    # The deterministic parser couldn't handle this output — defer to the judge
    # council rather than emit a spurious FAIL.
    return {"verdict": "UNVERIFIABLE", "note": note}


def run_auto_check(check: Dict[str, Any], output_text: str) -> Dict[str, str]:
    """Evaluate one auto-check against an output. Pure + deterministic.

    Returns {"verdict": "PASS"|"FAIL"|"UNVERIFIABLE", "note": str}. UNVERIFIABLE
    means the parser couldn't parse the output; the pipeline then routes that
    criterion to the judge council for that output.
    """
    kind = str((check or {}).get("kind", "")).strip()
    if kind not in CHECK_KINDS:
        return _unverifiable(f"unsupported auto-check kind {kind!r}")

    items = parse_items(output_text)

    if not items:
        return _unverifiable("could not parse any items from the output")

    if kind == "schema_valid":
        # Parsed but malformed items are a genuine FAIL; no items at all was
        # already handled as UNVERIFIABLE above.
        if any(not it.stem or not it.options for it in items):
            return _fail("output did not parse into well-formed items")
        return _pass()

    if kind == "question_count":
        expected = check.get("expected")
        if not isinstance(expected, int):
            return _fail("question_count check missing integer 'expected'")
        return _pass() if len(items) == expected else _fail(
            f"found {len(items)} questions, expected {expected}"
        )

    if kind == "option_count":
        expected = check.get("expected")
        if not isinstance(expected, int):
            return _fail("option_count check missing integer 'expected'")
        bad = [i + 1 for i, it in enumerate(items) if len(it.options) != expected]
        return _pass() if not bad else _fail(
            f"question(s) {bad} do not have exactly {expected} options"
        )

    if kind == "key_count":
        expected = check.get("expected")
        if not isinstance(expected, int):
            return _fail("key_count check missing integer 'expected'")
        bad = [i + 1 for i, it in enumerate(items) if len(it.keys) != expected]
        return _pass() if not bad else _fail(
            f"question(s) {bad} do not mark exactly {expected} correct key(s)"
        )

    if kind == "no_duplicate_options":
        for i, it in enumerate(items):
            norm = [o.strip().lower() for o in it.options]
            if len(norm) != len(set(norm)):
                return _fail(f"question {i + 1} has duplicate options")
        return _pass()

    if kind == "stem_present":
        bad = [i + 1 for i, it in enumerate(items) if not it.stem.strip()]
        return _pass() if not bad else _fail(f"question(s) {bad} have no stem")

    return _fail(f"could not auto-verify: unsupported check kind {kind!r}")
