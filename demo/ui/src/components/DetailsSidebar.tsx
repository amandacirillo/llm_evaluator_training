import { useEffect, useRef } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import { buildSegments, shouldScroll, type Span } from "../lib/highlight";

interface Props {
  open: boolean;
  onToggle: () => void;
  title: string;
  prompt: string;
  models: string[];
  width: number;
  onWidthChange: (w: number) => void;
  /** Spans of the active criterion's source quote (empty when none/implicit). */
  highlightSpans?: Span[];
  /** True when the active criterion is implicit (tied to no specific text). */
  implicitActive?: boolean;
  /** Changes whenever the active criterion changes — drives the scroll effect. */
  highlightKey?: string;
  /** True when the highlight is pinned (click) vs. transient (hover). */
  pinned?: boolean;
}

const MIN_WIDTH = 220;
const MAX_WIDTH = 620;

/**
 * Full-height left rail showing the run's inputs. The prompt is rendered as
 * highlightable segments so the selected criterion's source quote lights up
 * inline; it smooth-scrolls into view only when off-screen. An implicit criterion
 * (no source span) scrolls the prompt to the top, where the "not tied to a specific
 * part" note is shown.
 */
export default function DetailsSidebar({
  open,
  onToggle,
  title,
  prompt,
  models,
  width,
  onWidthChange,
  highlightSpans = [],
  implicitActive = false,
  highlightKey = "",
  pinned = false,
}: Props) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const markRef = useRef<HTMLSpanElement | null>(null);
  const implicitRef = useRef<HTMLDivElement | null>(null);

  // React to the selected criterion changing.
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const mark = markRef.current;
    // Implicit criterion (no highlight span): scroll the prompt to the top, where the
    // "not tied to a specific part" message is shown. Scoped to this container (not
    // scrollIntoView, which would also scroll the page) and offset a little for room.
    if (implicitActive) {
      const el = implicitRef.current;
      if (el) {
        const delta = el.getBoundingClientRect().top - container.getBoundingClientRect().top - 8;
        container.scrollTop += delta;
      }
      return;
    }
    // Otherwise scroll the highlight into view ONLY when it is not already visible.
    if (!mark) return;
    const c = container.getBoundingClientRect();
    const m = mark.getBoundingClientRect();
    if (shouldScroll({ top: m.top, bottom: m.bottom }, { top: c.top, bottom: c.bottom })) {
      mark.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [highlightKey, implicitActive]);

  if (!open) {
    return (
      <div className="flex w-11 shrink-0 flex-col items-center border-r border-border bg-surface py-3">
        <button
          aria-label="Show run details"
          onClick={onToggle}
          className="rounded p-1.5 text-ink-muted transition-colors hover:bg-accent-soft hover:text-ink"
        >
          <span className="text-lg leading-none">›</span>
        </button>
        <span
          className="mt-3 text-[10px] uppercase tracking-wide text-ink-muted"
          style={{ writingMode: "vertical-rl" }}
        >
          Run details
        </span>
      </div>
    );
  }

  const startDrag = (e: ReactMouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = width;
    const onMove = (ev: MouseEvent) => {
      const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startW + (ev.clientX - startX)));
      onWidthChange(next);
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
  };

  const segments = buildSegments(prompt, highlightSpans);
  let markAssigned = false;

  return (
    <aside
      className="relative flex shrink-0 flex-col border-r border-border bg-surface"
      style={{ width }}
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold text-ink">Run details</h2>
        <button
          aria-label="Hide run details"
          onClick={onToggle}
          className="rounded p-1 text-ink-muted transition-colors hover:bg-accent-soft hover:text-ink"
        >
          <span className="text-lg leading-none">‹</span>
        </button>
      </div>

      <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">
        {title && (
          <div>
            <div className="text-xs uppercase tracking-wide text-ink-muted">Title</div>
            <div className="mt-0.5 text-sm text-ink">{title}</div>
          </div>
        )}

        <div>
          <div className="text-xs uppercase tracking-wide text-ink-muted">Models compared</div>
          <ul className="mt-1 flex flex-col gap-1">
            {models.map((m) => (
              <li key={m} className="rounded bg-accent-soft px-2 py-1 text-xs text-ink">
                {m}
              </li>
            ))}
          </ul>
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          <div className="text-xs uppercase tracking-wide text-ink-muted">Prompt</div>
          {implicitActive && (
            <div
              ref={implicitRef}
              className="mt-1 scroll-mt-2 rounded border border-border bg-accent-soft/50 px-2 py-1 text-[11px] italic text-ink-muted"
            >
              This criterion isn’t tied to a specific part of the prompt.
            </div>
          )}
          <div className="mt-1 whitespace-pre-wrap rounded border border-border bg-bg p-2 text-xs leading-relaxed text-ink">
            {segments.map((seg, i) => {
              if (!seg.highlighted) return <span key={i}>{seg.text}</span>;
              const isFirst = !markAssigned;
              markAssigned = true;
              return (
                <mark
                  key={i}
                  ref={isFirst ? markRef : undefined}
                  className={
                    pinned
                      ? "rounded bg-[#FCE7A2] text-ink ring-1 ring-[#C79A2E]"
                      : "rounded bg-[#FBEFC3] text-ink"
                  }
                >
                  {seg.text}
                </mark>
              );
            })}
          </div>
        </div>
      </div>

      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize run details panel"
        onMouseDown={startDrag}
        className="group absolute right-0 top-0 z-10 h-full w-1.5 translate-x-1/2 cursor-col-resize"
      >
        <div className="mx-auto h-full w-0.5 bg-transparent transition-colors group-hover:bg-accent" />
      </div>
    </aside>
  );
}
