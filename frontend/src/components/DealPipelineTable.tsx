"use client";

/**
 * DealPipelineTable.tsx
 * ---------------------
 * The 3-axis deal list. Clicking a row selects it for the Overseer panel
 * (radar + traceability). Axis scores render "[Not Disclosed]" whenever the
 * backend returns score: null -- this file never fills that gap with a guess.
 */

import type { AxisResult, DealRow } from "../lib/types";

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

export default function DealPipelineTable({
  rows,
  loading,
  error,
  selectedId,
  onSelect,
}: {
  rows: DealRow[];
  loading: boolean;
  error: string | null;
  selectedId: string | null;
  onSelect: (row: DealRow) => void;
}) {
  return (
    <div className="rounded-lg border border-hair bg-panel">
      <div className="flex items-center justify-between border-b border-hair px-4 py-3">
        <h2 className="font-mono text-xs uppercase tracking-wider text-muted">
          Deal Pipeline — 3-Axis Screen
        </h2>
        <span className="font-mono text-[10px] text-dim">{rows.length} opportunities</span>
      </div>
      <div className="overflow-hidden">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-hair bg-panel-raised">
              {["Founder", "Sector", "Founder Axis", "Market Axis", "Idea vs. Market", "Momentum", ""].map((h) => (
                <th key={h} className="px-4 py-2 text-left font-mono text-[10px] uppercase tracking-wider text-dim">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center font-mono text-xs text-dim">
                  Loading pipeline…
                </td>
              </tr>
            )}
            {!loading && (error || rows.length === 0) && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center font-mono text-xs text-dim">
                  {error ?? "[Pipeline: Not Disclosed]"}
                </td>
              </tr>
            )}
            {!loading &&
              rows.map((row) => (
                <tr
                  key={row.opportunity_id}
                  onClick={() => onSelect(row)}
                  className={`cursor-pointer border-b border-hair transition-colors last:border-0 hover:bg-panel-raised ${
                    selectedId === row.opportunity_id ? "bg-panel-raised" : ""
                  }`}
                  style={
                    selectedId === row.opportunity_id
                      ? { boxShadow: "inset 2px 0 0 0 var(--color-accent)" }
                      : undefined
                  }
                >
                  <td className="px-4 py-3">
                    <p className="font-sans text-sm text-primary">{row.founder_name}</p>
                    <p className="font-mono text-[10px] text-dim">{row.opportunity_id}</p>
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded border border-hair bg-panel-inset px-1.5 py-0.5 font-mono text-[10px] text-muted">
                      {row.sector}
                    </span>
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
                    <span className="font-mono text-[10px] text-dim">
                      {selectedId === row.opportunity_id ? "viewing trace ●" : "view trace →"}
                    </span>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
