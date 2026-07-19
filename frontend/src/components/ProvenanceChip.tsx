"use client";

/**
 * ProvenanceChip.tsx
 * ------------------
 * A small, professional badge for data provenance. Replaces the old
 * paragraph-style "[Aggregated live from the current hackathon roster...]"
 * disclaimers with something that reads as a deliberate terminal UI element
 * rather than a leftover dev comment -- while still keeping the underlying
 * distinction visible: simulated vs. live vs. live-but-unverified data never
 * look identical on screen.
 */

import type { DataProvenance } from "../../lib/types";

const CONFIG: Record<string, { text: string; className: string }> = {
  demo_fixture: {
    text: "SIMULATED",
    className: "border-hair text-dim bg-panel-inset",
  },
  live_session: {
    text: "LIVE",
    className: "border-accent/40 text-accent bg-accent/10",
  },
  live_enriched: {
    text: "LIVE · ENRICHED",
    className: "border-accent/40 text-accent bg-accent/10",
  },
  live_awaiting_input: {
    text: "LIVE · AWAITING SEARCH",
    className: "border-hair text-dim bg-panel-inset",
  },
};

export default function ProvenanceChip({
  provenance,
  confidence,
}: {
  provenance: string;
  confidence?: string | null;
}) {
  const cfg = CONFIG[provenance] ?? { text: provenance.toUpperCase(), className: "border-hair text-dim bg-panel-inset" };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider ${cfg.className}`}
      title={confidence ? `single-pass confidence: ${confidence}` : undefined}
    >
      {cfg.text}
      {confidence && <span className="opacity-70">· {confidence}</span>}
    </span>
  );
}
