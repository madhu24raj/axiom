# Axiom OS — Autonomous Venture Investment Operating System

(formerly "The VC Brain") An end-to-end sourcing -> screening -> diligence ->
decisioning pipeline, now with a Bloomberg-style quantitative command center:
a real-math Sourcing Network Graph, live-aggregated Command KPIs + pipeline
funnel, a 3-axis Radar per deal, and an Overseer traceability panel that
shows the exact decayed Founder Score and Bayesian trust-score math behind
every number.

Nothing new here is a "vain UI placeholder" — every visual is backed by a
real computation:

- **Sourcing Network Graph** — `backend/network_analysis.py` runs real
  NetworkX graph algorithms (eigenvector centrality, betweenness centrality,
  articulation points) plus a custom Dead-Man-Switch (DMS) fragility score
  that actually removes each node from a graph copy and measures how much
  of the network falls out of the giant component. The only "invented"
  part is the demo topology itself (who-collaborated-with-whom at a
  simulated hackathon), which is clearly labeled as such in
  `mock_data.py`; the math on top of it is never fabricated.
- **Command KPIs + Pipeline Funnel** — `backend/main.py`'s
  `/api/pipeline/overview` aggregates the live hackathon roster (Founder
  Score computed via the same `FounderScoreEngine` `/api/evaluate` uses,
  thesis-fit computed via the same `ThesisEngine`) rather than hand-typing
  summary totals, so the KPI cards can never drift out of sync with the
  underlying rows.
