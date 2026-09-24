import { useMemo } from "react";
import ModelPicker from "./ModelPicker";

export type Mode = "output_only" | "scoring";

interface Props {
  prompt: string;
  title: string;
  models: [string, string, string];
  options: string[];
  running: boolean;
  mode: Mode;
  onPromptChange: (v: string) => void;
  onTitleChange: (v: string) => void;
  onModelChange: (index: 0 | 1 | 2, v: string) => void;
  onModeChange: (m: Mode) => void;
  onSubmit: () => void;
}

export default function PromptForm({
  prompt,
  title,
  models,
  options,
  running,
  mode,
  onPromptChange,
  onTitleChange,
  onModelChange,
  onModeChange,
  onSubmit,
}: Props) {
  const selected = useMemo(() => models.filter(Boolean), [models]);
  const canSubmit = prompt.trim().length > 0 && selected.length >= 1 && !running;
  const cta = mode === "scoring" ? "Start evaluation" : "Compare outputs";

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.7fr_1fr]">
      {/* Prompt — primary element. Fills the column height to match the inputs. */}
      <div className="flex flex-col">
        <label className="text-sm font-medium text-ink" htmlFor="prompt">
          Your prompt
        </label>
        <textarea
          id="prompt"
          className="mt-2 min-h-[240px] flex-1 resize-y rounded border border-border bg-surface p-4 text-sm leading-relaxed text-ink placeholder:text-ink-muted focus:border-accent-strong focus:outline-none focus:ring-2 focus:ring-accent-soft"
          placeholder="Paste the prompt you want to compare models on."
          value={prompt}
          onChange={(e) => onPromptChange(e.target.value)}
        />
      </div>

      {/* Right panel */}
      <div className="flex flex-col gap-5">
        <label className="block">
          <span className="text-xs text-ink-muted">Run title (optional)</span>
          <input
            className="mt-1 w-full rounded border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent-strong focus:outline-none focus:ring-2 focus:ring-accent-soft"
            placeholder="e.g. Water cycle test #1"
            value={title}
            onChange={(e) => onTitleChange(e.target.value)}
          />
        </label>

        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium text-ink">Mode</span>
          <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Evaluation mode">
            {([
              [
                "output_only",
                "Output comparison only",
                "Choose this option to just compare each selected model's output side by side.",
              ],
              [
                "scoring",
                "Output comparison + evaluation scoring",
                "Choose this option to compare outputs side by side and gain deeper insights into each model's overall performance.",
              ],
            ] as [Mode, string, string][]).map(([value, label, info]) => {
              const active = mode === value;
              return (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => onModeChange(value)}
                  className={[
                    "relative rounded border px-3 py-2 text-left text-xs leading-snug transition-colors",
                    active
                      ? "border-accent-strong bg-accent-soft text-ink"
                      : "border-border bg-surface text-ink-muted hover:border-accent",
                  ].join(" ")}
                >
                  <span className="pr-5">{label}</span>
                  <span
                    className="group absolute right-1.5 top-1.5 inline-flex"
                    role="note"
                    aria-label={info}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <span
                      tabIndex={0}
                      className="flex h-4 w-4 cursor-help items-center justify-center rounded-pill border border-current text-[9px] font-semibold text-ink-muted"
                    >
                      i
                    </span>
                    <span
                      role="tooltip"
                      className="pointer-events-none absolute bottom-full right-0 z-30 mb-2 hidden w-52 rounded-lg bg-ink px-3 py-2 text-left text-xs font-normal leading-snug text-white shadow-lg group-hover:block group-focus-within:block"
                    >
                      {info}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between">
            <span className="text-sm font-medium text-ink">Models to compare</span>
          </div>
          <ModelPicker
            label="Model 1"
            required
            value={models[0]}
            options={options}
            taken={selected}
            onChange={(v) => onModelChange(0, v)}
          />
          <ModelPicker
            label="Model 2"
            value={models[1]}
            options={options}
            taken={selected}
            onChange={(v) => onModelChange(1, v)}
          />
          <ModelPicker
            label="Model 3"
            value={models[2]}
            options={options}
            taken={selected}
            onChange={(v) => onModelChange(2, v)}
          />
        </div>

        <button
          className="mt-1 flex items-center justify-center gap-2 rounded bg-accent-strong px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[#6B79D6] disabled:cursor-not-allowed disabled:bg-border disabled:text-ink-muted disabled:shadow-none"
          disabled={!canSubmit}
          onClick={onSubmit}
        >
          {running ? "Working…" : cta}
        </button>
      </div>
    </div>
  );
}
