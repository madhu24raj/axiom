"use client";

/**
 * DealPipelineTable.tsx
 * ---------------------
 * The 3-axis deal list. Clicking a row selects it for the Overseer panel
 * (radar + traceability). Axis scores render "[Not Disclosed]" whenever the
 * backend returns score: null -- this file never fills that gap with a guess.
 */

import type { AxisResult, DealRow } from "../../lib/types";
import ProvenanceChip from "./ProvenanceChip";
import { FileText } from "lucide-react";

function TrendChip({ trend }: { trend?: "improving" | "declining" | "stable" }) {
  if (!trend) return null;
  const cfg =
    trend === "improving"
      ? { glyph: "▲", cls: "text-bull" }
      : trend === "declining"
      ? { glyph: "▼", cls: "text-bear" }
      : { glyph: "–", cls: "text-dim" };
  return (
    <span className={`ml-1 font-mono text-[9px] ${cfg.cls}`} title={`axis trend: ${trend}`}>
      {cfg.glyph}
    </span>
  );
}

function thesisReject(row: { thesis_check?: { detail: string } | null }): string | null {
  const d = row.thesis_check?.detail;
  return d && d.startsWith("REJECT") ? d : null;
}

function AxisScore({
  result,
  label,
  trend,
  rejectReason,
}: {
  result: AxisResult | null;
  label: string;
  trend?: "improving" | "declining" | "stable";
  rejectReason?: string | null;
}) {
  if (rejectReason) {
    // Axes are null BY DESIGN for thesis-rejected deals — render the gate
    // verdict, not a data-gap placeholder, so "filtered out" never reads as
    // "broken ingestion".
    return (
      <div className="flex flex-col gap-0.5" title={rejectReason}>
        <span className="font-mono text-[10px] uppercase tracking-wider text-dim">{label}</span>
        <span className="font-mono text-sm text-bear">✕ thesis</span>
      </div>
    );
  }
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
  const isColdStart = label === "F_S" && result.metadata?.is_cold_start;
  const history = result.metadata?.cold_start_history as { low_estimate_0to100: number; high_estimate_0to100: number }[] | undefined;
  const latestRange = history && history.length > 0 ? history[history.length - 1] : null;

  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-mono text-[10px] uppercase tracking-wider text-dim">
        {label}
        {isColdStart && <span className="ml-1 text-accent">~cold</span>}
        <TrendChip trend={trend} />
      </span>
      <span className={`font-mono text-sm font-semibold ${tone}`} title={latestRange ? `range [${latestRange.low_estimate_0to100}, ${latestRange.high_estimate_0to100}]` : undefined}>
        {result.score.toFixed(1)}
        <span className="ml-1 text-[10px] text-dim">conf {Math.round(result.confidence * 100)}%</span>
      </span>
    </div>
  );
}

function MomentumBadge({ momentum }: { momentum: DealRow["momentum"] }) {
  const tone =
    momentum.direction === "up"
      ? "text-bull"
      : momentum.direction === "down"
      ? "text-bear"
      : momentum.direction === "pivot"
      ? "text-accent"
      : "text-neutral";
  return (
    <span className={`font-mono text-base ${tone}`} title={momentum.note}>
      {momentum.arrow}
      {momentum.accelerating && <span className="ml-0.5 text-[9px] align-super">↑↑</span>}
    </span>
  );
}

export default function DealPipelineTable({
  rows,
  loading,
  error,
  selectedId,
  onSelect,
  onGenerateMemo,
}: {
  rows: DealRow[];
  loading: boolean;
  error: string | null;
  selectedId: string | null;
  onSelect: (row: DealRow) => void;
  onGenerateMemo: (row: DealRow) => void;
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
              {["Founder", "Sector", "Founder Axis", "Market Axis", "Idea vs. Market", "Momentum", "Memo", ""].map((h) => (
                <th key={h} className="px-4 py-2 text-left font-mono text-[10px] uppercase tracking-wider text-dim">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center font-mono text-xs text-dim">
                  Loading pipeline…
                </td>
              </tr>
            )}
            {!loading && (error || rows.length === 0) && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center font-mono text-xs text-dim">
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
                    <div className="flex items-center gap-2">
                      <p className="font-sans text-sm text-primary">{row.founder_name}</p>
                      <ProvenanceChip provenance={row.data_provenance} confidence={row.data_confidence} />
                      {thesisReject(row) && (
                        <span
                          className="rounded border border-bear/40 bg-panel-inset px-1 py-0.5 font-mono text-[9px] uppercase tracking-wider text-bear"
                          title={thesisReject(row) ?? undefined}
                        >
                          thesis reject
                        </span>
                      )}
                      {(row.applications_on_file ?? 1) > 1 && (
                        <span
                          className="rounded border border-hair bg-panel-inset px-1 py-0.5 font-mono text-[9px] text-dim"
                          title="Applications on file in Memory — Founder Score persists across these"
                        >
                          {row.applications_on_file}× in Memory
                        </span>
                      )}
                    </div>
                    <p className="font-mono text-[10px] text-dim">{row.company_name ?? row.opportunity_id}</p>
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded border border-hair bg-panel-inset px-1.5 py-0.5 font-mono text-[10px] text-muted">
                      {row.sector}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <AxisScore result={row.founder} label="F_S" trend={row.axis_trends?.founder} rejectReason={thesisReject(row)} />
                  </td>
                  <td className="px-4 py-3">
                    <AxisScore result={row.market} label="MKT" trend={row.axis_trends?.market} rejectReason={thesisReject(row)} />
                  </td>
                  <td className="px-4 py-3">
                    <AxisScore result={row.idea_vs_market} label="PIVOT" trend={row.axis_trends?.idea_vs_market} rejectReason={thesisReject(row)} />
                  </td>
                  <td className="px-4 py-3">
                    <MomentumBadge momentum={row.momentum} />
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onGenerateMemo(row);
                      }}
                      className="flex items-center gap-1 rounded border border-hair px-2 py-1 font-mono text-[10px] text-muted hover:border-accent/50 hover:text-primary"
                    >
                      <FileText size={11} /> memo
                    </button>
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