- **3-Axis Radar + Overseer Panel** — the Founder / Market / Idea-vs-Market
  axes are still never averaged (see `agents.py`'s orchestrator docstring).
  The Overseer panel now renders the Founder Score's full per-signal ledger
  (source, age, decay factor, contribution, % of F_S) and the Bayesian
  Trust Score's prior/posterior/evidence-excerpt chain, not just a final
  number.


## Challenge-brief coverage map

| Brief requirement | Where it lives |
|---|---|
| MVP 1 — Configurable Thesis Engine | `/api/thesis` + `ThesisConfigPanel.tsx`; risk appetite genuinely shifts the F_S bar (`agents.py RISK_ADJUSTMENT`) |
| MVP 2 — Smart data collection | `memory.py`: identity-keyed, deduplicated (explicit fingerprint rule), timestamped, source-tagged, append-only |
| MVP 3 — Multi-attribute NL queries | `/api/opportunities/search`: qualifier-aware scoring over computed F_S/market/trust, live enrichment fallback |
| MVP 4 — Inbound Apply (deck + name minimum) | `/api/apply` + `ApplyForm.tsx` |
| MVP 5 — Outbound Identify / Activate / Converge | Demo roster = identified cohort; `/api/outreach/draft` (draft-only, human sends); both tracks converge on `_run_evaluation_and_register` |
| MVP 6 — 3 independent axes + per-axis trend | Never averaged (orchestrator); trends via change-only `axis_history` in Memory |
| MVP 7 — Evidence-backed memos + per-claim Trust Score | `/api/memo/generate` (Appendix 1 shape, gaps flagged "Not disclosed"), Bayesian `TrustScoreEngine` with evidence excerpts |
| Founder Score ≠ 3-axis score (FAQ 6) | F_S persists in `memory.py` across applications, never resets; feeds the Founder axis as one input |
| Cold-start case (FAQ 10, scored heavily) | `FounderAxisAgent._assess_cold_start`: text-grounded read with explicit [low, high] interval, blended (α=0.6) across repeat applications |
| Stretch 1 — Agentic Traceability | Step-level `reasoning_trace` on every axis, rendered in the Overseer panel |
| Stretch 2 — Self-correction / Validator | `ValidatorAgent` + Tavily cross-referencing, discrepancy-weighted Bayesian update |
| Stretch 3 — Sourcing network | `network_analysis.py`: real NetworkX centrality/DMS over the sourcing graph |
| Speed instrumentation | `first_signal_at → decision_at → time_to_decision_seconds` on every evaluated row, shown in the memo |
| "One human in the loop" | Capital deployment and outreach sending are explicitly human actions; the system drafts and recommends only |

## Layout

```
backend/
  main.py              FastAPI app: mode toggle, Live/Cached tool clients,
                        /api/evaluate, /api/network/sourcing,
                        /api/pipeline/overview, and the Mode A/B routes
  scoring.py            FounderScoreEngine (+ per-signal breakdown),
                         Bayesian TrustScoreEngine (+ evidence excerpts),
                         MomentumTracker
  agents.py              ThesisEngine + Founder / Market / Idea-vs-Market
                         axis agents + ValidatorAgent + DealOrchestrator
  network_analysis.py   NEW — SourcingNetworkEngine: real NetworkX
                         centrality / articulation-point / DMS math
  mock_data.py           Labeled fixtures for Demo Mode, incl. the sourcing
                         network topology and hackathon roster
frontend/
  lib/
    types.ts             Shared TS types mirroring the backend schemas
    api.ts               Fetch layer with graceful {data,error} degradation
    theme.ts              Design tokens (injected once by Dashboard.tsx)
  components/
    Dashboard.tsx         Top-level layout + data orchestration
    CommandKPIs.tsx       KPI cards + pipeline conversion funnel
    NetworkGraph.tsx      d3-force sourcing network + Structural Risks panel
    DealPipelineTable.tsx 3-axis deal list
    OverseerPanel.tsx     Radar chart + F_S math + Bayesian trust-score log
  tailwind.config.snippet.js   Merge into your tailwind.config.js so the
                                /NN opacity-modifier classes resolve
```

## Running the backend

```bash
cd backend
pip install fastapi uvicorn pydantic httpx networkx numpy
uvicorn main:app --reload --port 8000
```

Defaults to **Demo Mode** (`demo_mode=True`) so it's fully functional with
zero API keys — every external call routes through `mock_data.py`, and the
Sourcing Network Graph's math runs live on the labeled fixture topology.

To go live, set:

```bash
export OPENAI_API_KEY=...      # reserved for future GPT-4o structured calls
export ANTHROPIC_API_KEY=...   # used by LiveLLMClient (claude-sonnet-4-6)
export TAVILY_API_KEY=...
```

then `POST /api/mode?demo_mode=false` (or flip the toggle in the UI). Note
that `/api/network/sourcing` and `/api/pipeline/overview` intentionally
return `501` in Live mode until a real ingestion adapter / evaluation store
is wired up — they fail loudly rather than silently mock-serving data, same
as the existing `/api/hackathon/telemetry` and `/api/hackathon/profiles`
routes.

## Running the frontend

```bash
cd frontend
npm install recharts d3-force lucide-react
npm install -D @types/d3-force
# inside a Next.js 14 App Router project with Tailwind configured:
#   npm install ibm-plex-mono ibm-plex-sans   (or load via next/font)
#   merge tailwind.config.snippet.js into your tailwind.config.js
#   drop lib/ and components/ into your project, import Dashboard into
#   app/dashboard/page.tsx
export NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

## Design decisions worth knowing about

- **No averaging across axes.** Unchanged from V1 — Founder / Market /
  Idea-vs-Market scores are computed by three independent, concurrently
  running agents and never collapsed into one blended number.
- **Nothing is fabricated.** Extended to the network graph: centrality,
  articulation-point status, and DMS scores are computed by NetworkX on
  whatever topology is supplied, not hardcoded per-node. KPI/funnel
  numbers are aggregated live from the roster, not hand-typed.
- **Live vs. Cached is a routing decision, not an agent (or engine)
  decision.** `network_analysis.SourcingNetworkEngine` and the axis agents
  only ever operate on data handed to them; `main.py` is still the only
  place that decides where that data came from.
- **Fail loud, not fabricate quiet.** New Live-mode endpoints follow the
  same pattern as the original `/api/hackathon/*` routes: a `501` with a
  clear "not wired up yet" message beats silently reusing Demo data.

## Tests run during development

In addition to the original test coverage (Founder Score decay math,
Bayesian trust scoring, full async orchestrator fan-out, FastAPI
`TestClient` smoke tests for all routes), this pass added:

- `network_analysis.SourcingNetworkEngine` exercised directly via FastAPI's
  `TestClient` against `/api/network/sourcing` — confirmed 18 nodes / 22
  edges resolve to 1 connected component, 8 real articulation points, and
  DMS scores that correctly rank the two cross-cluster bridge nodes
  (`@kai_ships`, mentor node) above single-cluster contributors.
- `/api/pipeline/overview` confirmed to aggregate KPIs and a monotonic
  Sourced → Screened → Diligence → Approved funnel directly from the
  roster fixture, with the funnel counts cross-checked against
  `pipeline_stage` values by hand.
- `/api/evaluate` re-verified end-to-end with the new `metadata` field:
  confirmed the Founder axis's `founder_score_breakdown` sums to the same
  F_S the top-level `score` field reports, and that a claim with a real
  discrepancy (5,000 claimed vs. 1,100 extracted stars) produces a flagged,
  low trust score with a real `evidence_excerpt` string attached.
- `frontend/components/*.tsx` and `frontend/lib/*.ts` type-checked with
  `tsc --noEmit` against `react`, `next`, `recharts`, `d3-force`, and
  `lucide-react` type definitions — zero type errors.
