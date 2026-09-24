# AGENTS.md — LLM Evaluator

Operating guide for AI agents (and humans) working in this repo. Read this first,
then read `SPECS.md` (the source of truth for behavior). When a task changes
behavior, the flow is **spec → plan → verified implementation**, never
code-first.

---

## What this project is

The **LLM Evaluator** takes an item-generation prompt (multiple-choice /
multiple-select) plus 1–3 models, generates a PASS/FAIL checklist from the prompt,
blind-grades each model's output against the checklist with an LLM judge, and
shows a per-criterion results grid. Its job is to **present evidence so a
user can decide which model fits their prompt**.

> **The tool must NEVER declare a winner itself.** It surfaces per-criterion
> verdicts, pass rates, and variability — the human decides.

---

## Tech stack

**Backend (Python 3.11)** — pipeline logic in `src/evaluator/`, thin Flask server
in `demo/server/`.

| Package | Used for |
|---|---|
| Flask `>=3.0`, flask-cors `>=4.0` | Demo server + API routes (SSE) |
| langchain-openai `>=0.1.0` | LLM calls via the LiteLLM proxy (`ChatOpenAI`) |
| python-dotenv `>=1.0.0` | Loads `.env` |
| gunicorn `>=22.0` | Production WSGI server |
| pytest `>=8.0` | Tests |

**Frontend (React + Vite + TypeScript)** — `demo/ui/`. React 18, Vite 5, Tailwind
3, axios (for `GET /api/models`), `fetch`+`ReadableStream` for SSE, react-markdown
+ remark-gfm, react-hot-toast.

**LLM access** — every call goes through `get_llm()` in `src/evaluator/llm.py`,
which builds a `ChatOpenAI` pointed at a LiteLLM proxy. The proxy is the source of
truth for which models exist. **The gateway key is read from the environment
server-side and never serialized into any response.**

**Configuration** — the environment holds **only** `LITELLM_API_KEY` and
`LITELLM_API_BASE` (secrets/endpoint). All other tunables — the checklist/critic
model, the judge council, the backup judge, the sample count N, and the output
temperature — live in `config/` JSON files (`config/models.json` for the picker
allow-list; `config/evaluator.json` for judge/council/sampling). Config is not
secret and is committed.

---

## Project structure

```
llm_evaluator/
├── AGENTS.md                 ← this file (how to work here)
├── SPECS.md                  ← single source of truth for behavior (10-section spec)
├── README.md                 ← setup + design decisions
├── docs/model-evaluator.md   ← per-feature human doc (status header)
├── specs/
│   ├── model-evaluator.md    ← pointer → ../SPECS.md
│   └── plan.archived.md      ← shipped build plan, archived
├── .env / .env.example       ← LITELLM_API_KEY + LITELLM_API_BASE only
├── config/
│   ├── models.json           ← picker allow-list
│   └── evaluator.json        ← checklist_model, council, backup_judge, samples N, output_temperature
├── src/evaluator/
│   ├── config.py             ← load_evaluator_config()
│   ├── llm.py                ← get_llm() + parse_json_response()
│   ├── models.py             ← list_models() + list_all_proxy_models()
│   ├── prompts.py            ← checklist maker/critic + scorer prompts
│   ├── provenance.py         ← find_quote() + ground_checklist() (grounding gate)
│   ├── autocheck.py          ← deterministic auto-checks (parser + CHECK_KINDS)
│   ├── council.py            ← resolve_council() + aggregate_votes()
│   ├── checklist.py          ← two-pass maker→critic + grounding (no cache)
│   └── pipeline.py           ← generate()/grade()/score(): sample → blind → council → aggregate
├── demo/
│   ├── server/app.py         ← Flask API routes (SSE): /api/models, /api/score, /api/generate
│   └── ui/                   ← React SPA (src/App.tsx, components/, lib/, api/comparison.ts, types.ts)
└── tests/                    ← pytest; pure helpers tested without an LLM
```

`SPECS.md` §8 is authoritative for the *current* file layout; when a change lands,
reconcile `SPECS.md` first.

---

## How to run

