"use client";

/**
 * OverseerPanel.tsx
 * -----------------
 * "The Overseer" -- the human partner's terminal into the agent mesh's exact
 * chain of thought. Two halves:
 *   1. A Recharts RadarChart plotting the 3 independent axes + a momentum
 *      readout (never averaged into one number -- see agents.py docstring).
 *   2. A terminal-log style trace: the decayed Founder Score (F_S) built up
 *      signal-by-signal, the Market/Idea-vs-Market reasoning steps, and the
 *      Bayesian Trust Score validation for every claim that was checked --
 *      including the actual cached/live evidence excerpt, not a summary of
 *      one.
 */

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";
import { X, Sigma, FlaskConical } from "lucide-react";
import type { DealRow, FounderScoreBreakdown, ReasoningStep } from "../lib/types";

function fmtScore(score: number | null): string {
  return score === null ? "—" : score.toFixed(1);
}

function RadarSection({ row }: { row: DealRow }) {
  const axes: { key: keyof DealRow; label: string }[] = [
    { key: "founder", label: "Founder" },
    { key: "market", label: "Market" },
    { key: "idea_vs_market", label: "Idea vs Mkt" },
  ];
  const notDisclosed: string[] = [];
  const radarData = axes.map(({ key, label }) => {
    const axis = row[key] as DealRow["founder"];
    if (!axis || axis.score === null) notDisclosed.push(label);
    return { axis: label, score: axis?.score ?? 0 };
  });

  const momentumTone =
    row.momentum.direction === "up"
      ? "text-bull"
      : row.momentum.direction === "down"
      ? "text-bear"
      : "text-neutral";

  return (
    <div className="border-b border-hair px-5 py-4">
      <div className="flex items-center justify-between">
        <h4 className="font-mono text-xs uppercase tracking-wider text-muted">3-Axis Radar</h4>
        <span className={`font-mono text-sm ${momentumTone}`}>
          Momentum {row.momentum.arrow} {row.momentum.direction}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <RadarChart data={radarData} outerRadius="72%">
          <PolarGrid stroke="var(--color-hair)" />
          <PolarAngleAxis
            dataKey="axis"
            tick={{ fill: "var(--color-muted)", fontSize: 11, fontFamily: "IBM Plex Mono" }}
          />
          <PolarRadiusAxis
            angle={30}
            domain={[0, 100]}
            tick={{ fill: "var(--color-dim)", fontSize: 9 }}
            tickCount={3}
          />
          <Radar
            name="Score"
            dataKey="score"
            stroke="var(--color-accent)"
            fill="var(--color-accent)"
            fillOpacity={0.28}
            strokeWidth={2}
            isAnimationActive
          />
        </RadarChart>
      </ResponsiveContainer>
      {notDisclosed.length > 0 && (
        <p className="font-mono text-[10px] text-dim">
          Plotted at 0 for chart continuity, not asserted as zero — Not Disclosed: {notDisclosed.join(", ")}
        </p>
      )}
    </div>
  );
}

