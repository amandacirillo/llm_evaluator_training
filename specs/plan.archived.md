# PLAN.md (archived) — Model Evaluator v2 build

> **Status:** Shipped; archived 2026-07-14. Temporary scaffolding, kept for history.
> The source of truth is [`../SPECS.md`](../SPECS.md). Later revisions (v3–v10) were
> tracked outside this file (git history + the per-change plan); this records the
> original v2 task loop only.

Derived from the signed-off model-evaluator spec. Work was done one task at a time:
implement → run the `verify:` command → show the green run → mark done → commit.
Retries capped at 5; on repeated failure, hand back structured feedback. Never marked
done without evidence.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done (with evidence).

---

- [x] **T0 — Docs: reconcile root SPECS.md** — done; `pytest` 8 passed, stale claims removed.
  Update root `SPECS.md` §3.4, "Four design decisions" (#2 wording, #4), and §9 to
  match the new target (review/edit step, no cache, council, N-sampling, config
  file). Add pointer to the model-evaluator spec.
  `verify:` `python -m pytest tests/ -v` still green (docs-only, no code change);
  grep shows no remaining "generated once per prompt and cached" / "No multi-judge".

- [x] **T1 — Config loader + trim env** — done; `test_config.py` 5 passed, full suite 13 passed.
  New `src/evaluator/config.py` (`load_evaluator_config()` with defaults). New
  `config/evaluator.json`. `llm.py`: source `checklist_model`, judge/council, and
  `output_temperature` from config; stop reading `LITELLM_MODEL`,
  `LITELLM_MINI_MODEL`, `LITELLM_OUTPUT_TEMPERATURE`. Trim `.env.example`.
  `verify:` `python -m pytest tests/test_config.py -v` (defaults when file absent;
  values when present; env no longer consulted for models/temperature).

- [x] **T2 — Provenance helper + grounding gate** — done; `test_provenance.py` 6 passed.
  New `src/evaluator/provenance.py`: `find_quote(prompt, quote) -> list[[from,to]]`
  (all matches; empty ⇒ ungrounded). `ground_checklist(prompt, checklist)` sets
  `spans`, drops ungrounded non-implicit items, leaves implicit with `[]`.
  `verify:` `python -m pytest tests/test_provenance.py -v` (V9).

- [x] **T3 — Auto-checks** — done; `test_autocheck.py` 11 passed (determinism + all kinds).
  New `src/evaluator/autocheck.py`: deterministic parser + `CHECK_KINDS` registry +
  `run_auto_check(check, output_text)`.
  `verify:` `python -m pytest tests/test_autocheck.py -v` (V1, V2).

- [x] **T4 — Two-pass checklist generation** — done; `test_checklist.py` 6 passed, full suite 36.
  `prompts.py`: `CHECKLIST_MAKER_PROMPT`, `CHECKLIST_CRITIC_PROMPT`. `checklist.py`:
  `generate_checklist(prompt)` runs maker→critic→ground/gate, bounded 3 attempts,
  **no cache** (remove `_CACHE`/`prompt_hash`/`clear_cache`). Returns Criterion[].
  `verify:` `python -m pytest tests/test_checklist.py -v` (maker/critic wired via
  injected fakes; grounding gate + bounded retry; no cache symbol remains).

- [x] **T5 — Council** — done; `test_council.py` 11 passed (aggregation + safeguard).
  New `src/evaluator/council.py`: `resolve_council(...)` (self-judging safeguard,
  odd-size, backup substitution, empty→low-confidence) and `aggregate_votes(...)`.
  `verify:` `python -m pytest tests/test_council.py -v` (V3, V4).

- [x] **T6 — Grading + sampling + aggregation** — done; pipeline/sampling/blinding/no-winner 19 passed, full suite 58.
  `pipeline.py`: `grade(prompt, models, checklist, *, config, rng)` (SSE-yielding);
  `generate(prompt, models)` (output-only); pure `aggregate_samples(...)`. Per-round
  blinded council grading; auto-checks in code; ragged samples. Remove `run_comparison`.
  `verify:` `python -m pytest tests/test_pipeline.py tests/test_sampling.py tests/test_blinding.py tests/test_no_winner.py -v`
  (V5, V6, V7, V8, V10).

- [x] **T7 — Server routes** — done; `test_server.py` 9 passed, full suite 67.
  `demo/server/app.py`: add `POST /api/checklist` (JSON), `POST /api/grade` (SSE),
  `POST /api/generate` (SSE); remove `POST /api/run`. Keep `GET /api/models`.
  `verify:` `python -m pytest tests/test_server.py -v` (Flask `test_client`: shapes,
  validation, edited-checklist round-trip, no `/api/run`).

- [x] **T8 — Types + API client** — done; verified together with T9/T10 via `npm run build` (green).
  `demo/ui/src/types.ts` (Criterion fields, `low_confidence`, `sampling`, `mode`);
  `api/comparison.ts` (`fetchChecklist`, `gradeChecklist`, `generateOutputs`).
  `verify:` `cd demo/ui && npm run build` (tsc passes).

- [x] **T9 — Input mode toggle + review/edit view** — done; `npm run build` green (E2E smoke pending).
  `PromptForm.tsx` (mode toggle), `App.tsx` (new `review` view + state), new
  `ReviewChecklist.tsx` (add/delete/edit → Approve & grade with edited list).
  `verify:` `cd demo/ui && npm run build`; E2E in preview: scoring run pauses at
  review, edits carry into grading.

- [x] **T10 — Results additions** — done; `npm run build` green (E2E smoke pending).
  `ChecklistGrid.tsx` (auto/judged icon; low-confidence in-cell marker + tooltip);
  new `SummaryTable.tsx` (items generated/graded, avg "X out of total", spread).
  Grid stays visually identical otherwise; no cost/latency.
  `verify:` `cd demo/ui && npm run build`; E2E screenshot shows icons + table.

- [x] **T11 — Provenance highlight** — done; vitest 10 passed; E2E verified: hover
  highlights the correct span in the sidebar, different criteria map to different
  spans, click pins (ring style persists), collapsed panel shows a popover with
  the quote in context; output-only shows no grid.
  `DetailsSidebar.tsx` (prompt as spans; hover highlight; click pin; scroll only
  off-screen; collapsed popover; implicit → nothing). Pure `isSpanVisible` helper.
  `verify:` `cd demo/ui && npm test` (vitest: `isSpanVisible`/highlight helper) +
  E2E in preview.

- [x] **T12 — Docs: README** — done; README rewritten (modes, review, council,
  sampling, config, env trim); SPECS.md §4.3/§5/§6/§7 marked (v2) with redirects.
  Update `README.md` (modes, review step, council, sampling, config file, env
  trim). Final root `SPECS.md` consistency pass.
  `verify:` `python -m pytest tests/ -v` green; manual read-through.

---

**Definition of done (whole change):** all `verify:` lines green, an E2E run of
both modes shown with proof, root `SPECS.md`/`README.md` reconciled, and **no
winner** anywhere (V10).

> **Note (2026-07-14):** several tasks above describe the intermediate v2 design
> (a review/edit step, `/api/checklist` + `/api/grade`, auto/judged icons, a summary
> table). Those were superseded by v3–v10 — see [`../SPECS.md`](../SPECS.md) for the
> shipped state (single `POST /api/score`, no review step, run-consistency sparkline,
> click-to-select provenance).
