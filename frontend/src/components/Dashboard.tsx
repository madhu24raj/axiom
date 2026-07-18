"use client";

/**
 * Dashboard.tsx
 * -------------
 * The VC Brain investor command center — "Bloomberg Terminal meets Notion."
 *
 * Design system (see accompanying DESIGN_NOTES.md for the full token list):
 *   - bg-void #0A0C10 / bg-panel #12151B / bg-panel-raised #181C24
 *   - border #262B35
 *   - text-primary #E8EAED / text-muted #8A93A3 / text-dim #545B68
 *   - accent (signal amber) #E8A33D — used ONLY for the live-mode indicator,
 *     the selected row, and primary actions, never as background wash
 *   - bull #4FD1A5 / bear #F06464 / neutral #8A93A3
 *   - Display + data: 'IBM Plex Mono'  |  UI copy: 'IBM Plex Sans'
 *
 * This file is intentionally dependency-light (plain Tailwind, no shadcn
 * import) so it drops into any Next.js 14 App Router project without extra
 * scaffolding. Swap the marked sections for shadcn/ui primitives if your
 * project already has them installed.
 *
 * Data contract: talks to the FastAPI backend in /backend (main.py) via
 * NEXT_PUBLIC_API_BASE_URL. Every fetch degrades gracefully — if the
 * backend is unreachable the UI shows an explicit "[Connection: Not
 * Established]" state rather than fabricating numbers.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types mirroring the backend's Pydantic / dataclass schemas
// ---------------------------------------------------------------------------
type MacroStance = "bull" | "neutral" | "bear";

interface ReasoningStep {
  step: string;
  detail: string;
  source_ref: string | null;
  timestamp: string;
}

interface AxisResult {
  axis: string;
  score: number | null;
  confidence: number;
  reasoning_trace: ReasoningStep[];
  raw_refs: string[];
}

interface TrustScoreResult {
  claim_text: string;
  trust_score: number;
  discrepancy_pct: number | null;
  flagged: boolean;
}

interface DealRow {
  opportunity_id: string;
  founder_name: string;
  sector: string;
  founder: AxisResult | null;
  market: AxisResult | null;
  idea_vs_market: AxisResult | null;
  trust_scores: TrustScoreResult[];
  momentum: { direction: "up" | "flat" | "down"; arrow: string };
}

// ---------------------------------------------------------------------------
// Small presentational primitives
// ---------------------------------------------------------------------------
function AxisScore({ result, label }: { result: AxisResult | null; label: string }) {
  if (!result || result.score === null) {
    return (
      <div className="flex flex-col gap-0.5">
        <span className="font-mono text-[10px] uppercase tracking-wider text-dim">{label}</span>
        <span className="font-mono text-sm text-dim">[Not Disclosed]</span>
      </div>
    );
  }
  const tone =
    result.score >= 66 ? "text-bull" : result.score <= 33 ? "text-bear" : "text-neutral";
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-mono text-[10px] uppercase tracking-wider text-dim">{label}</span>
      <span className={`font-mono text-sm font-semibold ${tone}`}>
        {result.score.toFixed(1)}
        <span className="ml-1 text-[10px] text-dim">conf {Math.round(result.confidence * 100)}%</span>
      </span>
    </div>
  );
}

function MomentumBadge({ momentum }: { momentum: DealRow["momentum"] }) {
  const tone =
    momentum.direction === "up" ? "text-bull" : momentum.direction === "down" ? "text-bear" : "text-neutral";
  return <span className={`font-mono text-base ${tone}`}>{momentum.arrow}</span>;
}

function ModeToggle({
  demoMode,
  onToggle,
  connected,
}: {
  demoMode: boolean;
  onToggle: () => void;
  connected: boolean;
}) {
  return (
    <button
      onClick={onToggle}
      className="group flex items-center gap-2 rounded-md border border-hair bg-panel-raised px-3 py-1.5 transition-colors hover:border-accent/50"
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          !connected ? "bg-dim" : demoMode ? "bg-neutral" : "bg-accent shadow-[0_0_6px_var(--tw-shadow-color)] shadow-accent"
        }`}
      />
      <span className="font-mono text-[11px] uppercase tracking-wider text-muted group-hover:text-primary">
        {demoMode ? "Cached Demo" : "Live API"}
      </span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Traceability slide-over — the "click any metric, see the chain-of-thought"
// requirement
// ---------------------------------------------------------------------------
function TracePanel({ row, onClose }: { row: DealRow | null; onClose: () => void }) {
  if (!row) return null;
  const axes: { label: string; result: AxisResult | null }[] = [
    { label: "Founder Axis", result: row.founder },
    { label: "Market Axis", result: row.market },
    { label: "Idea vs. Market Axis", result: row.idea_vs_market },
  ];

  return (
    <div className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-hair bg-panel shadow-2xl">
      <div className="flex items-center justify-between border-b border-hair px-5 py-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-dim">Traceability</p>
          <h3 className="font-sans text-base font-semibold text-primary">{row.founder_name}</h3>
        </div>
        <button
          onClick={onClose}
          className="rounded border border-hair px-2 py-1 font-mono text-xs text-muted hover:text-primary"
        >
          Close
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4">
        {axes.map(({ label, result }) => (
          <div key={label} className="mb-6">
            <div className="mb-2 flex items-center justify-between">
              <h4 className="font-mono text-xs uppercase tracking-wider text-muted">{label}</h4>
              <span className="font-mono text-xs text-dim">
                {result?.score !== null && result?.score !== undefined
                  ? result.score.toFixed(1)
                  : "[Not Disclosed]"}
              </span>
            </div>
            <ol className="space-y-2 border-l border-hair pl-4">
              {(result?.reasoning_trace ?? []).length === 0 && (
                <li className="font-sans text-xs text-dim">No reasoning steps recorded.</li>
              )}
              {result?.reasoning_trace.map((step, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[21px] top-1 h-1.5 w-1.5 rounded-full bg-accent" />
                  <p className="font-mono text-[11px] uppercase tracking-wide text-dim">{step.step}</p>
                  <p className="font-sans text-xs leading-relaxed text-muted">{step.detail}</p>
                  {step.source_ref && (
                    <p className="mt-0.5 truncate font-mono text-[10px] text-dim">↳ {step.source_ref}</p>
                  )}
                </li>
              ))}
            </ol>
          </div>
        ))}

        {row.trust_scores.length > 0 && (
          <div>
            <h4 className="mb-2 font-mono text-xs uppercase tracking-wider text-muted">
              Trust-Score Validation
            </h4>
            <ul className="space-y-2">
              {row.trust_scores.map((t, i) => (
                <li
                  key={i}
                  className={`rounded border px-3 py-2 ${
                    t.flagged ? "border-bear/40 bg-bear/5" : "border-hair bg-panel-raised"
                  }`}
                >
                  <p className="font-sans text-xs text-primary">{t.claim_text}</p>
                  <div className="mt-1 flex items-center justify-between font-mono text-[10px]">
                    <span className={t.flagged ? "text-bear" : "text-bull"}>
                      trust {Math.round(t.trust_score * 100)}%
                    </span>
                    {t.discrepancy_pct !== null && (
                      <span className="text-dim">Δ {t.discrepancy_pct.toFixed(1)}% vs. claim</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main dashboard
// ---------------------------------------------------------------------------
export default function Dashboard() {
  const [demoMode, setDemoMode] = useState(true);
  const [connected, setConnected] = useState(false);
  const [rows, setRows] = useState<DealRow[]>([]);
  const [selected, setSelected] = useState<DealRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMode = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/mode`);
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      setDemoMode(data.demo_mode);
      setConnected(true);
      setError(null);
    } catch {
      setConnected(false);
      setError("[Connection: Not Established — check API_BASE_URL / backend is running]");
    }
  }, []);

  const toggleMode = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/mode?demo_mode=${!demoMode}`, { method: "POST" });
      const data = await res.json();
      setDemoMode(data.demo_mode);
    } catch {
      setError("[Mode toggle failed — backend unreachable]");
    }
  }, [demoMode]);

  const fetchPipeline = useCallback(async () => {
    setLoading(true);
    try {
      const profilesRes = await fetch(`${API_BASE}/api/hackathon/profiles`);
      if (!profilesRes.ok) throw new Error(String(profilesRes.status));
      const profiles: any[] = await profilesRes.json();

      const evaluated = await Promise.all(
        profiles.map(async (p) => {
          const payload = {
            opportunity: {
              id: p.founder_id,
              sector: "dev tools",
              founder_score: 50,
              keywords: [p.project],
              idea_summary: p.project,
              engineering_signals: p.raw_signals,
            },
            founder_profile: {
              founder_id: p.founder_id,
              name: p.name,
              public_footprints: p.public_footprints,
              historical_signals: [
                {
                  source: "github",
                  timestamp: new Date().toISOString(),
                  normalized_score: Math.min(1, (p.raw_signals?.stars_7d ?? 0) / 25),
                  confidence: 0.7,
                  raw_data: {},
                  data_points: p.raw_signals,
                },
              ],
            },
            claims_to_verify: [],
          };
          const res = await fetch(`${API_BASE}/api/evaluate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const data = await res.json();
          return {
            opportunity_id: data.evaluation.opportunity_id,
            founder_name: p.name,
            sector: "dev tools",
            founder: data.evaluation.founder,
            market: data.evaluation.market,
            idea_vs_market: data.evaluation.idea_vs_market,
            trust_scores: data.evaluation.trust_scores,
            momentum: data.momentum,
          } as DealRow;
        })
      );
      setRows(evaluated);
      setError(null);
    } catch {
      setError("[Pipeline data unavailable — Not Disclosed]");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMode();
  }, [fetchMode]);

  useEffect(() => {
    fetchPipeline();
  }, [demoMode, fetchPipeline]);

  const sortedRows = useMemo(
    () => [...rows].sort((a, b) => (b.founder?.score ?? 0) - (a.founder?.score ?? 0)),
    [rows]
  );

  return (
    <div className="min-h-screen bg-void font-sans text-primary">
      <style>{`
        :root {
          --color-void: #0A0C10;
          --color-panel: #12151B;
          --color-panel-raised: #181C24;
          --color-hair: #262B35;
          --color-primary: #E8EAED;
          --color-muted: #8A93A3;
          --color-dim: #545B68;
          --color-accent: #E8A33D;
          --color-bull: #4FD1A5;
          --color-bear: #F06464;
          --color-neutral: #8A93A3;
        }
        .bg-void { background-color: var(--color-void); }
        .bg-panel { background-color: var(--color-panel); }
        .bg-panel-raised { background-color: var(--color-panel-raised); }
        .border-hair { border-color: var(--color-hair); }
        .text-primary { color: var(--color-primary); }
        .text-muted { color: var(--color-muted); }
        .text-dim { color: var(--color-dim); }
        .text-accent { color: var(--color-accent); }
        .bg-accent { background-color: var(--color-accent); }
        .border-accent { border-color: var(--color-accent); }
        .text-bull { color: var(--color-bull); }
        .text-bear { color: var(--color-bear); }
        .text-neutral { color: var(--color-neutral); }
        .bg-bull { background-color: var(--color-bull); }
        .bg-bear { background-color: var(--color-bear); }
        .font-mono { font-family: 'IBM Plex Mono', ui-monospace, monospace; }
        .font-sans { font-family: 'IBM Plex Sans', ui-sans-serif, system-ui; }
      `}</style>

      {/* Command header */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-hair bg-void/95 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-4">
          <h1 className="font-mono text-sm font-bold tracking-widest text-primary">
            THE&nbsp;VC&nbsp;BRAIN
          </h1>
          <span className="hidden font-mono text-[10px] uppercase tracking-wider text-dim sm:inline">
            thesis: dev tools · infra · agentic systems — pre-seed
          </span>
        </div>
        <div className="flex items-center gap-3">
          {error && <span className="font-mono text-[10px] text-bear">{error}</span>}
          <ModeToggle demoMode={demoMode} onToggle={toggleMode} connected={connected} />
        </div>
      </header>

      {/* Pipeline grid */}
      <main className="px-6 py-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-mono text-xs uppercase tracking-wider text-muted">
            Deal Pipeline — 3-Axis Screen
          </h2>
          <span className="font-mono text-[10px] text-dim">{sortedRows.length} opportunities</span>
        </div>

        <div className="overflow-hidden rounded-lg border border-hair">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-hair bg-panel">
                {["Founder", "Founder Axis", "Market Axis", "Idea vs. Market", "Momentum", ""].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-2 text-left font-mono text-[10px] uppercase tracking-wider text-dim"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center font-mono text-xs text-dim">
                    Loading pipeline…
                  </td>
                </tr>
              )}
              {!loading && sortedRows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center font-mono text-xs text-dim">
                    [Pipeline: Not Disclosed]
                  </td>
                </tr>
              )}
              {sortedRows.map((row) => (
                <tr
                  key={row.opportunity_id}
                  onClick={() => setSelected(row)}
                  className="cursor-pointer border-b border-hair bg-panel transition-colors last:border-0 hover:bg-panel-raised"
                >
                  <td className="px-4 py-3">
                    <p className="font-sans text-sm text-primary">{row.founder_name}</p>
                    <p className="font-mono text-[10px] text-dim">{row.sector}</p>
                  </td>
                  <td className="px-4 py-3">
                    <AxisScore result={row.founder} label="F_S" />
                  </td>
                  <td className="px-4 py-3">
                    <AxisScore result={row.market} label="MKT" />
                  </td>
                  <td className="px-4 py-3">
                    <AxisScore result={row.idea_vs_market} label="PIVOT" />
                  </td>
                  <td className="px-4 py-3">
                    <MomentumBadge momentum={row.momentum} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="font-mono text-[10px] text-dim">view trace →</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>

      <TracePanel row={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
