"use client";

/**
 * CommandKPIs.tsx
 * ---------------
 * Top-level command strip: four KPI cards + the Sourced -> Screened ->
 * Diligence -> Approved conversion funnel. Every number comes straight from
 * PipelineOverview (main.py's /api/pipeline/overview), which aggregates the
 * live hackathon roster rather than hand-typing summary totals -- see the
 * `label` field rendered at the bottom for that provenance note.
 */

import { useMemo } from "react";
import { Target, TrendingUp, Gauge, Banknote, type LucideIcon } from "lucide-react";
import type { PipelineOverview } from "../lib/types";
import ProvenanceChip from "./ProvenanceChip";

function KPICard({
  icon: Icon,
  label,
  value,
  sublabel,
  tone = "primary",
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  sublabel?: string;
  tone?: "primary" | "accent" | "bull";
}) {
  const toneClass =
    tone === "accent" ? "text-accent" : tone === "bull" ? "text-bull" : "text-primary";
  return (
    <div className="flex flex-1 min-w-[180px] flex-col gap-2 rounded-lg border border-hair bg-panel px-4 py-3.5">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-wider text-dim">{label}</span>
        <Icon size={14} strokeWidth={1.75} />
      </div>
      <span className={`font-mono text-2xl font-semibold leading-none ${toneClass}`}>{value}</span>
      {sublabel && <span className="font-mono text-[10px] text-dim">{sublabel}</span>}
    </div>
  );
}

function FunnelBar({
  stage,
  count,
  maxCount,
  index,
  prevCount,
}: {
  stage: string;
  count: number;
  maxCount: number;
  index: number;
  prevCount: number | null;
}) {
  const widthPct = maxCount > 0 ? Math.max(4, (count / maxCount) * 100) : 4;
  const conversionPct =
    prevCount && prevCount > 0 ? Math.round((count / prevCount) * 100) : null;
  return (
    <div className="flex items-center gap-3">
      <span className="w-20 shrink-0 font-mono text-[10px] uppercase tracking-wider text-muted">
        {stage}
      </span>
      <div className="relative h-6 flex-1 rounded bg-panel-inset">
        <div
          className="h-6 rounded bg-accent/80 transition-all duration-500"
          style={{ width: `${widthPct}%` }}
        />
        <span className="absolute inset-y-0 left-2 flex items-center font-mono text-[11px] font-semibold text-void mix-blend-screen">
          {count}
        </span>
      </div>
      <span className="w-12 shrink-0 text-right font-mono text-[10px] text-dim">
        {conversionPct !== null ? `${conversionPct}%` : "—"}
      </span>
    </div>
  );
}

export default function CommandKPIs({
  overview,
  loading,
  error,
}: {
  overview: PipelineOverview | null;
  loading: boolean;
  error: string | null;
}) {
  const maxCount = useMemo(
    () => Math.max(1, ...(overview?.funnel.map((f) => f.count) ?? [1])),
    [overview]
  );

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr_1fr_1fr_1.4fr]">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-lg border border-hair bg-panel" />
        ))}
      </div>
    );
  }

  if (error || !overview) {
    return (
      <div className="rounded-lg border border-hair bg-panel px-4 py-3 font-mono text-xs text-dim">
        {error ?? "[KPI overview: Not Disclosed]"}
      </div>
    );
  }

  const { kpis, funnel } = overview;

  return (
    <div className="axiom-fade-in flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-[1fr_1fr_1fr_1fr_1.4fr]">
        <KPICard
          icon={Target}
          label="Total Opportunities"
          value={String(kpis.total_opportunities)}
          sublabel={`${kpis.thesis_pass_rate_pct}% clear thesis filter`}
        />
        <KPICard
          icon={TrendingUp}
          label="High Potential"
          value={String(kpis.high_potential_count)}
          sublabel={`F_S ≥ 55`}
          tone="bull"
        />
        <KPICard
          icon={Gauge}
          label="Avg Founder Score"
          value={kpis.avg_founder_score.toFixed(1)}
          sublabel="decayed, multi-source F_S"
        />
        <KPICard
          icon={Banknote}
          label="Capital Deployed"
          value={`$${(kpis.capital_deployed_usd / 1000).toFixed(0)}K`}
          sublabel={
            kpis.human_approval_required
              ? "human sign-off required to deploy"
              : `${kpis.check_size_usd.toLocaleString()} per check`
          }
          tone="accent"
        />

        <div className="flex flex-col justify-center gap-2 rounded-lg border border-hair bg-panel px-4 py-3.5">
          <span className="font-mono text-[10px] uppercase tracking-wider text-dim">
            Pipeline Conversion
          </span>
          <div className="flex flex-col gap-1.5">
            {funnel.map((f, i) => (
              <FunnelBar
                key={f.stage}
                stage={f.stage}
                count={f.count}
                maxCount={maxCount}
                index={i}
                prevCount={i > 0 ? funnel[i - 1].count : null}
              />
            ))}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <ProvenanceChip provenance={overview.provenance} />
        <span className="font-mono text-[10px] text-dim">{overview.label}</span>
      </div>
    </div>
  );
}
