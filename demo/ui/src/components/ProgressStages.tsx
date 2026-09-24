export type Stage = "checklist" | "outputs" | "scoring" | "done";

const STEPS: { key: Stage; label: string }[] = [
  { key: "checklist", label: "Building requirement checklist" },
  { key: "outputs", label: "Generating outputs" },
  { key: "scoring", label: "Scoring against requirements" },
];

const ORDER: Stage[] = ["checklist", "outputs", "scoring", "done"];

interface Props {
  stage: Stage;
  /** Output-only mode shows just the generation step. */
  mode?: "output_only" | "scoring";
}

export default function ProgressStages({ stage, mode = "scoring" }: Props) {
  const currentIdx = ORDER.indexOf(stage);
  const steps =
    mode === "output_only" ? STEPS.filter((s) => s.key === "outputs") : STEPS;

  return (
    <div className="flex flex-col gap-3 py-8">
      {steps.map((step) => {
        const idx = ORDER.indexOf(step.key);
        const done = currentIdx > idx;
        const active = currentIdx === idx;
        return (
          <div key={step.key} className="flex items-center gap-3">
            <span
              className={[
                "flex h-5 w-5 items-center justify-center rounded-pill text-xs",
                done
                  ? "bg-pass text-white"
                  : active
                  ? "bg-accent text-white"
                  : "bg-accent-soft text-ink-muted",
              ].join(" ")}
            >
              {done ? "✓" : ""}
            </span>
            <span
              className={[
                "text-sm",
                active ? "text-ink" : done ? "text-ink-muted" : "text-ink-muted",
                active ? "font-medium" : "",
              ].join(" ")}
            >
              {step.label}
              {active ? "…" : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}
