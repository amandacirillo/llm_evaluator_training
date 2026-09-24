import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { fetchModels, generateOutputs, score } from "./api/comparison";
import PromptForm, { type Mode } from "./components/PromptForm";
import ProgressStages, { type Stage } from "./components/ProgressStages";
import OutputColumns from "./components/OutputColumns";
import ChecklistGrid from "./components/ChecklistGrid";
import DetailsSidebar from "./components/DetailsSidebar";
import type { ChecklistItem, RunResult } from "./types";

type View = "input" | "running" | "results";

export default function App() {
  const [view, setView] = useState<View>("input");

  const [prompt, setPrompt] = useState("");
  const [title, setTitle] = useState("");
  const [models, setModels] = useState<[string, string, string]>(["", "", ""]);
  const [mode, setMode] = useState<Mode>("scoring");

  const [options, setOptions] = useState<string[]>([]);

  const [stage, setStage] = useState<Stage>("checklist");
  const [result, setResult] = useState<RunResult | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(320);

  // Provenance highlight: a requirement is selected by click; the selection persists
  // until you click it again, click empty space, or close the side panel.
  const [selectedCriterion, setSelectedCriterion] = useState<ChecklistItem | null>(null);
  const activeCriterion = selectedCriterion;

  // Selecting a requirement opens the panel (so a collapsed panel reveals the
  // highlight); toggling the panel closed clears the current selection.
  const selectCriterion = (item: ChecklistItem) => {
    setSelectedCriterion((cur) => {
      const next = cur?.id === item.id ? null : item;
      if (next) setPanelOpen(true);
      return next;
    });
  };
  const togglePanel = () => {
    setPanelOpen((open) => {
      if (open) setSelectedCriterion(null);
      return !open;
    });
  };

  useEffect(() => {
    fetchModels()
      .then((r) => {
        setOptions(r.models);
        if (r.models[0]) setModels((m) => [m[0] || r.models[0], m[1], m[2]]);
      })
      .catch(() => toast.error("Could not load the model list."));
  }, []);

  const onModelChange = (index: 0 | 1 | 2, value: string) => {
    setModels((m) => {
      const next = [...m] as [string, string, string];
      next[index] = value;
      return next;
    });
  };

  const selectedModels = models.filter(Boolean);

  const onSubmit = () => {
    if (!prompt.trim() || selectedModels.length === 0) return;
    setResult(null);
    setPanelOpen(true);

    if (mode === "output_only") {
      setStage("outputs");
      setView("running");
      generateOutputs(
        { prompt: prompt.trim(), title: title.trim() || undefined, models: selectedModels },
        {
          onOutputs: () => setStage("outputs"),
          onDone: (r) => {
            setResult(r);
            setStage("done");
            setView("results");
          },
          onError: (m) => {
            toast.error(m);
            setView("input");
          },
        }
      ).catch((e) => {
        toast.error(String(e));
        setView("input");
      });
      return;
    }

    // Scoring mode — a single call: the checklist is generated automatically
    // then graded (no review step). To change a requirement, edit the prompt.
    setStage("checklist");
    setView("running");
    score(
      { prompt: prompt.trim(), title: title.trim() || undefined, models: selectedModels },
      {
        onOutputs: () => setStage("scoring"),
        onScoring: () => setStage("scoring"),
        onDone: (r) => {
          setResult(r);
          setStage("done");
          setView("results");
        },
        onError: (m) => {
          toast.error(m);
          setView("input");
        },
      }
    ).catch((e) => {
      toast.error(String(e));
      setView("input");
    });
  };

  const onReset = () => {
    setView("input");
    setResult(null);
  };

  const running = view === "running";
  const showSidebar = view !== "input";

  return (
    <div className="flex h-screen flex-col">
      <header className="shrink-0 border-b border-border bg-surface">
        <div className="flex items-baseline gap-2 px-6 py-3">
          <span className="text-sm font-semibold text-ink">LLM Evaluator</span>
          <span className="text-sm text-ink-muted">
            – Model Comparison and Scoring Tool
          </span>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {showSidebar && (
          <DetailsSidebar
            open={panelOpen}
            onToggle={togglePanel}
            title={title}
            prompt={prompt}
            models={selectedModels}
            width={sidebarWidth}
            onWidthChange={setSidebarWidth}
            highlightSpans={
              activeCriterion && activeCriterion.source !== "implicit"
                ? activeCriterion.spans ?? []
                : []
            }
            implicitActive={activeCriterion?.source === "implicit"}
            highlightKey={`sel:${activeCriterion?.id ?? ""}`}
            pinned={!!selectedCriterion}
          />
        )}

        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1400px] px-6 py-8">
            {view === "input" && (
              <PromptForm
                prompt={prompt}
                title={title}
                models={models}
                options={options}
                running={running}
                mode={mode}
                onPromptChange={setPrompt}
                onTitleChange={setTitle}
                onModelChange={onModelChange}
                onModeChange={setMode}
                onSubmit={onSubmit}
              />
            )}

            {view === "running" && (
              <div className="py-4">
                <ProgressStages stage={stage} mode={mode} />
              </div>
            )}

            {view === "results" && result && (
              <div className="flex flex-col gap-10">
                <div className="flex items-start justify-between gap-4">
                  <h1 className="text-lg font-semibold text-ink">
                    Outputs side by side
                  </h1>
                  <button
                    className="shrink-0 rounded bg-accent-strong px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[#6B79D6]"
                    onClick={onReset}
                  >
                    + New comparison
                  </button>
                </div>

                <OutputColumns
                  outputs={result.models.map((m) => ({
                    model: m.model,
                    output: m.output,
                    error: m.error,
                  }))}
                />

                {result.mode !== "output_only" && result.checklist && (
                  <section
                    className="flex flex-col gap-5"
                    onClick={() => setSelectedCriterion(null)}
                  >
                    {(() => {
                      const missing = [
                        ...(result.council_unavailable ?? []),
                        ...(result.council_excluded ?? []),
                      ];
                      const used = result.council?.length ?? 0;
                      if (!missing.length && used >= 3) return null;
                      return (
                        <div className="rounded-lg border border-[#E3C36B] bg-[#FBF3D8] px-4 py-2.5 text-sm text-[#7A5B12]">
                          <span className="font-medium">Heads-up:</span>{" "}
                          {missing.length > 0
                            ? `judge${missing.length > 1 ? "s" : ""} ${missing
                                .map((m) => `“${m}”`)
                                .join(", ")} couldn’t be used`
                            : "fewer than 3 judges were available"}
                          {used > 0 ? ` — scored with ${used} judge${used > 1 ? "s" : ""}.` : "."}{" "}
                          Update the council in <code>config/evaluator.json</code>.
                        </div>
                      );
                    })()}
                    <div>
                      <h2 className="text-lg font-semibold text-ink">
                        Prompt requirement adherence
                      </h2>
                      <p className="mt-1 text-sm text-ink-muted">
                        Each output is graded against a checklist derived from the
                        prompt. Pass/fail is determined by three AI judge models,
                        and supporting evidence is shown so you can validate the
                        results yourself.
                      </p>
                    </div>
                    <ChecklistGrid
                      result={result}
                      selectedId={selectedCriterion?.id ?? null}
                      onSelectCriterion={selectCriterion}
                    />
                  </section>
                )}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
