"use client";

/**
 * Dashboard.tsx
 * -------------
 * Axiom OS command center — "Bloomberg Terminal meets Notion."
 *
 * Layout:
 *   header             -> thesis strip, Global Command Search, Live/Demo toggle
 *   CommandKPIs        -> KPI cards + pipeline conversion funnel
 *   NetworkGraph       -> Reverse Sourcing collaboration graph + Structural Risks
 *   DealPipelineTable  -> 3-axis deal list (click a row to open the Overseer)
 *   OverseerPanel      -> slide-over: radar + F_S math + trust validation + chat
 *
 * Data source by mode:
 *   Demo mode -> fetchDealPipeline() (the labeled fixture roster, fully
 *                evaluated through the real agent mesh)
 *   Live mode -> getLiveOpportunities() (backend/main.py's LiveSessionState:
 *                starts empty, grows only from searches this session runs)
 *
 * The search bar is the only thing that can add a new row to Live mode.
 * A query that doesn't match the current roster triggers a real Tavily +
 * Anthropic enrichment pass server-side (see main.py's
 * _tavily_enrich_founder) -- Demo mode never does this, regardless of query.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Search, X, Loader2, Sliders, UserPlus } from "lucide-react";
import { themeCSS } from "../../lib/theme";
import {
  fetchDealPipeline,
  getLiveOpportunities,
  getMode,
  getPipelineOverview,
  getSourcingNetwork,
  searchOpportunities,
  setMode as apiSetMode,
} from "../../lib/api";
import type { DealRow, PipelineOverview, SourcingNetworkResult } from "../../lib/types";
import { findStructuralRisk } from "../../lib/networkMatch";
import CommandKPIs from "./CommandKPIs";
import NetworkGraph from "./NetworkGraph";
import DealPipelineTable from "./DealPipelineTable";
import OverseerPanel from "./OverseerPanel";
import ThesisConfigPanel from "./ThesisConfigPanel";
import ApplyForm from "./ApplyForm";
import MemoView from "./MemoView";

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

function CommandSearch({
  demoMode,
  onSearch,
  onClear,
  loading,
  active,
}: {
  demoMode: boolean;
  onSearch: (query: string) => void;
  onClear: () => void;
  loading: boolean;
  active: boolean;
}) {
  const [value, setValue] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSearch(value);
      }}
      className="flex min-w-[260px] flex-1 max-w-xl items-center gap-2 rounded-md border border-hair bg-panel-raised px-3 py-1.5 focus-within:border-accent/50"
    >
      {loading ? (
        <Loader2 size={13} className="animate-spin text-accent" />
      ) : (
        <Search size={13} className="text-dim" />
      )}
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={
          demoMode
            ? "Filter the roster — try “technical founder infra high trust score”"
            : "Search the roster, or a GitHub handle / startup name to live-enrich…"
        }
        className="flex-1 bg-transparent font-mono text-xs text-primary placeholder:text-dim focus:outline-none"
      />
      {active && (
        <button
          type="button"
          onClick={() => {
            setValue("");
            onClear();
          }}
          className="text-dim hover:text-primary"
        >
          <X size={13} />
        </button>
      )}
    </form>
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

  const [allRows, setAllRows] = useState<DealRow[]>([]);
  const [rowsLoading, setRowsLoading] = useState(true);
  const [rowsError, setRowsError] = useState<string | null>(null);

  const [searchActive, setSearchActive] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchMessage, setSearchMessage] = useState<string | null>(null);
  const [displayedRows, setDisplayedRows] = useState<DealRow[]>([]);

  const [selected, setSelected] = useState<DealRow | null>(null);
  const [showThesis, setShowThesis] = useState(false);
  const [showApply, setShowApply] = useState(false);
  const [memoRow, setMemoRow] = useState<DealRow | null>(null);

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

  const refreshOverviewAndNetwork = useCallback(async () => {
    setOverviewLoading(true);
    setNetworkLoading(true);
    const [overviewResult, networkResult] = await Promise.all([getPipelineOverview(), getSourcingNetwork()]);
    setOverview(overviewResult.data);
    setOverviewError(overviewResult.error);
    setOverviewLoading(false);
    setNetwork(networkResult.data);
    setNetworkError(networkResult.error);
    setNetworkLoading(false);
  }, []);

  const refreshAll = useCallback(async () => {
    setRowsLoading(true);
    setSearchActive(false);
    setSearchMessage(null);

    const [rowsResult] = await Promise.all([
      demoMode ? fetchDealPipeline() : getLiveOpportunities(),
      refreshOverviewAndNetwork(),
    ]);

    setAllRows(rowsResult.data ?? []);
    setRowsError(rowsResult.error);
    setRowsLoading(false);
  }, [demoMode, refreshOverviewAndNetwork]);

  useEffect(() => {
    refreshMode();
  }, [refreshMode]);

  useEffect(() => {
    refreshAll();
  }, [demoMode, refreshAll]);

  const handleSearch = useCallback(
    async (query: string) => {
      if (!query.trim()) {
        setSearchActive(false);
        setSearchMessage(null);
        return;
      }
      setSearchLoading(true);
      setSearchMessage(null);
      const result = await searchOpportunities(query);
      setSearchLoading(false);
      setSearchActive(true);

      if (!result.data) {
        setDisplayedRows([]);
        setSearchMessage(result.error);
        return;
      }

      setDisplayedRows(result.data.matches);
      setSearchMessage(result.data.message);

      // A live-enrichment hit adds a genuinely new row -- fold it into the
      // master roster and refresh the KPIs/network so they pick it up too.
      if (!demoMode && result.data.matches.length > 0) {
        setAllRows((prev) => {
          const byId = new Map(prev.map((r) => [r.opportunity_id, r]));
          result.data!.matches.forEach((m) => byId.set(m.opportunity_id, m));
          return Array.from(byId.values());
        });
        refreshOverviewAndNetwork();
      }
    },
    [demoMode, refreshOverviewAndNetwork]
  );

  const handleClearSearch = useCallback(() => {
    setSearchActive(false);
    setSearchMessage(null);
  }, []);

  const handleApplied = useCallback(
    (row: DealRow) => {
      setAllRows((prev) => {
        const byId = new Map(prev.map((r) => [r.opportunity_id, r]));
        byId.set(row.opportunity_id, row);
        return Array.from(byId.values());
      });
      refreshOverviewAndNetwork();
    },
    [refreshOverviewAndNetwork]
  );

  const visibleRows = searchActive ? displayedRows : allRows;

  const selectedNetworkRisk = useMemo(
    () => (selected ? findStructuralRisk(network, selected) : null),
    [network, selected]
  );

  return (
    <div className="axiom-root min-h-screen font-sans">
      <style>{themeCSS}</style>

      <header className="sticky top-0 z-30 flex flex-wrap items-center gap-3 border-b border-hair bg-void/95 px-6 py-3 backdrop-blur">
        <div className="flex shrink-0 items-center gap-4">
          <h1 className="font-mono text-sm font-bold tracking-widest text-primary">AXIOM&nbsp;OS</h1>
          <span className="hidden font-mono text-[10px] uppercase tracking-wider text-dim lg:inline">
            thesis: dev tools · infra · agentic systems — pre-seed
          </span>
        </div>

        <CommandSearch
          demoMode={demoMode}
          onSearch={handleSearch}
          onClear={handleClearSearch}
          loading={searchLoading}
          active={searchActive}
        />

        <div className="flex shrink-0 items-center gap-2">
          {connectionError && <span className="font-mono text-[10px] text-bear">{connectionError}</span>}
          <button
            onClick={() => setShowThesis(true)}
            className="flex items-center gap-1.5 rounded-md border border-hair bg-panel-raised px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-muted transition-colors hover:border-accent/50 hover:text-primary"
          >
            <Sliders size={12} /> Thesis
          </button>
          <button
            onClick={() => setShowApply(true)}
            className="flex items-center gap-1.5 rounded-md border border-accent/40 bg-accent/10 px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-accent transition-colors hover:bg-accent/20"
          >
            <UserPlus size={12} /> Apply
          </button>
          <ModeToggle demoMode={demoMode} onToggle={toggleMode} connected={connected} />
        </div>
      </header>

      {searchActive && searchMessage && (
        <div className="border-b border-hair bg-panel-inset px-6 py-1.5">
          <p className="font-mono text-[10px] text-dim">{searchMessage}</p>
        </div>
      )}

      <main className="flex flex-col gap-5 px-6 py-6">
        <CommandKPIs overview={overview} loading={overviewLoading} error={overviewError} />

        <NetworkGraph data={network} loading={networkLoading} error={networkError} />

        <DealPipelineTable
          rows={visibleRows}
          loading={rowsLoading}
          error={rowsError}
          selectedId={selected?.opportunity_id ?? null}
          onSelect={setSelected}
          onGenerateMemo={setMemoRow}
        />
      </main>

      <OverseerPanel row={selected} networkRisk={selectedNetworkRisk} onClose={() => setSelected(null)} />

      {showThesis && (
        <ThesisConfigPanel
          onClose={() => setShowThesis(false)}
          onSaved={refreshAll}
        />
      )}
      {showApply && <ApplyForm onClose={() => setShowApply(false)} onSubmitted={handleApplied} />}
      {memoRow && <MemoView row={memoRow} onClose={() => setMemoRow(null)} />}
    </div>
  );
}
