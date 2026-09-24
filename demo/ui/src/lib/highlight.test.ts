import { describe, expect, it } from "vitest";
import { buildSegments, isSpanVisible, shouldScroll, windowAround } from "./highlight";

describe("buildSegments", () => {
  it("marks a single span and leaves the rest unhighlighted", () => {
    const text = "Generate 5 questions.";
    const segs = buildSegments(text, [[9, 20]]);
    expect(segs.map((s) => s.text).join("")).toBe(text);
    const hi = segs.filter((s) => s.highlighted).map((s) => s.text);
    expect(hi).toEqual(["5 questions"]);
  });

  it("handles multiple, unsorted, overlapping spans", () => {
    const text = "aXXbYYc";
    const segs = buildSegments(text, [[3, 5], [1, 3], [4, 5]]);
    // spans merge into [1,5) (end exclusive) -> chars 1..4 -> "XXbY"
    const hi = segs.filter((s) => s.highlighted).map((s) => s.text);
    expect(hi).toEqual(["XXbY"]);
    expect(segs.map((s) => s.text).join("")).toBe(text);
  });

  it("returns a single unhighlighted segment when no spans", () => {
    expect(buildSegments("hello", [])).toEqual([{ text: "hello", highlighted: false }]);
  });

  it("clamps out-of-range spans", () => {
    const segs = buildSegments("abc", [[1, 99]]);
    expect(segs.filter((s) => s.highlighted).map((s) => s.text)).toEqual(["bc"]);
  });
});

describe("isSpanVisible / shouldScroll", () => {
  const container = { top: 100, bottom: 400 };

  it("visible span does not scroll", () => {
    expect(isSpanVisible({ top: 150, bottom: 200 }, container)).toBe(true);
    expect(shouldScroll({ top: 150, bottom: 200 }, container)).toBe(false);
  });

  it("span below the fold scrolls", () => {
    expect(isSpanVisible({ top: 500, bottom: 520 }, container)).toBe(false);
    expect(shouldScroll({ top: 500, bottom: 520 }, container)).toBe(true);
  });

  it("span above the fold scrolls", () => {
    expect(shouldScroll({ top: 40, bottom: 60 }, container)).toBe(true);
  });

  it("partially cut-off span scrolls", () => {
    expect(shouldScroll({ top: 380, bottom: 460 }, container)).toBe(true);
  });
});

describe("windowAround", () => {
  it("returns surrounding text with truncation flags", () => {
    const text = "0123456789ABCDE quote HERE more text 0123456789";
    const start = text.indexOf("quote HERE");
    const w = windowAround(text, [start, start + "quote HERE".length], 5);
    expect(w.quote).toBe("quote HERE");
    expect(w.before).toBe("BCDE ");
    expect(w.after).toBe(" more");
    expect(w.truncatedStart).toBe(true);
    expect(w.truncatedEnd).toBe(true);
  });

  it("no truncation near the edges", () => {
    const text = "short quote";
    const w = windowAround(text, [6, 11], 50);
    expect(w.quote).toBe("quote");
    expect(w.truncatedStart).toBe(false);
    expect(w.truncatedEnd).toBe(false);
  });
});
