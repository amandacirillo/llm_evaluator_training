# LLM Evaluator — Model Comparison & Scoring

> **About this repo.** This was built collaboratively with a small team at my
> employer (not a solo personal project, and not a from-scratch recreation like
> my other `_training` repos). I was a co-contributor to the design and
> implementation. It's published here lightly sanitized: internal
> product/codenames, employer domain names, and real AWS resource IDs
> (VPC/subnet/certificate/prefix-list IDs) have been swapped for generic
> placeholders. The architecture, pipeline logic, and tests are otherwise
> unchanged from what we actually built.

Send one prompt to up to three AI models, see their outputs **side by side**, and
get an **objective pass/fail grade** of how well each output met the prompt's
requirements. Built to help you decide, with evidence, which model to use — it
**never declares a winner itself**.

> **Specs are the source of truth.** Read [`AGENTS.md`](AGENTS.md) (how to work
> here), then [`SPECS.md`](SPECS.md) (the single source of truth). A per-feature
> walkthrough lives in [`docs/model-evaluator.md`](docs/model-evaluator.md). Code
> changes must match the spec — update the spec before the code.

---

## Two modes

- **Output comparison only** — generate and show each model's output side by
  side, no checklist or scoring.
- **Output comparison + evaluation scoring** — the full pipeline below.

## How scoring works

1. **Two-pass checklist (automatic).** A *maker* pass drafts prompt-specific binary
   PASS/FAIL criteria; a *critic* pass refines them (de-ambiguate, split non-atomic
   items, strip example-leakage). Each criterion is tagged **auto** (checkable in
   code) or **judged** (needs an LLM), carries a frozen pass/fail rubric, and a
   verbatim **source quote** located in your prompt. The checklist is generated
   **without human editing** — to change a requirement, edit the prompt. Nothing is
   cached; every prompt regenerates.
2. **Multi-sampling.** Each selected model is called **N times** (default 5) so
   consistency is measurable.
3. **Split grading.** *Auto* criteria are checked by deterministic Python (option
   counts, key counts, no duplicate options, stem present, schema); if an output
   can't be parsed, that criterion **falls back to the judge** rather than failing.
   *Judged* criteria go to a **council** of judge models — majority vote decides.
   Grading is **blinded**: each judge scores **one identity-stripped output at a
   time** (labeled just "OUTPUT", no model name, no other outputs in the prompt), so
   it can't tell whose output it is or anchor on the others.
4. **Results.** Outputs side by side; a pass-% headline per model; the
   requirement-by-model **✓/✗/–** grid (majority verdict across samples). Hover a
   **✗** to see why that requirement failed; **click** a requirement to highlight the
   exact prompt text it came from in the side panel. Below the grid, a per-model
   **run-consistency** sparkline shows each run's score, the model's average, and
   whether it was **consistent** or **variable**. **No cost or latency is shown.**

---

## Setup

### Prerequisites
- Python 3.11+
- Node 18+

### 1. Backend

```bash
# from the repo root
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then edit .env (see below)
python -m demo.server.app          # serves on http://127.0.0.1:5001
```

### 2. Frontend

```bash
cd demo/ui
npm install
npm run dev                        # serves on http://localhost:3000
```

Open **http://localhost:3000**. The Vite dev server proxies `/api/*` to Flask, so
the browser only ever calls same-origin `/api/*` and never sees your key.

---

## Configuration

**Environment (`.env`) holds only the proxy secret + endpoint:**

| Var | Required | Purpose |
|---|---|---|
| `LITELLM_API_BASE` | yes | Your LiteLLM proxy URL (OpenAI-compatible), e.g. `https://litellm.example.com` |
| `LITELLM_API_KEY` | yes | Your LiteLLM key (`sk-…`). **Server-side only.** |

**Everything else lives in `config/evaluator.json`** (committed, non-secret):

```json
{
  "checklist_model": "claude-sonnet-4-6",
  "council": ["claude-sonnet-4-6", "gpt-5.4", "claude-sonnet-4-5"],
  "backup_judge": "gpt-5.4-mini",
  "samples": 5,
  "output_temperature": 0
}
```

- `checklist_model` — model for the maker + critic passes.
- `council` — default judge panel. Resolved against the proxy at runtime; a member
  the proxy doesn't serve is dropped, and a missing second `claude-sonnet-*` is
  auto-picked. Set these to exact ids your proxy serves.
- `backup_judge` — used to restore an odd-sized council, or as the fallback single
  judge if the configured council would otherwise be empty; prefer a non-OpenAI,
  non-under-test model.
- `samples` — N, how many times each model is called in scoring mode.
- `output_temperature` — for the compared models (the judges always run at 0).

