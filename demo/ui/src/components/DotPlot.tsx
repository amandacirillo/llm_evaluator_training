import type { ModelResult } from "../types";
import { consistencyLabel, mean } from "../lib/beeswarm";

interface Props {
  models: ModelResult[];
}

const GOOD = "#2F8F5B"; // consistent
const WARN = "#B5730C"; // variable
const MEAN = "#9CA3AF"; // dashed average line (light gray — shows on white)
const LABEL = "#374151"; // dot score labels
const AVG_LABEL = "#6B7280"; // average value label

// Wide viewBox so the plot fills the horizontal space; width:100% scales it to
// the card, so the line stretches across the available room.
const VBW = 1060;
const PLOT_X0 = 132; // after the model-name gutter
const PLOT_X1 = 880; // before the value + label gutter
const PLOT_W = PLOT_X1 - PLOT_X0;
const BAND_H = 58; // taller band → 1 score unit is a bigger vertical step
const PAD = 9; // vertical padding inside the band (keeps dots off the edges)
const MIN_SPAN = 3; // so a small (≤2, consistent) spread stays gentle, not band-filling
const ROW_GAP = 22;
const ROW_H = BAND_H + ROW_GAP;
const TOP = 20;

/**
 * Run consistency — a per-model line chart (sparkline) over the N runs. Each run
 * is a labeled point (x = run order, y = score) connected by a line; a flat line
 * = consistent, an up-and-down line = variable. A dashed line marks the average
 * (its value is labeled). All rows share a trimmed score scale so the wiggle is
 * proportional to real variation. Every score is labeled — no hover needed.
 */
export default function DotPlot({ models }: Props) {
  const rows = models
    .filter((m) => m.sampling && m.sampling.generated > 0)
    .map((m) => ({ model: m.model, s: m.sampling! }));
  if (!rows.length) return null;

  const total = rows[0].s.total_criteria || 1;
  // Fit the y-scale to the actual observed range (shared across models) so
  // variability fills the band; a minimum span keeps a small (≤2) spread gentle.
  const allScores = rows.flatMap((r) => r.s.scores ?? []);
  const dataMin = allScores.length ? Math.min(...allScores) : 0;
  const dataMax = allScores.length ? Math.max(...allScores) : total;
  const range = dataMax - dataMin;
  const span = Math.max(range, MIN_SPAN);
  const height = TOP + rows.length * ROW_H + 8;

  const xOf = (k: number, n: number) =>
    n <= 1 ? (PLOT_X0 + PLOT_X1) / 2 : PLOT_X0 + (k / (n - 1)) * PLOT_W;

  return (
    <svg
      viewBox={`0 0 ${VBW} ${height}`}
      width="100%"
      role="img"
      aria-label="Run consistency: each model's score across its runs"
    >
      {rows.map((r, i) => {
        const scores = r.s.scores ?? [];
        const bandTop = TOP + i * ROW_H;
        const bandBottom = bandTop + BAND_H;
        const bandCenter = bandTop + BAND_H / 2;
        const yOf = (score: number) =>
          range === 0
            ? bandCenter // all runs identical → flat line, centered
            : bandBottom - PAD - ((score - dataMin) / span) * (BAND_H - 2 * PAD);

        const m = mean(scores);
        const isConsistent = consistencyLabel(scores) === "Consistent";
        const color = isConsistent ? GOOD : WARN;
        const name = r.model.length > 22 ? r.model.slice(0, 21) + "…" : r.model;
        const pts = scores.map((s, k) => `${xOf(k, scores.length)},${yOf(s)}`).join(" ");

        return (
          <g key={r.model}>
            {/* dashed average line */}
            <line
              x1={PLOT_X0}
              x2={PLOT_X1}
              y1={yOf(m)}
              y2={yOf(m)}
              stroke={MEAN}
              strokeWidth={1}
              strokeDasharray="4 3"
            />

            {/* model name (left) */}
            <text x={10} y={bandCenter + 4} fontSize={13} fontWeight={600} fill="#1B2A4A">
              {name}
              <title>{r.model}</title>
            </text>

            {/* connected line through the runs */}
            {scores.length > 1 && (
              <polyline points={pts} fill="none" stroke={color} strokeWidth={2} />
            )}
            {/* a dot per run, with its score labeled above */}
            {scores.map((s, k) => {
              const cx = xOf(k, scores.length);
              const cy = yOf(s);
              return (
                <g key={k}>
                  <circle cx={cx} cy={cy} r={4} fill={color} stroke="#FFFFFF" strokeWidth={1} />
                  <text x={cx} y={cy - 8} fontSize={10} fontWeight={600} fill={LABEL} textAnchor="middle">
                    {s}
                  </text>
                </g>
              );
            })}

            {/* average value — labeled at the dashed line's height, in the gutter */}
            <text x={PLOT_X1 + 12} y={yOf(m) + 4} fontSize={11} fill={AVG_LABEL}>
              avg {m.toFixed(1)}/{total}
            </text>

            {/* consistent / variable (far-right column, its own x) */}
            <text x={PLOT_X1 + 108} y={bandCenter + 4} fontSize={13} fontWeight={700} fill={color}>
              {isConsistent ? "consistent" : "variable"}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
