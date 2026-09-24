import { describe, expect, it } from "vitest";
import { beeswarmOffsets, consistencyLabel, maxStack, mean, stackSlots } from "./beeswarm";

describe("stackSlots", () => {
  it("assigns a distinct 0-based slot within each score group", () => {
    expect(stackSlots([3, 3, 3])).toEqual([0, 1, 2]);
    expect(stackSlots([1, 2, 1])).toEqual([0, 0, 1]);
  });
  it("all 10 dots at one score get distinct slots (countable)", () => {
    const slots = stackSlots(new Array(10).fill(4));
    expect(new Set(slots).size).toBe(10);
  });
  it("empty in, empty out", () => {
    expect(stackSlots([])).toEqual([]);
  });
});

describe("beeswarmOffsets", () => {
  it("returns one offset per input", () => {
    expect(beeswarmOffsets([1, 2, 3, 3]).length).toBe(4);
    expect(beeswarmOffsets([])).toEqual([]);
  });

  it("centres a same-score group and keeps every dot distinct (countable)", () => {
    const offs = beeswarmOffsets([3, 3, 3]);
    expect(offs).toEqual([-1, 0, 1]);
    expect(new Set(offs).size).toBe(3); // no two coincide
  });

  it("handles even groups symmetrically", () => {
    expect(beeswarmOffsets([5, 5])).toEqual([-0.5, 0.5]);
  });

  it("only offsets within a score group, not across scores", () => {
    // indices 0 & 2 share score 1; index 1 is alone at score 2.
    expect(beeswarmOffsets([1, 2, 1])).toEqual([-0.5, 0, 0.5]);
  });

  it("all 10 dots at one score are individually placed (none overlap)", () => {
    const offs = beeswarmOffsets(new Array(10).fill(4));
    expect(offs.length).toBe(10);
    expect(new Set(offs).size).toBe(10); // countable
  });
});

describe("maxStack / mean", () => {
  it("maxStack is the largest same-score count", () => {
    expect(maxStack([1, 1, 2, 3, 3, 3])).toBe(3);
    expect(maxStack([])).toBe(0);
  });
  it("mean averages", () => {
    expect(mean([1, 2, 3])).toBe(2);
    expect(mean([])).toBe(0);
  });
});

describe("consistencyLabel", () => {
  it("all-equal is Consistent", () => {
    expect(consistencyLabel([3, 3, 3, 3])).toBe("Consistent");
  });
  it("within 1 point is Consistent", () => {
    expect(consistencyLabel([3, 4, 3, 4])).toBe("Consistent");
  });
  it("a 2-point spread is Consistent (boundary, max − min === 2)", () => {
    expect(consistencyLabel([3, 5])).toBe("Consistent");
  });
  it("a 3-point spread is Variable (just past the boundary)", () => {
    expect(consistencyLabel([2, 5])).toBe("Variable");
  });
  it("a wider spread is Variable", () => {
    expect(consistencyLabel([1, 5, 3])).toBe("Variable");
  });
  it("a single run is Consistent", () => {
    expect(consistencyLabel([2])).toBe("Consistent");
  });
});
