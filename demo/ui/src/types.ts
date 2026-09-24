/** How a criterion is graded and where it came from. */
export type CriterionTag = "auto" | "judged";
export type CriterionSource = "quote" | "implicit";

/** A character span [from, to) into the prompt text. */
export type Span = [number, number];

export interface AutoCheck {
  kind: string;
  expected?: number;
}

export interface ChecklistItem {
  id: string;
  text: string;
  /** Grading route. Optional for back-compat with older payloads. */
  tag?: CriterionTag;
  /** Frozen rubric shown to graders. */
  pass_means?: string;
  fail_means?: string;
  /** Provenance: a verbatim prompt quote, or "implicit" (tied to no specific text). */
  source?: CriterionSource;
  source_quote?: string;
  /** App-computed offsets of source_quote in the prompt ([] for implicit). */
  spans?: Span[];
  /** Present only when tag === "auto". */
  check?: AutoCheck;
}

export type Verdict = "PASS" | "FAIL";

export interface ItemVerdict {
  id: string;
  verdict: Verdict;
  /** One-line reason shown on hover; empty for passes. */
  note: string;
  /** Council split — shown as a subtle low-confidence marker. */
  low_confidence?: boolean;
  /** No judge was available to score this cell — shown as a neutral "—", not ✗. */
  no_votes?: boolean;
}

/** Per-model variability across the N samples. */
export interface SamplingSummary {
  generated: number;
  graded: number;
  total_criteria: number;
  /** One score (criteria passed) per generated sample — the dots of the plot. */
  scores: number[];
  avg_score: number;
  min_score: number;
  max_score: number;
  stdev: number;
}

export interface ModelResult {
  model: string;
  output: string | null;
  error: string | null;
  pass_count: number;
  total: number;
  pass_pct: number;
  items: ItemVerdict[];
  sampling?: SamplingSummary;
}

export type RunMode = "output_only" | "scoring";

export interface RunResult {
  title: string | null;
  mode?: RunMode;
  checklist?: ChecklistItem[];
  /** Judges actually used (transparency only — never a ranking/winner). */
  council?: string[];
  /** Configured judges the proxy didn't serve (shown as a heads-up). */
  council_unavailable?: string[];
  /** Configured judges excluded because they were a model under test. */
  council_excluded?: string[];
  models: ModelResult[];
}

/** Partial output streamed before scoring completes. */
export interface StreamedOutput {
  model: string;
  output: string | null;
  error: string | null;
}

export interface ModelsResponse {
  models: string[];
  source: "config" | "proxy" | "config-unverified" | "fallback";
}
