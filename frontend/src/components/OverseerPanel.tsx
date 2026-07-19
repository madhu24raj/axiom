"use client";

/**
 * OverseerPanel.tsx
 * -----------------
 * "The Overseer" -- the human partner's terminal into the agent mesh's exact
 * chain of thought, now with a live Q&A channel. Three sections:
 *   1. A Recharts RadarChart plotting the 3 independent axes + a real
 *      momentum vector (direction, velocity, acceleration -- see
 *      scoring.py's MomentumTracker; never a hardcoded arrow).
 *   2. A terminal-log trace: the decayed Founder Score (F_S) built up
 *      signal-by-signal, Market/Idea-vs-Market reasoning steps, and the
 *      Bayesian Trust Score validation with real evidence excerpts.
 *   3. An Overseer chat: ask about this ONE deal's numbers. In Demo mode
 *      this is answered by a deterministic, fully-offline explainer that
 *      reads the real numbers straight out of the context below (see
 *      main.py's _deterministic_overseer_reply); in Live mode it's a real
 *      Anthropic API call, still constrained by a system prompt that
 *      forbids introducing new unverified facts about the individual.
 */

import { useState } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";
import { X, Sigma, FlaskConical, Send, ShieldAlert, Bot, Sparkles, Mail } from "lucide-react";
import type {
  ColdStartRead,
  DealRow,
  FounderScoreBreakdown,
  OverseerChatTurn,
  ReasoningStep,
  StructuralRisk,
} from "../../lib/types";
import { draftOutreach, postOverseerChat } from "../../lib/api";

function fmtScore(score: number | null): string {
  return score === null ? "—" : score.toFixed(1);
}