`config/models.json` separately curates which models appear in the picker.

---

## Choosing which models appear in the picker

The proxy is the source of truth for which models exist; **`config/models.json`**
curates which subset the picker offers:

```json
{ "allowed_models": ["claude-sonnet-4-6", "gpt-4o", "gpt-5-mini"] }
```

- Edit `allowed_models` to control the picker. Ids are validated against the
  proxy, so a typo simply won't appear.
- Leave the array **empty** to show every model your key can reach.
- If the proxy is unreachable and no allow-list is set, a small hardcoded
  fallback (`gpt-4o`, `gpt-4o-mini`, `gpt-5-mini`) is used. The fallback lives in
  exactly one place: `FALLBACK_MODELS` in `src/evaluator/models.py`.

---

## Load-bearing design decisions (please don't undo these)

These are deliberate. Documented here so future maintainers don't reverse them.

1. **The gateway key stays server-side.** All model and judge calls go through
   Flask. `LITELLM_API_KEY` is read from the environment in
   `demo/server/app.py` and is never serialized into any response. The browser
   talks only to `/api/*`.
2. **Scoring is pass/fail against a concrete checklist only.** No subjective 1–10
   quality scores. Every checklist item is binary and human-checkable.
3. **Judges are blinded.** Each judge grades one identity-stripped output at a time
   (labeled just "OUTPUT", no model name, no other outputs alongside it), so it can't
   recognize its own output or anchor on a neighbor. See the per-output grading in
   `src/evaluator/pipeline.py` / `council.py`. This is the core same-family bias
   mitigation — do not weaken it.
4. **A maker never grades its own work.** Generation and verification stay separate.
   For the judges, this is enforced by **blinding** (single, anonymized outputs)
   rather than a self-judging safeguard — a configured judge may also be a model
   under test. Ungrounded criteria are dropped rather than shipped; and "done" means
   a passing test run, not an assertion.
5. **The tool never declares a winner.** It presents per-criterion verdicts, pass
   rates, and variability — the user decides. There is no ranking or
   recommendation anywhere.

> Reversed from v1: the checklist is no longer cached — it is regenerated per
> prompt (maker→critic). It is generated **automatically** (no human review/edit
> step): to change a requirement, edit the prompt.

---

## Judge self-preference bias

An LLM judge tends to favor outputs from its own model family. The mitigation is
**blinding**: each judge scores one identity-stripped output at a time (no model
name, and never several outputs in one prompt), so it can't recognize its own output
or anchor on a neighbor. There is intentionally **no self-judging safeguard** — a
configured judge stays on the council even when it's also a model you're comparing;
blinding is trusted to prevent self-recognition. Configure the `council` /
`backup_judge` in `config/evaluator.json` to favor families outside your comparison
for extra rigor.

The council is resolved against the **full LiteLLM proxy model list**, not the
picker allow-list (`config/models.json`) — so your judges don't need to appear in
the picker. Set `council` to model IDs your proxy actually serves; the server logs
the judges it resolved for each run, and the UI shows a notice if a configured judge
couldn't be used. If a run's council would be empty, the tool falls back to a single
default judge rather than leaving cells ungraded.

## Why scores can still vary between runs

There is no cache — every prompt regenerates its checklist, and the compared
models regenerate a different output each run. That real variation is exactly
what **multi-sampling** measures: each model runs N times (default 5) and the
grid shows the majority verdict per criterion, with the per-model spread in the
**run-consistency** chart (a model is labeled *consistent* when its run scores stay
within 2 points, else *variable*). Judges run at `temperature=0`; the compared
models use `output_temperature` from `config/evaluator.json`.

## Tests

```bash
python -m pytest tests/ -q          # backend
cd demo/ui && npm test              # UI helpers (vitest)
```

Backend tests are LLM-free (pure helpers + injected fakes): `test_config`,
`test_provenance`, `test_autocheck`, `test_checklist`, `test_council`,
`test_sampling`, `test_blinding`, `test_pipeline`, `test_server`, and
`test_no_winner` (asserts no ranking/winner is ever emitted). UI tests cover the
pure highlight helpers.

---

## Project layout

See `SPECS.md` §8 and [`AGENTS.md`](AGENTS.md). In short: pipeline logic in
`src/evaluator/` (`config`, `provenance`, `autocheck`, `checklist`, `council`,
`pipeline`), the thin Flask server in `demo/server/app.py`, and the React + Vite
+ Tailwind UI in `demo/ui/`.

---

## Not in v1 (future work)

Cost/token accounting, run history/export, SSO/auth, and more than three models.
