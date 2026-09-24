# Model Evaluator

> **Status:** On `feat/model-evaluator-v2`, not yet merged.
> _(After merge: "Merged into `main` on YYYY-MM-DD.")_

## Purpose

The Model Evaluator helps a prompt developer decide which AI model best
fits a given item-generation prompt. You paste one multiple-choice / multiple-select
prompt, pick 1–3 models, and the tool runs them side by side. In **scoring** mode it
also derives a PASS/FAIL requirements checklist from your prompt, runs each model
several times, and blind-grades every output against the checklist with a council of
LLM judges — then shows a per-criterion grid and a per-model run-consistency chart.
Use it when you want an evidence-based comparison instead of eyeballing one output.
**It never declares a winner** — it surfaces the evidence and you decide.

## Inputs / outputs

**Input:** a prompt (required), an optional run title, 1–3 model ids, and a mode
(*output comparison only* or *output comparison + evaluation scoring*).

**Output (scoring mode):** for each model — its first output, a pass count / pass %,
a per-criterion verdict list (✓ / ✗ / –), and a `sampling` summary (per-run scores,
average, min/max, stdev) that drives the run-consistency sparkline. Plus the derived
checklist and the list of judges actually used.

**Example (HTTP):**

```bash
curl -N http://127.0.0.1:5001/api/score \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Write 5 MCQs about the water cycle, 4 options each, one correct.",
       "models":["gpt-5.4","claude-sonnet-4-6"]}'
# → SSE: event: checklist → event: outputs → event: scoring → event: done (RunResult)
```

See [`../SPECS.md`](../SPECS.md) §7 for the full `RunResult` shape.

## Internal design

- **`src/evaluator/checklist.py` + `prompts.py`** — two-pass maker→critic checklist
  generation (no cache), grounded against the prompt.
- **`src/evaluator/provenance.py`** — `find_quote` / `ground_checklist`: locate each
  criterion's `source_quote` in the prompt to compute highlight spans; drop
  ungrounded criteria (bounded 3 retries).
- **`src/evaluator/autocheck.py`** — deterministic, LLM-free auto-checks (counts,
  keys, duplicates, stems, schema); returns `UNVERIFIABLE` (→ council) when it can't
  parse an output.
- **`src/evaluator/council.py`** — `resolve_council` (full-proxy availability,
  empty-council fallback, no self-judging safeguard) and `aggregate_votes` (majority).
- **`src/evaluator/pipeline.py`** — `generate()` (output-only), `grade()` and
  `score()` (scoring): sample each model N times, grade **one identity-stripped
  output per judge prompt**, aggregate across samples. SSE generator.
- **`demo/ui/`** — React SPA: `ChecklistGrid` (grid + run-consistency section),
  `DotPlot` (per-model sparkline; consistent when `max − min ≤ 2`), `DetailsSidebar`
  (click-to-select provenance highlighting of the prompt).

Control flow for a scoring run: `score()` → `generate_checklist()` → sample models →
`resolve_council()` → per-`(model, sample)` `council_grade_output()` →
`aggregate_samples()` → SSE `done`.

## Dependencies

- A **LiteLLM proxy** (OpenAI-compatible) reachable via `LITELLM_API_BASE`, with
  `LITELLM_API_KEY`. The proxy must serve the compared models and the configured
  judges.
- Python: Flask, flask-cors, langchain-openai, python-dotenv, gunicorn (prod).
- UI: React 18, Vite 5, Tailwind 3.
- Config: `config/evaluator.json` (checklist model, council, backup judge, samples,
  output temperature) and `config/models.json` (picker allow-list).

## How to run standalone

```bash
# backend (from repo root, with .env populated)
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m demo.server.app                           # http://127.0.0.1:5001

# frontend
cd demo/ui && npm install && npm run dev            # http://localhost:3000
```

The pipeline is also usable as a library: `from evaluator.pipeline import score` (add
`src/` to `sys.path`), iterating the SSE events it yields.

## Tests

- **Backend (`tests/`, pytest, LLM-free with injected fakes):** `test_autocheck`,
  `test_provenance`, `test_checklist`, `test_council`, `test_sampling`,
  `test_blinding`, `test_pipeline`, `test_server`, `test_config`, `test_no_winner`.
  Run: `python -m pytest tests/ -v`.
- **UI helpers (vitest):** `demo/ui/src/lib/beeswarm.test.ts` (incl. the `≤ 2`
  consistency boundary) and `highlight.test.ts`. Run: `cd demo/ui && npm test`.
- No network or real LLM is used in tests; judges and models are faked.