function MomentumReadout({ row }: { row: DealRow }) {
  const m = row.momentum;
  const tone =
    m.direction === "up" ? "text-bull" : m.direction === "down" ? "text-bear" : m.direction === "pivot" ? "text-accent" : "text-neutral";
  return (
    <div className="flex flex-col items-end gap-0.5">
      <span className={`font-mono text-sm ${tone}`}>
        Momentum {m.arrow} {m.direction}
        {m.accelerating && <span className="ml-1 text-[10px] opacity-80">(accelerating)</span>}
      </span>
      <span className="font-mono text-[9px] text-dim">
        v={m.velocity.toFixed(2)}
        {m.prior_velocity !== null && `, prior=${m.prior_velocity.toFixed(2)}`} · {m.basis}
      </span>
    </div>
  );
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

  return (
    <div className="border-b border-hair px-5 py-4">
      <div className="flex items-start justify-between gap-3">
        <h4 className="font-mono text-xs uppercase tracking-wider text-muted">3-Axis Radar</h4>
        <MomentumReadout row={row} />
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
      <p className="mt-1 font-mono text-[10px] text-dim">{row.momentum.note}</p>
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

function ColdStartSection({ row }: { row: DealRow }) {
  const meta = row.founder?.metadata;
  const history = meta?.cold_start_history as ColdStartRead[] | undefined;
  if (!meta?.is_cold_start || !history || history.length === 0) return null;
  return (
    <div className="mb-6">
      <div className="mb-2 flex items-center gap-2">
        <Sparkles size={13} className="text-accent" />
        <h4 className="font-mono text-xs uppercase tracking-wider text-muted">Cold-Start Assessment</h4>
      </div>
      <p className="mb-2 font-sans text-[11px] leading-relaxed text-muted">
        No GitHub / funding / network signal on file — the displayed Founder score is a recency-weighted
        blend of the application-text read(s) below, NOT the decayed multi-source formula. Each read
        carries an explicit range instead of false precision.
      </p>
      <ul className="space-y-2">
        {history.map((h, i) => (
          <li key={i} className="rounded border border-hair bg-panel-raised px-3 py-2">
            <div className="flex items-center justify-between font-mono text-[10px]">
              <span className="text-primary">
                read #{i + 1}: {h.point_estimate_0to100.toFixed(1)}
                <span className="ml-1 text-dim">
                  [{h.low_estimate_0to100.toFixed(0)}, {h.high_estimate_0to100.toFixed(0)}]
                </span>
              </span>
              <span className="text-dim">{h.primary_signal}</span>
            </div>
            <p className="mt-1 font-sans text-[10px] leading-relaxed text-dim">
              {h.rationale.replace(/^\[DEMO heuristic\]\s*/, "")}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function OutreachSection({ row }: { row: DealRow }) {
  const [draft, setDraft] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDraft() {
    setLoading(true);
    setError(null);
    const res = await draftOutreach(row);
    setLoading(false);
    if (res.data) {
      setDraft(res.data.draft);
      setNote(res.data.note);
    } else {
      setError(res.error);
    }
  }

  return (
    <div className="mb-6">
      <div className="mb-2 flex items-center gap-2">
        <Mail size={13} className="text-axis-idea" />
        <h4 className="font-mono text-xs uppercase tracking-wider text-muted">Activate — Outreach</h4>
      </div>
      {!draft && (
        <button
          onClick={handleDraft}
          disabled={loading}
          className="rounded border border-hair px-3 py-1.5 font-mono text-[11px] text-muted hover:border-accent/50 hover:text-primary disabled:opacity-50"
        >
          {loading ? "Drafting…" : "Draft outreach from computed signals"}
        </button>
      )}
      {error && <p className="font-mono text-[10px] text-bear">{error}</p>}
      {draft && (
        <div className="rounded border border-hair bg-panel-raised px-3 py-2.5">
          <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-primary">
            {draft.replace(/^\[DEMO DRAFT — for human review before sending\]\s*/, "")}
          </pre>
          {note && <p className="mt-2 border-t border-hair pt-2 font-mono text-[9px] text-dim">{note}</p>}
        </div>
      )}
    </div>
  );
}

function TrustSection({ row }: { row: DealRow }) {
  if (row.trust_scores.length === 0) return null;
  return (
    <div className="mb-6">
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

function OverseerChat({ row, networkRisk }: { row: DealRow; networkRisk: StructuralRisk | null }) {
  const [turns, setTurns] = useState<OverseerChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const suggestions = ["Why did the trust score decay?", "How fragile is this node in the network?", "Break down F_S"];

  async function send(message: string) {
    if (!message.trim() || sending) return;
    setSending(true);
    setError(null);
    setTurns((t) => [...t, { role: "user", text: message }]);
    setInput("");

    const context = { ...row, network_risk: networkRisk };
    const result = await postOverseerChat(context, {}, message);
    if (result.data) {
      setTurns((t) => [...t, { role: "assistant", text: result.data!.reply }]);
    } else {
      setError(result.error);
    }
    setSending(false);
  }

  return (
    <div className="flex flex-col border-t border-hair">
      <div className="flex items-center gap-2 px-5 py-3">
        <Bot size={13} className="text-accent" />
        <h4 className="font-mono text-xs uppercase tracking-wider text-muted">Ask the Overseer</h4>
      </div>

      {turns.length === 0 && (
        <div className="flex flex-wrap gap-1.5 px-5 pb-3">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => send(s)}
              className="rounded border border-hair px-2 py-1 font-mono text-[10px] text-muted hover:border-accent/50 hover:text-primary"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {turns.length > 0 && (
        <div className="axiom-scrollbar max-h-52 overflow-y-auto px-5 pb-3">
          <ul className="flex flex-col gap-2.5">
            {turns.map((t, i) => (
              <li key={i} className={t.role === "user" ? "text-right" : "text-left"}>
                <span
                  className={`inline-block max-w-[90%] rounded px-2.5 py-1.5 text-left font-mono text-[11px] leading-relaxed ${
                    t.role === "user" ? "bg-panel-raised text-primary" : "bg-panel-inset text-muted"
                  }`}
                >
                  {t.text}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && <p className="px-5 pb-2 font-mono text-[10px] text-bear">{error}</p>}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex items-center gap-2 border-t border-hair px-4 py-2.5"
      >
        <span className="font-mono text-xs text-accent">&gt;</span>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this deal's numbers…"
          className="flex-1 bg-transparent font-mono text-xs text-primary placeholder:text-dim focus:outline-none"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="rounded border border-hair p-1.5 text-muted hover:border-accent/50 hover:text-primary disabled:opacity-40"
        >
          <Send size={12} />
        </button>
      </form>
    </div>
  );
}

export default function OverseerPanel({
  row,
  networkRisk,
  onClose,
}: {
  row: DealRow | null;
  networkRisk: StructuralRisk | null;
  onClose: () => void;
}) {
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
        <ColdStartSection row={row} />
        <TraceLog label="Market Axis — Reasoning Trace" trace={row.market?.reasoning_trace ?? []} />
        <TraceLog label="Idea vs. Market Axis — Reasoning Trace" trace={row.idea_vs_market?.reasoning_trace ?? []} />
        <TrustSection row={row} />
        <OutreachSection row={row} />
        {networkRisk && (
          <div>
            <div className="mb-2 flex items-center gap-2">
              <ShieldAlert size={13} className="text-risk-critical" />
              <h4 className="font-mono text-xs uppercase tracking-wider text-muted">Network Structural Risk</h4>
            </div>
            <p className="font-sans text-xs leading-relaxed text-muted">{networkRisk.narrative}</p>
          </div>
        )}
      </div>

      <OverseerChat row={row} networkRisk={networkRisk} />
    </div>
  );
}
