/** Pure helpers for the run-consistency dot plot.
 *
 * Scores are integers (criteria passed per generated sample), so dots at the same
 * score would overlap. `beeswarmOffsets` fans same-score dots out vertically —
 * symmetric around the row centerline — so every dot is individually countable.
 * Kept free of React/DOM for unit testing.
 */

/** For each input score, a vertical offset (in dot-slots) that separates dots
 * sharing a score. Dots at distinct scores get offset 0; a group of `k` dots at
 * the same score gets offsets centered on 0 (…-1, 0, 1… or …-0.5, 0.5…), all
 * distinct so the group is countable. Returns one offset per input, in order. */
export function beeswarmOffsets(scores: number[]): number[] {
  const groups = new Map<number, number[]>();
  scores.forEach((s, i) => {
    const g = groups.get(s);
    if (g) g.push(i);
    else groups.set(s, [i]);
  });

  const offsets = new Array<number>(scores.length).fill(0);
  for (const idxs of groups.values()) {
    const k = idxs.length;
    idxs.forEach((originalIndex, j) => {
      offsets[originalIndex] = j - (k - 1) / 2;
    });
  }
  return offsets;
}

/** For each score, its 0-based position within its score group, for **upward**
 * stacking (0 sits on the baseline, 1 above it, …). Every dot gets a distinct slot
 * within its group so all dots stay countable. Returns one slot per input, in order. */
export function stackSlots(scores: number[]): number[] {
  const seen = new Map<number, number>();
  return scores.map((s) => {
    const n = seen.get(s) ?? 0;
    seen.set(s, n + 1);
    return n;
  });
}

/** Tallest stack — how many dots share the most-common score. Drives row height. */
export function maxStack(scores: number[]): number {
  const counts = new Map<number, number>();
  let max = 0;
  for (const s of scores) {
    const n = (counts.get(s) ?? 0) + 1;
    counts.set(s, n);
    if (n > max) max = n;
  }
  return max;
}

export function mean(scores: number[]): number {
  if (!scores.length) return 0;
  return scores.reduce((a, b) => a + b, 0) / scores.length;
}

/** Plain-language variability: "Consistent" when every run landed within 2 points
 * of every other (max − min ≤ 2), else "Variable". */
export function consistencyLabel(scores: number[]): "Consistent" | "Variable" {
  if (scores.length < 2) return "Consistent";
  const range = Math.max(...scores) - Math.min(...scores);
  return range <= 2 ? "Consistent" : "Variable";
}
