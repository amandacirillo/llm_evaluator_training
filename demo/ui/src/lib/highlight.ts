/** Pure helpers for the criterion→prompt source highlighting.
 *
 * Kept free of React/DOM so they can be unit-tested directly. The DOM-facing
 * decision (does an element need scrolling into view?) is expressed as a pure
 * predicate over plain rectangles.
 */

export type Span = [number, number];

export interface Segment {
  text: string;
  highlighted: boolean;
}

/** Split `text` into contiguous segments, marking characters inside any span.
 * Overlapping/unsorted/out-of-range spans are normalized. */
export function buildSegments(text: string, spans: Span[]): Segment[] {
  const len = text.length;
  const clean = (spans || [])
    .map(([a, b]) => [Math.max(0, Math.min(a, b)), Math.min(len, Math.max(a, b))] as Span)
    .filter(([a, b]) => b > a)
    .sort((x, y) => x[0] - y[0]);

  // Merge overlaps.
  const merged: Span[] = [];
  for (const [a, b] of clean) {
    const last = merged[merged.length - 1];
    if (last && a <= last[1]) {
      last[1] = Math.max(last[1], b);
    } else {
      merged.push([a, b]);
    }
  }

  if (!merged.length) return text ? [{ text, highlighted: false }] : [];

  const segments: Segment[] = [];
  let cursor = 0;
  for (const [a, b] of merged) {
    if (a > cursor) segments.push({ text: text.slice(cursor, a), highlighted: false });
    segments.push({ text: text.slice(a, b), highlighted: true });
    cursor = b;
  }
  if (cursor < len) segments.push({ text: text.slice(cursor), highlighted: false });
  return segments;
}

export interface Rect {
  top: number;
  bottom: number;
}

/** Is the target rect fully within the container's visible band? */
export function isSpanVisible(target: Rect, container: Rect): boolean {
  return target.top >= container.top && target.bottom <= container.bottom;
}

/** Whether to scroll: only when the span is NOT already fully visible. */
export function shouldScroll(target: Rect, container: Rect): boolean {
  return !isSpanVisible(target, container);
}

export interface QuoteWindow {
  before: string;
  quote: string;
  after: string;
  truncatedStart: boolean;
  truncatedEnd: boolean;
}

/** A window of prompt text around a span, for the collapsed-panel popover. */
export function windowAround(text: string, span: Span, radius = 120): QuoteWindow {
  const [a, b] = [Math.max(0, span[0]), Math.min(text.length, span[1])];
  const start = Math.max(0, a - radius);
  const end = Math.min(text.length, b + radius);
  return {
    before: text.slice(start, a),
    quote: text.slice(a, b),
    after: text.slice(b, end),
    truncatedStart: start > 0,
    truncatedEnd: end < text.length,
  };
}
