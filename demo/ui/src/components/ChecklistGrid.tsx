import type { ChecklistItem, ItemVerdict, RunResult } from "../types";
import DotPlot from "./DotPlot";

interface Props {
  result: RunResult;
  /** Click-to-select wiring (supplied by App for the provenance side panel). */
  onSelectCriterion?: (item: ChecklistItem) => void;
  /** Id of the currently-selected requirement row (highlighted). */
  selectedId?: string | null;
}

export default function ChecklistGrid({ result, onSelectCriterion, selectedId = null }: Props) {
  const checklist = result.checklist ?? [];
  const scored = result.models.filter((m) => !m.error);
  if (!scored.length || !checklist.length) return null;

  const verdictOf = (modelIdx: number, itemId: string): ItemVerdict | undefined =>
    scored[modelIdx].items.find((it) => it.id === itemId);

  return (
    <div className="flex flex-col gap-5">
      {/* Headline pass scores */}
      <div
        className="grid gap-3"
        style={{ gridTemplateColumns: `repeat(${scored.length}, minmax(0, 1fr))` }}
      >
        {scored.map((m) => {
          const good = m.pass_pct >= 80;
          return (
            <div
              key={m.model}
              className="rounded-xl border border-border bg-surface p-4 text-center"
            >
              <div className="truncate text-xs text-ink-muted" title={m.model}>
                {m.model}
              </div>
              <div
                className="mt-1 text-3xl font-semibold"
                style={{ color: good ? "#2F8F5B" : "#C24B3A" }}
              >
                {m.pass_pct}%
              </div>
              <div className="text-xs text-ink-muted">
                {m.pass_count} / {m.total} passed
              </div>
            </div>
          );
        })}
      </div>

      {/* Requirement-by-model grid. */}
      <div className="rounded-xl border border-border bg-surface">
        <table className="w-full border-collapse text-sm" style={{ tableLayout: "fixed" }}>
          <thead>
            <tr>
              <th className="w-[44%] rounded-tl-xl bg-bg px-4 py-2.5 text-left font-medium text-ink-muted">
                Requirement
              </th>
              {scored.map((m, i) => (
                <th
                  key={m.model}
                  className={`bg-bg px-2 py-2.5 text-center font-medium text-ink-muted ${
                    i === scored.length - 1 ? "rounded-tr-xl" : ""
                  }`}
                >
                  <span className="block truncate" title={m.model}>
                    {m.model}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {checklist.map((item) => {
              const selected = selectedId === item.id;
              // Browsers don't paint `background` on <tr> under border-collapse, so
              // the selected tint is applied to the cells — via inline style so it
              // doesn't depend on Tailwind's --tw-bg-opacity var (which the row's
              // hover variant can zero out).
              const selBg = "#E8EAFB"; // = accent-soft
              return (
                <tr
                  key={item.id}
                  className={`cursor-pointer border-t border-border ${
                    selected ? "" : "hover:bg-accent-soft/40"
                  }`}
                  aria-selected={selected}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectCriterion?.(item);
                  }}
                >
                  <td
                    className="relative px-4 py-2.5 align-top text-ink"
                    style={
                      selected
                        ? { boxShadow: "inset 3px 0 0 0 #6B79D6", backgroundColor: selBg }
                        : undefined
                    }
                  >
                    <span>{item.text}</span>
                  </td>
                  {scored.map((_, idx) => {
                    const v = verdictOf(idx, item.id);
                    const unscored = !!v?.no_votes;
                    const pass = v?.verdict === "PASS";
                    const note = v?.note?.trim() || "";
                    const tip = unscored
                      ? note || "No judge was available to score this."
                      : !pass && note
                      ? note
                      : "";
                    const glyph = unscored ? "–" : pass ? "✓" : "✗";
                    const glyphColor = unscored ? "#9CA3AF" : pass ? "#2F8F5B" : "#C24B3A";
                    return (
                      <td
                        key={idx}
                        className="px-2 py-2.5 text-center align-top"
                        style={selected ? { backgroundColor: selBg } : undefined}
                      >
                        <span className="group relative inline-flex cursor-default justify-center">
                          <span
                            className="text-base font-semibold"
                            style={{ color: glyphColor }}
                            aria-label={
                              unscored
                                ? "not scored — no judge available"
                                : pass
                                ? "pass"
                                : note
                                ? `fail: ${note}`
                                : "fail"
                            }
                            tabIndex={0}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {glyph}
                          </span>
                          {tip && (
                            <span
                              role="tooltip"
                              className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-2 hidden w-56 -translate-x-1/2 rounded-lg bg-ink px-3 py-2 text-left text-xs font-normal leading-snug text-white shadow-lg group-hover:block group-focus-within:block"
                            >
                              {tip}
                              <span className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-ink" />
                            </span>
                          )}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-muted">
        Hover an <span className="font-medium" style={{ color: "#C24B3A" }}>✗</span> to
        see why that requirement failed, and click a requirement to see the part of
        your prompt it came from.
      </p>

      <section className="mt-2 flex flex-col gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">Run consistency</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Each AI model is run against the prompt five times to gauge how
            consistent it is: steady scores read as consistent, swinging scores as
            variable. Favor a model that's both high-scoring and steady.
          </p>
        </div>
        <div className="rounded-xl border border-border bg-surface p-4">
          <DotPlot models={result.models} />
        </div>
      </section>
    </div>
  );
}
