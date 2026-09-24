# SPECS.md — LLM Evaluator / Model-Comparison & Scoring Tool

> **Status:** Stable baseline — on `feat/model-evaluator-v2`, not yet merged.
> **Last aligned:** 2026-07-14.
> **Owners:** Jonathan Han (eng) · \<product\>
> **What this file is:** The single source of truth for what this tool does and
> why. Code changes must match what is written here. **When code and SPECS
> diverge, update SPECS first, then change code to match.** This is the first
> thing to read after [`AGENTS.md`](AGENTS.md); the per-feature human doc is
> [`docs/model-evaluator.md`](docs/model-evaluator.md).

---

## Table of contents

1. [Context](#1-context)
2. [Goal](#2-goal)
3. [Scope](#3-scope)
4. [Constraints](#4-constraints)
5. [Prior decisions](#5-prior-decisions)
6. [Design / behavior](#6-design--behavior)
7. [API / contract](#7-api--contract)
   - [Project structure](#project-structure) (file layout)
8. [Task breakdown](#8-task-breakdown)
9. [Verification criteria](#9-verification-criteria)
10. [Future considerations](#10-future-considerations)

---

## 1. Context

**Problem.** Picking which AI model to use for an item-generation prompt
is guesswork. Users eyeball one model's output and move on, with no objective,
side-by-side basis for comparison, and no evidence of how well each output actually
met the prompt's requirements.

**What this tool does.** It sends one prompt (multiple-choice / multiple-select item
generation) to 1–3 models, derives a PASS/FAIL checklist from the prompt, blind-
grades each model's output against that checklist with a council of LLM judges, and
shows a per-criterion results grid plus a per-model run-consistency chart — so a user
can make an **evidence-based** decision about which model fits their prompt.

**Origin.** A Dify-hosted prototype ("Multi-Model Prompt Comparison") proved the
idea. This repo re-implements it cleanly. Three Dify nodes are intentionally
**dropped**: the Dimension Scorer (subjective 1–10 scores), the Summary &
Recommendations node, and the Token/Cost Estimator.

**Affected users.** Prompt developers and content teams deciding which model to
standardize on for a given prompt or task type.

> **The tool must NEVER declare a winner itself.** It surfaces per-criterion
> verdicts, pass rates, and run consistency — the human decides.

---

## 2. Goal

> **A two-mode web app that runs one prompt against up to three models concurrently,
> shows their outputs side by side, and — in scoring mode — grades each output
> PASS/FAIL against an automatically generated, prompt-specific requirements
> checklist, so the user can decide which model to use. No winner, ranking, or
> recommendation is ever produced.**

The two modes:

- **Output comparison only** — generate and show each model's output side by side;
  no checklist, no scoring.
- **Output comparison + evaluation scoring** — the full pipeline: automatic checklist
  generation, N-sample generation per model, split grading (deterministic auto-checks
  + a blinded judge council), and a results grid with run-consistency.

---

## 3. Scope

### In scope
- Input-page **mode toggle** (output-only vs scoring), each option with an info (ⓘ)
  tooltip explaining what it does.
- **Automatic** two-pass (maker→critic) checklist generation with per-criterion `tag`
  (auto/judged), frozen `pass_means`/`fail_means` rubric, `source`, `source_quote`,
  and app-computed `spans`. **No human review/edit step; no `priority` field.**
- **Grounding gate** with bounded regeneration (3 attempts); multi-match handling.
- **Multi-sampling** — each model is run **N times** (default 5, from
  `config/evaluator.json`).
- **Split grading**: deterministic auto-checks (falling back to the council when an
  output can't be parsed) + a **blinded judge council** grading **one identity-
  stripped output at a time**, majority vote.
- **Aggregation** across samples; a per-model **run-consistency** chart.
- **Criterion→prompt provenance**: click a requirement to highlight the exact prompt
  text it came from in the side panel.
- All model / sampling / temperature config in `config/evaluator.json`; `.env` holds
  only `LITELLM_API_KEY` + `LITELLM_API_BASE`.
- No checklist cache; every prompt regenerates.

### Out of scope
- Cost / token / latency display anywhere (explicitly excluded, not deferred).
- Persistence, run history, export, auth/SSO, more than three models.
- Any subjective 1–10 quality/format score.
- Any item-type classification step (`tag` is a grading route, not an item-type
  classifier).
- **Any winner / ranking / recommendation output** — enforced by test.

---

## 4. Constraints

- **Blinding is non-negotiable.** Each judge grades **one identity-stripped output at
  a time** (labeled just "OUTPUT", no model name) and is told not to guess whose it
  is. No model identity may appear in any judge prompt. Grading one output per prompt
  also removes cross-output anchoring.
- **Determinism** for auto-checks: identical output text → identical verdict on
  repeat (pure Python, no LLM).
- **Statelessness:** the server holds no cross-request state (Gunicorn runs multiple
  workers). Each request is self-contained.
- **Temperature:** judges and the maker/critic run at temperature 0 + JSON mode.
  Compared models use `output_temperature` from config (default 0). Proxied LLMs are
  not perfectly deterministic even at 0 — run-to-run score drift is expected and is
  exactly what run-consistency measures.
- **Bounded loops:** checklist regeneration for grounding is capped at 3 attempts;
  ungrounded non-implicit criteria are dropped, never shipped.
- **The gateway key stays server-side.** `LITELLM_API_KEY` never reaches the browser.
- **Tech stack:** Python 3.11+ backend, React 18 + Vite 5 + TypeScript + Tailwind 3
  frontend (see §4-detail in Design). No new runtime dependency without review.
- **No winner** — enforced by `tests/test_no_winner.py`.

---

## 5. Prior decisions

Choices already made, recorded so they aren't relitigated:

1. **Blinding is the core bias mitigation** — kept and strengthened to per-output
   grading. There is **no separate self-judging safeguard**: a configured judge is
   used even when it is also a model under test, because blinding (identity-stripped,
   single-output grading) prevents a judge from recognizing its own output. The user
   accepted the residual self-preference risk in exchange for a stable 3-judge council.
2. **Pass/fail only** — no subjective 1–10 scores.
3. **The checklist is generated automatically** — no human review/edit step. To change
   a requirement, edit the prompt. (Reversed from an earlier v2 design that had a
   review step.)
4. **No caching** — every prompt regenerates its checklist (maker→critic).
5. **A judge council with majority vote** replaces the original single judge; a council
   split is recorded as low-confidence (computed, not surfaced as a UI marker).
6. **N-sample generation + aggregation** replaces single-run scoring.
7. **Model / sampling / temperature config lives in `config/evaluator.json`**, not env
   vars. `.env` holds only the two `LITELLM_*` values.
8. **Council members and N are config-only** — no input-page controls. Council is
   resolved against the full proxy at runtime; the operator hardcodes exact IDs.
9. **Run-consistency label:** a model is **consistent** when its per-run scores stay
   within **2 points** (`max − min ≤ 2`), else **variable**. (Loosened from ≤ 1.)

---

## 6. Design / behavior

### 6.1 Configuration — `config/evaluator.json`

Committed, non-secret. Loaded by `src/evaluator/config.py` (`load_evaluator_config()`)
with safe defaults if the file is missing.

```json
{
  "checklist_model": "claude-sonnet-4-6",
  "council": ["claude-sonnet-4-6", "gpt-5.4", "gpt-4o"],
  "backup_judge": "gpt-5.4-mini",
  "samples": 5,
  "output_temperature": 0
}
```

- `checklist_model` — model for the maker and critic passes.
- `council` — default judge set, resolved against the proxy at runtime (§6.6).
- `backup_judge` — substitute used to restore an odd-sized council / as an
  empty-council fallback.
- `samples` — N, how many times each model is called in scoring mode (default 5).
- `output_temperature` — temperature for the compared models (default 0).

`.env` / `.env.example` hold **only** `LITELLM_API_KEY` and `LITELLM_API_BASE`.
`llm.py` no longer reads `LITELLM_MODEL`, `LITELLM_MINI_MODEL`, or
`LITELLM_OUTPUT_TEMPERATURE`.

### 6.2 Criterion shape

```jsonc
{
  "id": "r1",
  "text": "Each question has exactly 4 options labeled A, B, C, D.",
  "tag": "auto" | "judged",
  "pass_means": "Every question lists exactly four options labeled A–D.",
  "fail_means": "Any question has ≠4 options or mislabels them.",
  "source": "quote" | "implicit",
  "source_quote": "4 options",          // "" when source == "implicit"
  "spans": [[from, to], ...],           // char offsets into the prompt; [] when implicit
  "check": { "kind": "option_count", "expected": 4 }   // present only when tag == "auto"
}
```

There is **no `priority` field** — every criterion is derived from the prompt and is
equally in scope. `tag` (how it's graded) and `source` (where it came from) are
orthogonal. `spans` are computed by the app (§6.4), never trusted from the model.

### 6.3 Two-pass checklist generation (`checklist.py`, `prompts.py`)

Both passes use `checklist_model`, temperature 0, JSON mode. **No caching.**

1. **Maker** (`CHECKLIST_MAKER_PROMPT`): draft binary, atomic PASS/FAIL criteria from
   the prompt — extract requirements (never example content); cover explicit + implicit
   correctness/format; no padding; for each emit a verbatim `source_quote` or
   `"implicit"`. No priority.
2. **Critic** (`CHECKLIST_CRITIC_PROMPT`): refine — remove ambiguity, split non-atomic
   items, strip example-leakage; assign `tag` (`auto` only when it maps cleanly onto a
   fixed auto-check `kind`, else `judged`) with a `check` descriptor; write frozen
   `pass_means`/`fail_means`; confirm/repair `source_quote` verbatim or mark implicit.
3. **Ground + gate** (`provenance.py`): locate each non-implicit `source_quote` in the
   prompt and set `spans`. Not found → ungrounded → regenerate (bounded to 3 attempts).
   After the cap, any still-ungrounded criterion is **demoted to implicit** (kept, with
   `source:"implicit"`, `source_quote:""`, `spans:[]` — still graded, just no prompt
   highlight), **not dropped**, so a prompt whose quotes can't be located still yields a
   checklist. The generator raises `ValueError` **only** when the model produced **no
   criteria at all** (both maker and critic empty). Implicit criteria get `spans: []`.

### 6.4 Provenance (`provenance.py`)

- `find_quote(prompt, quote) -> list[[from, to]]`: char offsets of **all** occurrences
  (multi-match). Empty list ⇒ ungrounded.
- Matching is **typography-tolerant**: before matching, both the prompt and the quote
  are normalized **char-for-char (length-preserving)** so that typographic Unicode maps
  to its ASCII equivalent — the hyphen family (`‐ ‑ ‒ – — −` → `-`), smart double
  quotes (`“ ”` → `"`), smart single quotes (`‘ ’` → `'`), and non-breaking space
  (→ space). Because normalization preserves length, the returned offsets are still
  valid indices into the **raw** prompt the UI renders (the highlight lands on the
  original characters). Matching stays whitespace-flexible. This prevents the common
  failure where the checklist model copies a quote but normalizes the prompt's fancy
  dashes/quotes to ASCII, so an otherwise-correct quote wouldn't be found verbatim.

### 6.5 Auto-checks (`autocheck.py`)

Pure, deterministic, no LLM. `run_auto_check(check, output_text) -> {"verdict":
"PASS"|"FAIL"|"UNVERIFIABLE", "note": str}`. Fixed registry `CHECK_KINDS`:

| kind | params | passes when |
|---|---|---|
| `question_count` | `expected` | parsed item count == expected |
| `option_count` | `expected` | every item has exactly `expected` options |
| `key_count` | `expected` | every item marks exactly `expected` correct keys |
| `no_duplicate_options` | — | no item repeats an option |
| `stem_present` | — | every item has a non-empty stem |
| `schema_valid` | — | output parses into the expected item structure |

A best-effort deterministic parser extracts items/options/keys from common MCQ/MS text
and JSON shapes. **Fallback, not fail:** when the parser can't parse the output,
`run_auto_check` returns **`UNVERIFIABLE`** (not `FAIL`); the pipeline then routes that
criterion to the judge council for that output (§6.7). Called twice on the same text,
it returns identical results.

### 6.6 Judge council (`council.py`)

- **Availability = the full LiteLLM proxy `/models` list**, not the picker allow-list
  (`config/models.json`). `pipeline._available_models()` uses
  `models.list_all_proxy_models()` (full proxy, `[]` on error → fall back to `council +
  backup + checklist_model` as assumed-available).
- **No self-judging safeguard — blinding is the sole protection.** A configured judge
  is used even when it is also a model under test.
- `resolve_council(configured, backup, models_under_test, available, *, fallback)
  -> {judges, notes, unavailable, excluded}`:
  - Start from `configured` filtered to `available`; auto-pick a second `claude-sonnet-*`
    if a configured one is missing.
  - Do **not** drop under-test judges (`models_under_test` is retained in the signature
    but no longer excludes; `excluded` is always `[]`).
  - If even-sized, add `backup` (available) to restore an odd size.
  - **Never empty:** if the council would be empty, fall back to a single default judge
    (`backup` → `checklist_model` → any available proxy model) and record a note. Only
    return `[]` if the proxy serves nothing.
  - Also returns `unavailable` (configured judges the proxy doesn't serve), surfaced to
    the UI, and `excluded` (kept for payload shape, always `[]`).
- `aggregate_votes(votes) -> {verdict, split, no_votes}`: **majority** verdict per
  criterion; `split == True` when judges aren't unanimous (even-council tie → `FAIL`,
  `split = True`). **Zero votes** → `{FAIL, split: False, no_votes: True}` — an unscored
  cell is **not** a split.

### 6.7 Grading a scoring run (`pipeline.py`)

`score(prompt, models, ...)` generates the checklist (§6.3) then delegates to `grade()`.

1. **Sample.** Call each model **N** times at `output_temperature` (via
   `ThreadPoolExecutor`). Collect up to N successful outputs per model; tolerate ragged
   counts.
2. **Resolve council** (§6.6).
3. **Grade each output independently — one output per judge prompt.** For every
   `(model, sample)`:
   - **Auto criteria:** `run_auto_check` on that output; a PASS/FAIL is the deterministic
     verdict; an `UNVERIFIABLE` result routes that criterion to the council.
   - **Council:** send **only this one identity-stripped output** (labeled "OUTPUT") plus
     the judged ∪ unverifiable-auto criteria to each judge (`council_grade_output`);
     `aggregate_votes` → per-criterion `verdict`/`split`/`no_votes`. FAIL notes quote the
     exact failing text. Each judge invoke is isolated (a failing judge = no vote, logged).
   - The `(model, sample)` tasks run in parallel.
4. **Aggregate across samples** per (model, criterion): `verdict` = majority of per-sample
   verdicts (tie → FAIL); `low_confidence` = council split on ≥ half the samples (computed
   for data completeness; **not** shown as a UI marker); a predominantly `no_votes` cell
   carries `no_votes: true` and a "No judge was available to score this" note.
5. **Per-model summary** (`sampling`): `generated` (successful samples), `graded`
   (== generated), `total_criteria`, the per-sample **`scores`** array (PASS count per
   sample — the dots of the run-consistency chart), and `avg_score`/`min_score`/
   `max_score`/`stdev`.
6. **Headline:** `pass_count` = # criteria whose aggregated verdict is PASS; `total` =
   len(checklist); `pass_pct = round(100 * pass_count / total)`.

Pure helpers (`aggregate_samples`, `aggregate_votes`, `resolve_council`, `run_auto_check`,
`council_grade_output`) are LLM-free and unit-tested with injected fakes.

### 6.8 Output-only run (`pipeline.py`)

`generate()` calls each model **once**, returns `{model, output, error}` per model. No
checklist, no sampling, no scoring.

### 6.9 UI behavior (`demo/ui/`)

**Input page.**
- **Mode toggle** — output-only vs scoring; each option has an info (ⓘ) tooltip phrased
  as guidance. The prompt textarea fills the left column height to match the right-hand
  inputs. Scoring-mode submit button reads **"Start evaluation"** (output-only: "Compare
  outputs"). Up to three model pickers (model 1 required); a model chosen in one picker
  is disabled in the others.
- While running, staged progress only ("Building checklist" → "Generating outputs" →
  "Scoring"); no partial results — the full results view appears at once.

**Results page.**
- **Outputs side by side** — up to three markdown columns, one per model; an errored
  model shows its error in place of output.
- **Prompt requirement adherence** — a headline pass-% card per model, then a
  requirement-by-model **✓ / ✗ / –** grid (majority verdict across samples). **No
  auto/judged icons, no low-confidence asterisk.** Hovering a **✗** shows a tooltip with
  the one-line reason that requirement failed. The section description reads: "Each output
  is graded against a checklist derived from the prompt. Pass/fail is determined by three
  AI judge models, and supporting evidence is shown so you can validate the results
  yourself." Caption: "Hover an ✗ to see why that requirement failed, and **click** a
  requirement to see the part of your prompt it came from."
- **Judge-availability notice** — if any configured judge was unavailable, or fewer than
  3 judges were used, a small amber notice appears above the grid ("Heads-up: judge `X`
  couldn't be used — scored with N judges. Update the council in
  `config/evaluator.json`."). Never a ranking.
- **Run consistency** (replaces any summary table) — a per-model **line chart
  (sparkline)** over the N runs. Header is an `<h2>` sized like the other section
  headers, with a brief explanation beneath ("Each AI model is run against the prompt
  **five** times to gauge how consistent it is: steady scores read as consistent, swinging
  scores as variable. Favor a model that's both high-scoring and steady."). Per row: model
  name (left); one **labeled point per run** (x = run 1…N evenly spaced, y = score)
  connected by a line; a horizontal **dashed mean line** with its value labeled; and a
  colored **consistent** (green) / **variable** (amber) label on the right. Line + dots are
  colored by consistency. All scores are labeled always-on (no hover). The chart is wide;
  the shared y-scale fits the observed score range (a minimum span keeps a small, consistent
  spread gentle). **Consistent = `max − min ≤ 2`, else variable** (`consistencyLabel` in
  `lib/beeswarm.ts`). No ranking; rows stay in selection order.

**Provenance — click-to-select** (`DetailsSidebar` renders the prompt as spans):
- Selection is by **click**, not hover. Clicking a requirement row selects it (click again
  or click empty space to deselect); the **selected row is visibly highlighted**.
- Selecting a requirement highlights its `source_quote` in the side panel and smooth-scrolls
  it into view **only when off-screen**. If the panel is **collapsed**, selecting a
  requirement **opens** it and shows the highlight (there is no collapsed-panel popover).
- An **implicit** criterion (no prompt source) highlights nothing; selecting it scrolls the
  prompt to the top, where "This criterion isn't tied to a specific part of the prompt." is
  shown.
- **Closing the side panel clears the current selection** (and the row highlight).
- **No cost / latency** anywhere. **No winner** — no ranking, "best", or recommendation
  text or affordance.

### 6.10 Tech stack (detail)

- **Backend (Python 3.11+):** Flask `>=3.0` + flask-cors (SSE routes), langchain-openai
  `>=0.1.0` (`ChatOpenAI` → LiteLLM proxy), python-dotenv, gunicorn (prod WSGI), pytest.
- **Frontend:** React 18, Vite 5, TypeScript 5, Tailwind 3, axios (`GET /api/models`),
  `fetch`+`ReadableStream` for SSE, react-markdown + remark-gfm, react-hot-toast, vitest.

---

## 7. API / contract

### `GET /api/models`
Returns the model ids for the pickers. Reads `allowed_models` from `config/models.json`
and intersects with the proxy `/models` list.

| Condition | `models` | `source` |
|---|---|---|
| Allow-list non-empty, proxy reachable | allow-list ∩ proxy (allow-list order) | `config` |
| Allow-list empty, proxy reachable | all proxy models | `proxy` |
| Proxy unreachable, allow-list present | allow-list as-is | `config-unverified` |
| Proxy unreachable, no allow-list | `["gpt-4o", "gpt-4o-mini", "gpt-5-mini"]` | `fallback` |

`FALLBACK_MODELS` lives in exactly one place (`src/evaluator/models.py`).

### `POST /api/score` (scoring) — SSE
Generates the checklist internally (automatic two-pass) and grades it; **no
client-supplied checklist**.
- Request: `{ "prompt": string, "title"?: string, "models": string[] (1–3) }`
- Events: `checklist` → `outputs` → `scoring` → `done`, or `error`.
- `done` payload (`RunResult`):

```jsonc
{
  "title": null,
  "mode": "scoring",
  "checklist": [Criterion, ...],
  "council": ["claude-sonnet-4-6", "gpt-5.4", "gpt-4o"],   // judges actually used
  "council_unavailable": [],   // configured judges the proxy didn't serve
  "council_excluded": [],      // always [] (kept for shape)
  "models": [
    {
      "model": "gpt-5.4",
      "output": "<first successful sample>",
      "error": null,
      "pass_count": 6, "total": 8, "pass_pct": 75,
      "items": [ { "id": "r1", "verdict": "PASS", "note": "", "no_votes": false }, ... ],
      "sampling": { "generated": 5, "graded": 5, "total_criteria": 8,
                    "scores": [6,7,6,5,6],
                    "avg_score": 6.0, "min_score": 5, "max_score": 7, "stdev": 0.71 }
    }
  ]
}
```

### `POST /api/generate` (output-only) — SSE
`{ prompt, title?, models }` → `outputs` → `done` (`mode: "output_only"`).

`POST /api/run`, `POST /api/checklist`, and `POST /api/grade` do **not** exist. No
payload anywhere contains a winner / ranking / recommendation.

**Frontend contract** (`api/comparison.ts`, `types.ts`): `fetchModels()`,
`score(req, handlers)` (SSE), `generateOutputs(req, handlers)` (SSE). `ChecklistItem = {
id, text, tag, source, source_quote, spans, pass_means, fail_means, check? }` (**no
`priority`**); `ModelResult` carries `low_confidence`/`no_votes` per item and a `sampling`
summary.

---

## Project structure

```
llm_evaluator/
├── AGENTS.md                     ← how to work here (constitution + context)
├── SPECS.md                      ← THIS FILE (single source of truth)
├── README.md                     ← setup + design decisions
├── docs/
│   └── model-evaluator.md        ← per-feature human doc (status header)
├── specs/
│   ├── model-evaluator.md        ← pointer → ../SPECS.md
│   └── plan.archived.md          ← shipped PLAN.md, archived
├── .env / .env.example           ← LITELLM_API_KEY + LITELLM_API_BASE only
├── requirements.txt
├── config/
│   ├── models.json               ← picker allow-list { "allowed_models": [...] }
│   └── evaluator.json            ← checklist_model, council, backup_judge, samples, output_temperature
├── cdk/                          ← AWS CDK infra (TypeScript)
├── src/evaluator/
│   ├── config.py                 ← load_evaluator_config()
│   ├── llm.py                    ← get_llm() + parse_json_response()
│   ├── models.py                 ← list_models() + list_all_proxy_models()
│   ├── prompts.py                ← CHECKLIST_MAKER / CRITIC / SCORER prompts
│   ├── provenance.py             ← find_quote() + ground_checklist() (grounding gate)
│   ├── autocheck.py              ← deterministic auto-checks (parser + CHECK_KINDS)
│   ├── council.py                ← resolve_council() + aggregate_votes()
│   ├── checklist.py              ← two-pass maker→critic + grounding, NO cache
│   └── pipeline.py               ← generate() / grade() / score(): sample → blind → council → aggregate
├── demo/
│   ├── server/
│   │   ├── app.py                ← Flask: /api/models, /api/score, /api/generate (SSE)
│   │   └── wsgi.py               ← Gunicorn entrypoint (serves demo/ui/dist)
│   └── ui/
│       └── src/
│           ├── App.tsx           ← input → running → results; selection state
│           ├── types.ts          ← Criterion, ModelResult (+sampling), SSE payloads
│           ├── api/comparison.ts ← fetchModels / score / generateOutputs (SSE)
│           ├── lib/
│           │   ├── beeswarm.ts   ← consistencyLabel (≤2), mean, chart helpers (+ .test.ts)
│           │   └── highlight.ts  ← buildSegments / shouldScroll (+ .test.ts)
│           └── components/
│               ├── PromptForm.tsx       ← prompt + mode toggle + pickers
│               ├── ProgressStages.tsx
│               ├── OutputColumns.tsx
│               ├── ChecklistGrid.tsx    ← ✓/✗/– grid + run-consistency section
│               ├── DotPlot.tsx          ← per-model run-consistency sparkline
│               └── DetailsSidebar.tsx   ← run details + click-to-select provenance highlight
└── tests/                        ← pytest (LLM-free; injected fakes):
    config · provenance · autocheck · checklist · council · sampling · blinding ·
    pipeline · server · no_winner
```

---

## 8. Task breakdown

The initial build and its revisions shipped in bounded, verified increments (archived in
[`specs/plan.archived.md`](specs/plan.archived.md) and the git history). The current change
(v10) is:

- [ ] **V10-0 — Docs restructure.** Consolidate to this single `SPECS.md`; retire
  `specs/model-evaluator.md` to a pointer; archive `PLAN.md`; add `docs/model-evaluator.md`;
  refresh `AGENTS.md` + `README.md`. **verify:** `pytest -q` green; structural greps
  (no `/api/run`, `/api/checklist`, `priority`, "review/edit" claims; all 10 sections
  present; `≤ 2` rule stated).
- [ ] **V10-1 — Consistency threshold ≤ 2.** `consistencyLabel` `max − min ≤ 2`; boundary
  unit tests. **verify:** `cd demo/ui && npm run build && npm test`.
- [ ] **V10-2 — Click-to-select provenance + copy.** Click selects a requirement (row
  highlighted); selecting opens a collapsed panel; implicit selection scrolls to top;
  closing the panel clears selection; run-consistency copy says "five". **verify:**
  `npm run build && npm test`; E2E via the mock server.

---

## 9. Verification criteria

Automated checker: `python -m pytest tests/ -v` (backend) and `cd demo/ui && npm test`
(UI helpers). Each maps to a requirement.

| # | Requirement | Test |
|---|---|---|
| V1 | Auto-checks deterministic | `test_autocheck.py` — same output twice → identical verdicts |
| V2 | Each auto-check kind correct | `test_autocheck.py` per-kind cases |
| V3 | Council majority + split | `test_council.py::test_majority_verdict`, `::test_split_*`, empty→fallback |
| V4 | Per-output grading independence | `test_pipeline.py` — a fake judge keyed on output text gives different models different verdicts |
| V5 | Blinding | `test_blinding.py` — no model id in any judge prompt; single-output grading |
| V6 | Multi-sample aggregation | `test_sampling.py` — majority cell, avg/min/max/stdev, ragged counts, `scores` present |
| V7 | Auto fallback to judge | `test_pipeline.py` — an `UNVERIFIABLE` auto check is scored by the council |
| V8 | Modes + SSE | `test_pipeline.py` output-only vs score; `test_server.py` `/api/score` streams SSE, old routes gone |
| V9 | Grounding gate | `test_provenance.py` — offsets, multi-match, missing→dropped, implicit→no spans |
| V10 | No winner | `test_no_winner.py` — scans payloads for forbidden keys/words |
| V11 | Consistency label ≤ 2 | `beeswarm.test.ts` — `[3,5]`→Consistent, `[2,5]`→Variable, `[1,5,3]`→Variable |
| V12 | Highlight logic | `highlight.test.ts` — `shouldScroll`/segment computation; click/scroll/selection verified E2E |

**End-to-end evidence:** run `python -m demo.server.app` + the Vite dev server (or the
scratchpad mock), drive output-only and scoring modes, and confirm the grid, run-consistency
sparkline, click-to-select provenance, and judge-availability notice behave per spec — shown
with a passing run / DOM inspection, not asserted.

---

## 10. Future considerations (not the current target)

- **Cost / token accounting** — dropped. If revived, compute from real `usage` returned by
  the proxy, not a word-count estimate.
- **Persisted run history / export.**
- **Auth / SSO** and **more than three models.**

---

*End of SPECS.md*
