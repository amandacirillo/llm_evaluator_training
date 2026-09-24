import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { StreamedOutput } from "../types";

interface Props {
  outputs: StreamedOutput[];
}

export default function OutputColumns({ outputs }: Props) {
  if (!outputs.length) return null;

  const cols =
    outputs.length === 1
      ? "grid-cols-1"
      : outputs.length === 2
      ? "grid-cols-1 md:grid-cols-2"
      : "grid-cols-1 md:grid-cols-3";

  return (
    <div className={`grid gap-4 ${cols}`}>
      {outputs.map((o) => (
        <div
          key={o.model}
          className="flex flex-col overflow-hidden rounded-xl border border-border bg-surface"
        >
          <div className="border-b border-border bg-accent-soft px-4 py-2.5 text-sm font-medium text-ink">
            {o.model}
          </div>
          <div className="flex-1 p-4">
            {o.error ? (
              <div className="rounded border border-fail/30 bg-fail/5 p-3 text-sm text-fail">
                <span className="font-medium">Model failed.</span> {o.error}
              </div>
            ) : o.output ? (
              <div className="markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{o.output}</ReactMarkdown>
              </div>
            ) : (
              <p className="text-sm italic text-ink-muted">(no output returned)</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
