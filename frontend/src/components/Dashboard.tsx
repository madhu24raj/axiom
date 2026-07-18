"use client";

/**
 * Dashboard.tsx
 * -------------
 * Axiom OS command center — "Bloomberg Terminal meets Notion."
 *
 * Layout:
 *   header        -> thesis strip, connection state, Live/Demo toggle
 *   CommandKPIs   -> KPI cards + pipeline conversion funnel
 *   NetworkGraph  -> Reverse Sourcing collaboration graph + Structural Risks
 *   DealPipelineTable -> 3-axis deal list (click a row to open the Overseer)
 *   OverseerPanel -> slide-over: radar + F_S math + trust-score validation
 *
 * Every panel receives its own {data, loading, error} triple and is
 * responsible for its own "[Not Disclosed]" / "[Connection: Not Established]"
 * fallback -- Dashboard.tsx only orchestrates fetching, it never fabricates
 * a number when a fetch fails.
 *
 * Data contract: talks to the FastAPI backend in /backend via
 * NEXT_PUBLIC_API_BASE_URL.
 */

import { useCallback, useEffect, useState } from "react";
import { themeCSS } from "../../lib/theme";
import {
  fetchDealPipeline,
  getMode,
  getPipelineOverview,
  getSourcingNetwork,
  setMode as apiSetMode,
} from "../../lib/api";
import type { DealRow, PipelineOverview, SourcingNetworkResult } from "../../lib/types";
import CommandKPIs from "./CommandKPIs";
import NetworkGraph from "./NetworkGraph";
import DealPipelineTable from "./DealPipelineTable";
import OverseerPanel from "./OverseerPanel";

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
          !connected ? "bg-dim" : demoMode ? "bg-neutral" : "bg-accent"
        }`}
        style={!demoMode && connected ? { boxShadow: "0 0 6px var(--color-accent)" } : undefined}
      />
      <span className="font-mono text-[11px] uppercase tracking-wider text-muted group-hover:text-primary">
        {demoMode ? "Cached Demo" : "Live API"}
      </span>
    </button>
  );
}

export default function Dashboard() {
  const [demoMode, setDemoModeState] = useState(true);
  const [connected, setConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const [overview, setOverview] = useState<PipelineOverview | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  const [network, setNetwork] = useState<SourcingNetworkResult | null>(null);
  const [networkLoading, setNetworkLoading] = useState(true);
  const [networkError, setNetworkError] = useState<string | null>(null);

  const [rows, setRows] = useState<DealRow[]>([]);
  const [rowsLoading, setRowsLoading] = useState(true);
  const [rowsError, setRowsError] = useState<string | null>(null);

  const [selected, setSelected] = useState<DealRow | null>(null);

  const refreshMode = useCallback(async () => {
    const result = await getMode();
    if (result.data) {
      setDemoModeState(result.data.demo_mode);
      setConnected(true);
      setConnectionError(null);
    } else {
      setConnected(false);
      setConnectionError(result.error);
    }
  }, []);

  const toggleMode = useCallback(async () => {
    const result = await apiSetMode(!demoMode);
    if (result.data) setDemoModeState(result.data.demo_mode);
  }, [demoMode]);

  const refreshAll = useCallback(async () => {
    setOverviewLoading(true);
    setNetworkLoading(true);
    setRowsLoading(true);

    const [overviewResult, networkResult, rowsResult] = await Promise.all([
      getPipelineOverview(),
      getSourcingNetwork(),
      fetchDealPipeline(),
    ]);

    setOverview(overviewResult.data);
    setOverviewError(overviewResult.error);
    setOverviewLoading(false);

    setNetwork(networkResult.data);
    setNetworkError(networkResult.error);
    setNetworkLoading(false);

    setRows(rowsResult.data ?? []);
    setRowsError(rowsResult.error);
    setRowsLoading(false);
  }, []);

  useEffect(() => {
    refreshMode();
  }, [refreshMode]);

  useEffect(() => {
    refreshAll();
  }, [demoMode, refreshAll]);

  return (
    <div className="axiom-root min-h-screen font-sans">
      <style>{themeCSS}</style>

      <header className="sticky top-0 z-30 flex flex-wrap items-center justify-between gap-2 border-b border-hair bg-void/95 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-4">
          <h1 className="font-mono text-sm font-bold tracking-widest text-primary">AXIOM&nbsp;OS</h1>
          <span className="hidden font-mono text-[10px] uppercase tracking-wider text-dim sm:inline">
            thesis: dev tools · infra · agentic systems — pre-seed
          </span>
        </div>
        <div className="flex items-center gap-3">
          {connectionError && <span className="font-mono text-[10px] text-bear">{connectionError}</span>}
          <ModeToggle demoMode={demoMode} onToggle={toggleMode} connected={connected} />
        </div>
      </header>

      <main className="flex flex-col gap-5 px-6 py-6">
        <CommandKPIs overview={overview} loading={overviewLoading} error={overviewError} />

        <NetworkGraph data={network} loading={networkLoading} error={networkError} />

        <DealPipelineTable
          rows={rows}
          loading={rowsLoading}
          error={rowsError}
          selectedId={selected?.opportunity_id ?? null}
          onSelect={setSelected}
        />
      </main>

      <OverseerPanel row={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