function FounderMathSection({ breakdown }: { breakdown: FounderScoreBreakdown | undefined }) {
  if (!breakdown) {
    return (
      <div className="mb-6">
        <h4 className="mb-2 font-mono text-xs uppercase tracking-wider text-muted">Founder Score (F_S)</h4>
        <p className="font-mono text-xs text-dim">[F_S breakdown: Not Disclosed]</p>
      </div>
    );
  }
  return (
    <div className="mb-6">
      <div className="mb-2 flex items-center gap-2">
        <Sigma size={13} className="text-axis-founder" />
        <h4 className="font-mono text-xs uppercase tracking-wider text-muted">Founder Score (F_S)</h4>
      </div>
      <p className="mb-2 rounded bg-panel-inset px-2.5 py-1.5 font-mono text-[11px] text-axis-founder">
        F_S = Σ w_i · S_i · e^(−λ·t_i) = {breakdown.founder_score.toFixed(2)} (λ = {breakdown.lambda_decay})
      </p>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse font-mono text-[10px]">
          <thead>
            <tr className="text-dim">
              {["source", "age(d)", "S_i", "w_i", "decay", "contrib", "% of F_S"].map((h) => (
                <th key={h} className="border-b border-hair px-1.5 py-1 text-left">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {breakdown.signals.map((s, i) => (
              <tr key={i} className="text-muted">
                <td className="px-1.5 py-1">{s.source}</td>
                <td className="px-1.5 py-1">{s.age_days}</td>
                <td className="px-1.5 py-1">{s.normalized_score.toFixed(2)}</td>
                <td className="px-1.5 py-1">{s.source_weight.toFixed(2)}</td>
                <td className="px-1.5 py-1">{s.decay_factor.toFixed(3)}</td>
                <td className="px-1.5 py-1 text-primary">{s.contribution.toFixed(2)}</td>
                <td className="px-1.5 py-1 text-accent">{s.contribution_pct_of_total.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TraceLog({ label, trace }: { label: string; trace: ReasoningStep[] }) {
  if (trace.length === 0) return null;
  return (
    <div className="mb-6">
      <h4 className="mb-2 font-mono text-xs uppercase tracking-wider text-muted">{label}</h4>
      <ol className="space-y-2 border-l border-hair pl-4">
        {trace.map((step, i) => (
          <li key={i} className="relative">
            <span className="absolute -left-[21px] top-1 h-1.5 w-1.5 rounded-full bg-accent" />
            <p className="font-mono text-[11px] uppercase tracking-wide text-dim">{step.step}</p>
            <p className="font-sans text-xs leading-relaxed text-muted">{step.detail}</p>
            {step.source_ref && <p className="mt-0.5 truncate font-mono text-[10px] text-dim">↳ {step.source_ref}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function TrustSection({ row }: { row: DealRow }) {
  if (row.trust_scores.length === 0) return null;
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <FlaskConical size={13} className="text-axis-market" />
        <h4 className="font-mono text-xs uppercase tracking-wider text-muted">Bayesian Trust-Score Validation</h4>
      </div>
      <p className="mb-2 rounded bg-panel-inset px-2.5 py-1.5 font-mono text-[11px] text-axis-market">
        posterior = (α + successes) / (α + β + n)
      </p>
      <ul className="space-y-2.5">
        {row.trust_scores.map((t, i) => (
          <li
            key={i}
            className={`rounded border px-3 py-2.5 ${t.flagged ? "border-bear/40 bg-bear/5" : "border-hair bg-panel-raised"}`}
          >
            <p className="font-sans text-xs text-primary">{t.claim_text}</p>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-[10px]">
              <span className={t.flagged ? "text-bear" : "text-bull"}>trust {Math.round(t.trust_score * 100)}%</span>
              <span className="text-dim">prior {Math.round(t.prior_mean * 100)}%</span>
              <span className="text-dim">
                n={t.posterior_successes + t.posterior_failures} (✓{t.posterior_successes} / ✗{t.posterior_failures})
              </span>
              {t.discrepancy_pct !== null && <span className="text-dim">Δ {t.discrepancy_pct.toFixed(1)}% vs. claim</span>}
            </div>
            {t.evidence.map((ev, j) => (
              <div key={j} className="mt-2 border-l-2 border-hair pl-2.5">
                {ev.evidence_excerpt && (
                  <p className="font-mono text-[10px] italic leading-relaxed text-muted">&gt; {ev.evidence_excerpt}</p>
                )}
                {ev.source_url && <p className="mt-0.5 truncate font-mono text-[9px] text-dim">↳ {ev.source_url}</p>}
              </div>
            ))}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function OverseerPanel({ row, onClose }: { row: DealRow | null; onClose: () => void }) {
  if (!row) return null;
  const founderBreakdown = row.founder?.metadata?.founder_score_breakdown as FounderScoreBreakdown | undefined;

  return (
    <div className="fixed inset-y-0 right-0 z-40 flex w-full max-w-lg flex-col border-l border-hair bg-panel shadow-2xl">
      <div className="flex items-center justify-between border-b border-hair px-5 py-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-dim">Agentic Traceability — Overseer</p>
          <h3 className="font-sans text-base font-semibold text-primary">{row.founder_name}</h3>
          <p className="font-mono text-[10px] text-dim">
            {row.sector} · F_S {fmtScore(row.founder?.score ?? null)} · MKT {fmtScore(row.market?.score ?? null)} ·
            PIVOT {fmtScore(row.idea_vs_market?.score ?? null)}
          </p>
        </div>
        <button
          onClick={onClose}
          className="rounded border border-hair px-2 py-1 font-mono text-xs text-muted hover:border-accent/50 hover:text-primary"
        >
          <X size={13} />
        </button>
      </div>

      <RadarSection row={row} />

      <div className="axiom-scrollbar flex-1 overflow-y-auto px-5 py-4">
        <FounderMathSection breakdown={founderBreakdown} />
        <TraceLog label="Market Axis — Reasoning Trace" trace={row.market?.reasoning_trace ?? []} />
        <TraceLog label="Idea vs. Market Axis — Reasoning Trace" trace={row.idea_vs_market?.reasoning_trace ?? []} />
        <TrustSection row={row} />
      </div>
    </div>
  );
}
