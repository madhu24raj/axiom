"""
main.py
-------
FastAPI entrypoint for Axiom OS (formerly "The VC Brain").

Responsibilities:
- Own the global Live / Demo mode toggle (single source of truth, exposed
  via GET/POST /api/mode so the frontend context can read + flip it).
- Implement LiveTavilyClient / CachedTavilyClient and LiveLLMClient /
  CachedLLMClient, both satisfying the Protocols in agents.py, so the
  agent mesh never has to know which one it's talking to.
- Expose the pipeline: thesis filter -> 3-axis screen -> validator ->
  investment memo, for both Mode A (historical simulation replay) and
  Mode B (live/cached hackathon ingestion).
- Expose the Sourcing Network Graph (real graph-theoretic centrality /
  fragmentation math, via network_analysis.py) and a Command KPI /
  Pipeline Funnel overview (aggregated live from the current roster,
  never hand-typed totals).

Run with:
    uvicorn main:app --reload --port 8000

Required env vars for LIVE mode (unused / unnecessary in DEMO mode):
    OPENAI_API_KEY
    ANTHROPIC_API_KEY
    TAVILY_API_KEY
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import mock_data
from scoring import FounderProfile, SignalMetric, MomentumTracker, FounderScoreEngine
from agents import (
    AgentTools, ThesisEngine, ThesisCriteria, DealOrchestrator, DealEvaluation,
)
from network_analysis import (
    SourcingNetworkEngine, NetworkNodeIn, NetworkEdgeIn, SourcingNetworkResult,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("vc_brain.main")

app = FastAPI(title="Axiom OS", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global Demo Mode state
# ---------------------------------------------------------------------------
class ModeState:
    """Single mutable source of truth for Live vs Cached routing.
    In a multi-worker deployment this would live in Redis; kept in-process
    here to satisfy the 'zero-config hackathon execution' constraint."""
    demo_mode: bool = True  # default to Demo Mode so the app is presentable with zero API keys


mode_state = ModeState()


class ModeResponse(BaseModel):
    demo_mode: bool
    updated_at: str


@app.get("/api/mode", response_model=ModeResponse)
async def get_mode():
    return ModeResponse(demo_mode=mode_state.demo_mode, updated_at=datetime.utcnow().isoformat())


@app.post("/api/mode", response_model=ModeResponse)
async def set_mode(demo_mode: bool):
    mode_state.demo_mode = demo_mode
    logger.info("Global mode switched -> demo_mode=%s", demo_mode)
    return ModeResponse(demo_mode=mode_state.demo_mode, updated_at=datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# Tool implementations: Live (real HTTP) vs Cached (mock_data.py)
# ---------------------------------------------------------------------------
class LiveTavilyClient:
    def __init__(self):
        self.api_key = os.environ.get("TAVILY_API_KEY")
        self.base_url = "https://api.tavily.com/search"

    async def search(self, query: str) -> Dict[str, Any]:
        if not self.api_key:
            raise HTTPException(
                status_code=503,
                detail="TAVILY_API_KEY not configured for Live mode. Switch to Demo mode or set the key.",
            )
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                self.base_url,
                json={"api_key": self.api_key, "query": query, "max_results": 5},
            )
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results", [])
        # Normalize Tavily's raw shape into the schema our agents expect.
        top_content = (results[0].get("content") if results else None) or None
        return {
            "source_label": "tavily_live",
            "urls": [r.get("url") for r in results],
            "competitor_count": len(results),
            "saturation_index": None,   # requires downstream LLM synthesis of raw results
            "extracted_value": None,    # claim-specific extraction happens in ValidatorAgent's caller
            "evidence_excerpt": (top_content[:220] + "…") if top_content and len(top_content) > 220 else top_content,
            "verified": None,
        }


class CachedTavilyClient:
    """Routes to mock_data.py so the demo has zero live latency."""

    async def search(self, query: str) -> Dict[str, Any]:
        logger.info("[DEMO] CachedTavilyClient.search(%r)", query)
        verifications = mock_data.get_mock_payload("tavily_verifications")
        for key, v in verifications.items():
            if key.lower() in query.lower():
                return {
                    "source_label": "tavily_cached",
                    "urls": [f"https://github.com/example/{key}"],
                    "competitor_count": 7,
                    "saturation_index": 0.22,
                    "extracted_value": v["extracted_value"],
                    "evidence_excerpt": v.get("results_summary"),
                    "verified": v["verified"],
                }
        # Generic fallback demo response
        return {
            "source_label": "tavily_cached",
            "urls": ["https://example.com/demo-source"],
            "competitor_count": 5,
            "saturation_index": 0.30,
            "extracted_value": None,
            "evidence_excerpt": "[DEMO] No cached verification snippet matched this query.",
            "verified": None,
        }


class LiveLLMClient:
    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.base_url = "https://api.anthropic.com/v1/messages"

    async def structured_complete(self, system: str, prompt: str, schema_hint: str) -> Dict[str, Any]:
        if not self.api_key:
            raise HTTPException(
                status_code=503,
                detail="ANTHROPIC_API_KEY not configured for Live mode. Switch to Demo mode or set the key.",
            )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self.base_url,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 1000,
                    "system": f"{system}\nRespond ONLY with JSON matching: {schema_hint}",
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        import json as _json
        try:
            return _json.loads(text.strip().strip("`").removeprefix("json").strip())
        except Exception:
            logger.warning("Failed to parse structured LLM output, returning raw text")
            return {"raw_text": text}


class CachedLLMClient:
    async def structured_complete(self, system: str, prompt: str, schema_hint: str) -> Dict[str, Any]:
        logger.info("[DEMO] CachedLLMClient.structured_complete(...)")
        if "skill matrix" in prompt.lower() or "grit" in prompt.lower():
            return {
                "skill_notes": "[DEMO] Strong systems-level Rust/TS profile inferred from commit graph.",
                "grit_notes": "[DEMO] Sustained commit velocity across 3 consecutive hackathons.",
            }
        if "pivot" in prompt.lower():
            return {
                "pivot_velocity_score": 81.0,
                "rationale": "[DEMO] Tight, modular architecture with low framework lock-in observed in repo structure.",
            }
        return {"raw_text": "[DEMO] generic cached completion"}


def get_tools() -> AgentTools:
    demo = mode_state.demo_mode
    return AgentTools(
        tavily=CachedTavilyClient() if demo else LiveTavilyClient(),
        llm=CachedLLMClient() if demo else LiveLLMClient(),
        demo_mode=demo,
    )


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------
class EvaluateOpportunityRequest(BaseModel):
    opportunity: Dict[str, Any]
    founder_profile: Dict[str, Any]
    claims_to_verify: List[Dict[str, Any]] = []


class MemoResponse(BaseModel):
    evaluation: Dict[str, Any]
    momentum: Dict[str, str]
    memo_ready: bool


# ---------------------------------------------------------------------------
# Core evaluation endpoint (used by both Mode A replay and Mode B live feed)
# ---------------------------------------------------------------------------
@app.post("/api/evaluate", response_model=MemoResponse)
async def evaluate_opportunity(req: EvaluateOpportunityRequest):
    tools = get_tools()
    thesis = ThesisEngine(ThesisCriteria())
    orchestrator = DealOrchestrator(tools, thesis)

    try:
        founder_profile = FounderProfile(
            founder_id=req.founder_profile["founder_id"],
            name=req.founder_profile["name"],
            public_footprints=req.founder_profile.get("public_footprints", {}),
            historical_signals=[
                SignalMetric(**s) for s in req.founder_profile.get("historical_signals", [])
            ],
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid founder_profile: {exc}")

    evaluation: DealEvaluation = await orchestrator.run(
        req.opportunity, founder_profile, req.claims_to_verify
    )

    momentum_dir = MomentumTracker.direction(founder_profile.score_history)

    return MemoResponse(
        evaluation={
            "opportunity_id": evaluation.opportunity_id,
            "thesis_check": evaluation.thesis_check.__dict__,
            "founder": evaluation.founder.__dict__ if evaluation.founder else None,
            "market": evaluation.market.__dict__ if evaluation.market else None,
            "idea_vs_market": evaluation.idea_vs_market.__dict__ if evaluation.idea_vs_market else None,
            "trust_scores": [t.dict() for t in evaluation.trust_scores],
            "generated_at": evaluation.generated_at,
        },
        momentum={
            "direction": momentum_dir.value,
            "arrow": MomentumTracker.arrow(momentum_dir),
        },
        memo_ready=evaluation.founder is not None,
    )


# ---------------------------------------------------------------------------
# Mode A: Reverse Sourcing historical simulation
# ---------------------------------------------------------------------------
@app.get("/api/simulation/historical")
async def get_historical_simulation():
    """Always served from mock_data.py regardless of the global toggle --
    this is a fixed, labeled historical walkthrough, not a live query."""
    return mock_data.get_mock_payload("historical_simulation")


# ---------------------------------------------------------------------------
# Mode B: Live hackathon network ingestion
# ---------------------------------------------------------------------------
@app.get("/api/hackathon/telemetry")
async def get_hackathon_telemetry():
    if mode_state.demo_mode:
        return mock_data.get_mock_payload("hackathon_toolkit_telemetry")
    # Live path would fan out to Emdash / Lovable / WOZ ingestion endpoints here.
    raise HTTPException(
        status_code=501,
        detail="Live telemetry ingestion endpoints not configured. Set toolkit webhook URLs or use Demo mode.",
    )


@app.get("/api/hackathon/profiles")
async def get_hackathon_profiles():
    if mode_state.demo_mode:
        return mock_data.get_mock_payload("live_hackathon_profiles")
    raise HTTPException(
        status_code=501,
        detail="Live profile ingestion not configured. Set source webhook URLs or use Demo mode.",
    )


# ---------------------------------------------------------------------------
# Sourcing Network Graph -- real centrality / fragmentation math computed by
# network_analysis.SourcingNetworkEngine on top of a topology. In Demo mode
# the topology is the labeled fixture in mock_data.py; in Live mode this
# would run the identical engine over an ingested collaboration graph (not
# yet wired up, so it fails loudly rather than silently mock-serving).
# ---------------------------------------------------------------------------
_network_engine = SourcingNetworkEngine()


@app.get("/api/network/sourcing", response_model=SourcingNetworkResult)
async def get_sourcing_network():
    if not mode_state.demo_mode:
        raise HTTPException(
            status_code=501,
            detail=(
                "Live network ingestion not configured. The centrality/DMS "
                "engine (network_analysis.py) is live-mode-ready, but no "
                "collaboration-graph ingestion adapter is wired up yet. "
                "Switch to Demo mode to see the engine run on fixture data."
            ),
        )
    raw_nodes = [NetworkNodeIn(**n) for n in mock_data.get_mock_payload("sourcing_network_nodes")]
    raw_edges = [NetworkEdgeIn(**e) for e in mock_data.get_mock_payload("sourcing_network_edges")]
    return _network_engine.run(raw_nodes, raw_edges)


# ---------------------------------------------------------------------------
# Command KPIs + Pipeline Funnel -- aggregated from the current hackathon
# roster (Founder Score computed live via FounderScoreEngine, thesis-fit
# computed live via ThesisEngine) rather than hand-typed summary numbers,
# so the KPI cards can never drift out of sync with the underlying rows.
# ---------------------------------------------------------------------------
CHECK_SIZE_USD = 100_000
HIGH_POTENTIAL_THRESHOLD = 55.0


def _profile_to_signals(raw_signals: Dict[str, Any]) -> List[SignalMetric]:
    """Best-effort mapping of a hackathon telemetry blob into SignalMetric
    rows the FounderScoreEngine already knows how to decay-weight. This is
    the same signal schema /api/evaluate consumes -- no parallel math path."""
    now = datetime.utcnow()
    commits = raw_signals.get("commits_7d", 0)
    stars = raw_signals.get("stars_7d", 0)
    tier = raw_signals.get("hackathon_award_tier", "none")
    tier_score = {"finalist": 0.95, "honorable mention": 0.7, "none": 0.35}.get(tier, 0.35)

    return [
        SignalMetric(
            source="github",
            timestamp=now,
            normalized_score=min(1.0, commits / 60.0),
            confidence=0.7,
            data_points={"commits_7d": commits, "stars_7d": stars},
        ),
        SignalMetric(
            source="hackathon",
            timestamp=now,
            normalized_score=tier_score,
            confidence=0.8,
            data_points={"hackathon_award_tier": tier},
        ),
    ]


class PipelineOverviewResponse(BaseModel):
    kpis: Dict[str, Any]
    funnel: List[Dict[str, Any]]
    label: str = "[Aggregated live from the current hackathon roster — not hand-typed totals]"


@app.get("/api/pipeline/overview", response_model=PipelineOverviewResponse)
async def get_pipeline_overview():
    if not mode_state.demo_mode:
        raise HTTPException(
            status_code=501,
            detail=(
                "Live pipeline aggregation requires a persistent evaluation "
                "store (not yet wired up). Switch to Demo mode to see KPIs "
                "aggregated from the fixture roster."
            ),
        )

    score_engine = FounderScoreEngine()
    thesis = ThesisEngine(ThesisCriteria())
    profiles = mock_data.get_mock_payload("live_hackathon_profiles")

    scored: List[Dict[str, Any]] = []
    for p in profiles:
        signals = _profile_to_signals(p.get("raw_signals", {}))
        f_s = score_engine.calculate_score(signals)
        thesis_result = thesis.passes({"sector": p.get("sector", "unknown"), "founder_score": f_s})
        scored.append({
            **p,
            "founder_score": f_s,
            "thesis_pass": thesis_result.detail.startswith("PASS"),
        })

    total = len(scored)
    high_potential = sum(1 for s in scored if s["founder_score"] >= HIGH_POTENTIAL_THRESHOLD)
    avg_founder_score = round(sum(s["founder_score"] for s in scored) / total, 2) if total else 0.0
    approved = [s for s in scored if s.get("pipeline_stage") == "approved"]
    capital_deployed = len(approved) * CHECK_SIZE_USD

    kpis = {
        "total_opportunities": total,
        "high_potential_count": high_potential,
        "avg_founder_score": avg_founder_score,
        "capital_deployed_usd": capital_deployed,
        "check_size_usd": CHECK_SIZE_USD,
        "thesis_pass_rate_pct": round(100 * sum(1 for s in scored if s["thesis_pass"]) / total, 1) if total else 0.0,
    }

    stage_order = mock_data.PIPELINE_STAGE_ORDER
    stage_index = {s: i for i, s in enumerate(stage_order)}
    funnel = []
    for i, stage in enumerate(stage_order):
        # Cumulative: count of opportunities that have reached AT LEAST this stage.
        count = sum(
            1 for s in scored
            if stage_index.get(s.get("pipeline_stage", "sourced"), 0) >= i
        )
        funnel.append({"stage": stage, "count": count})

    return PipelineOverviewResponse(kpis=kpis, funnel=funnel)


@app.get("/api/healthz")
async def healthz():
    return {"status": "ok", "demo_mode": mode_state.demo_mode, "time": datetime.utcnow().isoformat()}