**Backend** (from repo root, with `.env` populated):
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m demo.server.app                           # http://127.0.0.1:5001
```

**Frontend**:
```bash
cd demo/ui && npm install && npm run dev            # http://localhost:3000 (proxies /api → :5001)
```

Production runs Gunicorn (`demo/server/wsgi.py`) serving the pre-built SPA from
`demo/ui/dist`. Note Gunicorn runs multiple workers, so **the server keeps no
cross-request state** — anything needed across API phases round-trips through the
client.

## How to test

Python tests are the automated checker (they gate deploy in CI):
```bash
python -m pytest tests/ -v
```
Test files live in `tests/`, are named `test_*.py`, and each inserts
`.../src` on `sys.path` at the top so `import evaluator.*` works. There is no
pytest config file and no `conftest.py`. Pure helpers (blinding, scoring
aggregation, auto-checks, council) are tested **without an LLM or network** by
injecting fakes — keep new logic in that pure, injectable style.

Frontend build check: `cd demo/ui && npm run build` (runs `tsc -b` then Vite).
UI helper tests: `cd demo/ui && npm test` (vitest — `lib/beeswarm.test.ts`,
`lib/highlight.test.ts`).

---

## Conventions (how we write code here)

- **Error handling.** A per-model failure is caught and returned as
  `{ model, error }` for that column — it never aborts the run. A failing judge is
  isolated (counts as no vote, logged). Whole-run failures surface as an SSE `error`
  event / a toast in the UI.
- **Pure, injectable core.** Business logic in `src/evaluator/` is LLM-free and
  testable with injected fakes (`invoke_factory`, `rng`, fake judges). Keep new
  logic in that style — no network or real LLM in unit tests.
- **Naming / layout.** One module per concern in `src/evaluator/`; each has a 1:1
  `tests/test_<module>.py`. React components are `PascalCase.tsx` under
  `components/`; pure UI helpers live in `lib/` with a co-located `*.test.ts`.
- **SSE everywhere for runs.** Scoring/generation stream `event: <name>\ndata:
  <json>\n\n`; the client consumes them via `fetch` + `ReadableStream`.
- **Config, not env.** Tunables go in `config/*.json`, never new env vars. Only
  `LITELLM_API_KEY` / `LITELLM_API_BASE` come from the environment.

## Do not touch / handle with care

- **Blinding** (single-output, identity-stripped grading in `pipeline.py` /
  `council.py` — each judge sees one output labeled just "OUTPUT") — load-bearing bias
  mitigation; changing it needs a spec update.
- **The no-winner guarantee** — no ranking/"best"/recommendation may enter any
  payload or the UI; `tests/test_no_winner.py` enforces it.
- **`.env` surface** — keep it to the two `LITELLM_*` vars; the key must never reach
  the browser or a response body.
- **Council resolution** (`resolve_council`) — the full-proxy availability check and
  the empty-council fallback exist to avoid the "every cell ✗ / judges split" bug;
  don't gate judges on the picker allow-list again.

## Where to find things

- **Spec (source of truth):** [`SPECS.md`](SPECS.md).
- **Per-feature human doc:** [`docs/model-evaluator.md`](docs/model-evaluator.md).
- **Archived build plan:** [`specs/plan.archived.md`](specs/plan.archived.md).
- **Setup / design rationale:** [`README.md`](README.md).

---

## Constitution — non-negotiable rules

1. **Spec precedence.** `SPECS.md` (and any `specs/*.md` for an in-flight change)
   is the source of truth. **Update the spec before changing code.** If code and
   spec diverge, fix the spec first, then make code match. Do not implement
   behavior the spec doesn't describe.

2. **A maker never grades its own work.** Generation and verification stay
   separate — structurally, not just by convention. In our own process it means the
   thing that writes code is not the sole thing that certifies it — tests do. In the
   product, judging is kept honest by **blinding** rather than a self-judging
   safeguard: a configured judge may also be a model under test, but it only ever
   sees a single identity-stripped output and cannot tell the output is its own.

3. **Every loop has a bounded stop condition.** No open-ended "keep trying."
   Implementation retries are capped (**5 attempts**), then hand back structured
   feedback (what failed, the actual output, the hypothesis) rather than a vague
   retry. Generation/grounding loops declare their bound up front.

4. **Verification is evidence-based.** "Done" requires evidence — a passing test
   run pasted/shown, or the feature exercised end-to-end with observed output.
   Never assert something works without showing it. Never mark a task done without
   the green run.

5. **Never declare a winner.** No ranking, "best model," or recommendation field
   or text anywhere in the pipeline, API, or UI. Present the evidence; the user
   decides.

6. **Preserve blinding.** Each judge grades **one identity-stripped output at a
   time** (labeled just "OUTPUT", no model name) and is told not to guess whose it
   is. This is the core bias-mitigation mechanism — do not weaken or bypass it (e.g.
   never put a model name, or several outputs, in a single judge prompt).

7. **The gateway key stays server-side.** `LITELLM_API_KEY` is read from the env
   in the server and is never sent to the browser or written into a response.

---

## Working rhythm for a behavior change

1. Refresh/confirm `SPECS.md` for the change. Get sign-off.
2. Derive a **temporary plan** (small, independently verifiable tasks, each with a
   `verify:` line — the exact command/observation that proves it). This scaffolding
   is archived under `specs/` once the work ships (see
   [`specs/plan.archived.md`](specs/plan.archived.md)); it is not permanent docs.
3. Implement one task at a time: implement → run tests → show the green run →
   mark the task done → commit. Cap retries at 5; on repeated failure hand back
   structured feedback instead of thrashing.

The tests are the automated checker; the human owns spec sign-off and the merge.
