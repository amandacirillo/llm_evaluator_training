"""Judge prompts, mined from the Dify export and adapted.

- CHECKLIST_MAKER_PROMPT — drafts binary PASS/FAIL criteria from the prompt, each
  tagged with a verbatim source_quote (or marked implicit).
- CHECKLIST_CRITIC_PROMPT — refines the draft: de-ambiguates, splits non-atomic
  items, strips example-leakage, assigns auto/judged + a frozen rubric, and
  repairs source quotes.
- CHECKLIST_SCORER_PROMPT — from Dify node_checklist_scorer, adapted to strict
  PASS/FAIL (no PARTIAL) and structured JSON keyed by blinded output labels.

All return JSON so the pipeline can build a structured result. Criteria are NOT
labeled by priority — every requirement comes from the prompt and is in scope.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Checklist maker (pass 1)
# ---------------------------------------------------------------------------

CHECKLIST_MAKER_PROMPT = """\
You are an expert prompt engineer. Read the PROMPT below and DRAFT a thorough, \
granular checklist of binary PASS/FAIL criteria that will be used to evaluate \
whether an AI model's response fully followed the prompt AND is actually correct.

CRITICAL RULES:

1. REQUIREMENTS vs EXAMPLES — The prompt may contain example items or sample \
content to illustrate what is wanted. NEVER extract a requirement from the \
specific content of an example (e.g. do not write "the correct answer is C" just \
because a sample's answer was C). Examples show format and style, not rules.

2. GRANULARITY — One checklist item per distinct requirement. Do not merge \
multiple requirements into one item.

3. SPECIFICITY — Every item is a short, testable one-line statement a human can \
mark PASS or FAIL just by reading the response.

4. COMPLETENESS — cover BOTH explicit requirements (count, format, topic, \
constraints, labeling, ordering) AND implicit correctness/format requirements a \
correct response must meet even if unstated (e.g. "the marked answer is actually \
correct", "each distractor is plausible but unambiguously wrong", "no factual \
errors", exact counts, required labels present).

5. PROVENANCE — For EACH item, set "source_quote" to a SHORT, VERBATIM substring \
copied EXACTLY from the PROMPT that the item is derived from (copy the characters \
as they appear — do not paraphrase). If the item is an implicit correctness/quality \
rule not tied to any specific words in the prompt, set "source" to "implicit" and \
"source_quote" to "". Do NOT report character offsets — only the quote text.

6. NO PADDING — include only criteria that genuinely determine correctness. \
Typically 6–15 items. Do NOT label items by priority — every requirement comes \
from the prompt and is in scope.

OUTPUT — return ONLY a JSON object in exactly this shape:

{{
  "checklist": [
    {{ "text": "<requirement>", "source": "quote", "source_quote": "<verbatim substring>" }},
    {{ "text": "<implicit correctness rule>", "source": "implicit", "source_quote": "" }}
  ]
}}

PROMPT TO ANALYZE:
{prompt}
"""


# ---------------------------------------------------------------------------
# Checklist critic (pass 2)
# ---------------------------------------------------------------------------

CHECKLIST_CRITIC_PROMPT = """\
You are a strict reviewer refining a DRAFT checklist for evaluating responses to \
the PROMPT. Improve the draft — do not merely echo it.

REFINE:
1. DE-AMBIGUATE — reword any vague item into a precise, testable statement.
2. SPLIT — break any non-atomic item (covering >1 requirement) into separate items.
3. STRIP EXAMPLE-LEAKAGE — delete any item derived from the content of an example \
in the prompt rather than from an actual rule.

For EACH final criterion, decide how it will be graded:
- "tag": "auto" ONLY if it can be checked mechanically by exactly one of these \
kinds — question_count, option_count, key_count, no_duplicate_options, \
stem_present, schema_valid — in which case include a "check" object. Otherwise \
"tag": "judged" and omit "check".
  * question_count / option_count / key_count take an integer "expected".
    (key_count: 1 = single-select, >=2 = multi-select.)
  * no_duplicate_options / stem_present / schema_valid take no params.
- "pass_means" and "fail_means": a frozen one-line rubric for the PASS and FAIL \
conditions (this rubric is shown to graders and must not change later).
- "source"/"source_quote": keep a VERBATIM substring of the PROMPT the item comes \
from, repairing it if the draft's quote is not an exact substring; or set \
"source": "implicit" with "source_quote": "" for implicit correctness rules. Do \
NOT report offsets.

OUTPUT — return ONLY a JSON object in exactly this shape:

{{
  "checklist": [
    {{ "text": "Each question has exactly 4 options.",
       "tag": "auto", "check": {{ "kind": "option_count", "expected": 4 }},
       "pass_means": "Every question lists exactly four options.",
       "fail_means": "Any question has more or fewer than four options.",
       "source": "quote", "source_quote": "4 options" }},
    {{ "text": "The marked answer for each item is actually correct.",
       "tag": "judged",
       "pass_means": "Every marked key is the correct answer.",
       "fail_means": "Any marked key is wrong.",
       "source": "implicit", "source_quote": "" }}
  ]
}}

PROMPT:
{prompt}

DRAFT CHECKLIST (JSON):
{draft}
"""


# ---------------------------------------------------------------------------
# Checklist scorer (blinded)
# ---------------------------------------------------------------------------

CHECKLIST_SCORER_PROMPT = """\
You are an impartial evaluator. Score the SINGLE response labeled OUTPUT below \
against every item in the CHECKLIST. You do NOT know which model produced this \
response, and you must not guess or comment on it. Judge only what THIS response's \
text actually does.

SCORING RULES:
- Score every checklist item.
- PASS = the response clearly and fully satisfies the item across the whole \
response.
- FAIL = it does not satisfy the item, only partially satisfies it, or satisfies \
it inconsistently. There is no partial credit — when in doubt, FAIL.
- Score each item independently. Passing one item must not influence another.
- Base EVERY verdict ONLY on text that is actually present in OUTPUT. Do NOT \
invent, assume, or infer details that are not written. Read carefully before \
judging — e.g. do not claim an option is the longest/shortest without checking the \
actual text. If you cannot find supporting evidence in OUTPUT, it is a FAIL.
- Every item carries a "note". For a FAIL, the note is ONE short sentence that \
QUOTES or points to the exact part of OUTPUT that fails, so the user can verify \
it. For a PASS, the note is an empty string "".

OUTPUT FORMAT — return ONLY a JSON object, no preamble, in exactly this shape:

{{
  "items": [
    {{ "id": "r1", "verdict": "PASS", "note": "" }},
    {{ "id": "r2", "verdict": "FAIL", "note": "Only 4 questions are present (Q1–Q4); the prompt requires 5." }}
  ]
}}

Include a verdict for every checklist id. Use only "PASS" or "FAIL" — never \
"PARTIAL" or "N/A".

========================
CHECKLIST:
{checklist}

========================
OUTPUT:
{output}
"""
