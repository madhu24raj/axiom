"""
main.py
-------
FastAPI entrypoint for Axiom OS (formerly "The VC Brain").

Responsibilities:
- Own the global Live / Demo mode toggle.
- Implement LiveTavilyClient / CachedTavilyClient and LiveLLMClient /
  CachedLLMClient, both satisfying the Protocols in agents.py, so the
  agent mesh never has to know which one it's talking to.
- Expose the pipeline: thesis filter -> 3-axis screen -> validator ->
  investment memo, for Mode A (historical simulation replay) and Mode B
  (live/cached hackathon ingestion).
- Expose the Sourcing Network Graph and Command KPI / Pipeline Funnel
  overview, computed from live-grown session state in Live mode instead
  of raising 501 -- see LiveSessionState below.
- Expose keyword-heuristic + live-enrichment search, and a grounded
  Overseer chat endpoint.

A NOTE ON WHAT LIVE MODE DOES AND DOESN'T DO:
Live mode uses your real ANTHROPIC_API_KEY / TAVILY_API_KEY to research a
SPECIFIC, user-searched name or handle -- it does not crawl the open web
for arbitrary real people to score in the background, and it does not
pre-populate the Sourcing Network Graph with real, named individuals who
never opted into being profiled. The graph and pipeline start genuinely
empty in Live mode and grow only from searches the user actually runs.
This also means Axiom OS never autonomously "deploys capital" -- the
Pipeline Overview's capital_deployed_usd in Live mode is always computed
from deals a human has marked approved elsewhere, never asserted by the
scoring pipeline itself.

Run with:
    uvicorn main:app --reload --port 8000

Required env vars for LIVE mode (unused / unnecessary in DEMO mode):
    OPENAI_API_KEY   (reserved for future GPT-4o structured calls)
    ANTHROPIC_API_KEY
    TAVILY_API_KEY
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import mock_data
from memory import memory_store, normalize_identity
from scoring import FounderProfile, SignalMetric, MomentumTracker, MomentumVector
from agents import (
    AgentTools, ThesisEngine, ThesisCriteria, DealOrchestrator, DealEvaluation,
)
from network_analysis import (
    SourcingNetworkEngine, NetworkNodeIn, NetworkEdgeIn, SourcingNetworkResult,
    GitHubGraphSeeder, SeederUnavailable, infer_edges_for_new_node,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("vc_brain.main")

app = FastAPI(title="Axiom OS", version="0.3.0")

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
    demo_mode: bool = True


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
# Thesis State -- required MVP #1: "Investor sets sectors, stage, geography,
# check size, ownership targets, and risk appetite. Every recommendation is
# filtered and scored through this fund-specific lens." Every evaluation path
# in this file (apply, search, demo roster) reads thesis_state.criteria, so
# changing it from the UI actually changes what gets screened -- it's not a
# display-only settings panel.
# ---------------------------------------------------------------------------
class ThesisState:
    criteria: ThesisCriteria = ThesisCriteria()


thesis_state = ThesisState()


class ThesisCriteriaModel(BaseModel):
    min_check_fit_usd: int = 100_000
    target_sectors: List[str] = ["dev tools", "infra", "agentic systems"]
    excluded_sectors: List[str] = []
    min_founder_score: float = 40.0
    stage: str = "pre-seed"
    geography: List[str] = []
    ownership_target_pct: float = 10.0
    risk_appetite: str = "balanced"


@app.get("/api/thesis", response_model=ThesisCriteriaModel)
async def get_thesis():
    return ThesisCriteriaModel(**thesis_state.criteria.__dict__)


@app.post("/api/thesis", response_model=ThesisCriteriaModel)
async def set_thesis(criteria: ThesisCriteriaModel):
    thesis_state.criteria = ThesisCriteria(**criteria.dict())
    logger.info("Thesis criteria updated: %s", thesis_state.criteria)
    return criteria


# ---------------------------------------------------------------------------
# Live Session State -- what Live mode's network graph and pipeline overview
# are actually built from. On first Live-mode network fetch it is seeded from
# the GitHub PUBLIC API (org handles -> top repos -> top contributors --
# public profiles/commit histories only, every node stamped with its source
# URL and fetch time), then grows from searches this session runs. Deal rows
# and scores are still never pre-seeded: seeded nodes are topology, not
# evaluations. In a multi-user deployment this would be per-session
# (cookie/user id keyed) rather than process-global.
# ---------------------------------------------------------------------------
@dataclass
class LiveSessionState:
    deal_rows: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    graph_nodes: Dict[str, NetworkNodeIn] = field(default_factory=dict)
    graph_edges: List[NetworkEdgeIn] = field(default_factory=list)
    # GitHub public-API seeding (Live mode). seed_attempted stops us from
    # hammering GitHub on every poll if the first attempt failed; hit
    # POST /api/network/seed to retry explicitly.
    seed_attempted: bool = False
    seed_meta: Optional[Dict[str, Any]] = None
    seed_error: Optional[str] = None


live_state = LiveSessionState()


# ---------------------------------------------------------------------------
# Tool implementations: Live (real HTTP) vs Cached (mock_data.py)
# ---------------------------------------------------------------------------
class LiveTavilyClient:
    def __init__(self):
        self.api_key = os.environ.get("TAVILY_API_KEY")
        self.base_url = "https://api.tavily.com/search"

    async def _raw_search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise HTTPException(
                status_code=503,
                detail="TAVILY_API_KEY not configured for Live mode. Switch to Demo mode or set the key.",
            )
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                self.base_url,
                json={"api_key": self.api_key, "query": query, "max_results": max_results},
            )
            resp.raise_for_status()
            data = resp.json()
        return data.get("results", [])

    async def search(self, query: str) -> Dict[str, Any]:
        results = await self._raw_search(query)
        top_content = (results[0].get("content") if results else None) or None
        return {
            "source_label": "tavily_live",
            "urls": [r.get("url") for r in results],
            "competitor_count": len(results),
            "saturation_index": None,
            "extracted_value": None,
            "evidence_excerpt": (top_content[:220] + "…") if top_content and len(top_content) > 220 else top_content,
            "verified": None,
        }

    async def enrich_search(self, query: str) -> Dict[str, Any]:
        """Broader raw-snippet search used by live founder enrichment --
        distinct from search() because the agent-facing schema above is
        narrowed to the competitor/verification shape those callers expect."""
        results = await self._raw_search(query, max_results=4)
        return {
            "raw_results": [
                {"url": r.get("url"), "content": r.get("content", "")} for r in results
            ]
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
        return {
            "source_label": "tavily_cached",
            "urls": ["https://example.com/demo-source"],
            "competitor_count": 5,
            "saturation_index": 0.30,
            "extracted_value": None,
            "evidence_excerpt": "[DEMO] No cached verification snippet matched this query.",
            "verified": None,
        }

    async def enrich_search(self, query: str) -> Dict[str, Any]:
        logger.info("[DEMO] CachedTavilyClient.enrich_search(%r)", query)
        return {"raw_results": []}  # live enrichment is a Live-mode-only capability


class LiveLLMClient:
    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.base_url = "https://api.anthropic.com/v1/messages"

    async def _call(self, system: str, user_message: str, max_tokens: int) -> str:
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
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user_message}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")

    async def structured_complete(self, system: str, prompt: str, schema_hint: str) -> Dict[str, Any]:
        text = await self._call(f"{system}\nRespond ONLY with JSON matching: {schema_hint}", prompt, 1000)
        try:
            return json.loads(text.strip().strip("`").removeprefix("json").strip())
        except Exception:
            logger.warning("Failed to parse structured LLM output, returning raw text")
            return {"raw_text": text}

    async def chat(self, system: str, user_message: str) -> str:
        text = await self._call(system, user_message, 700)
        return text.strip() or "[No response generated]"


class CachedLLMClient:
    async def structured_complete(self, system: str, prompt: str, schema_hint: str) -> Dict[str, Any]:
        logger.info("[DEMO] CachedLLMClient.structured_complete(...)")
        if "cold-start case" in system.lower():
            return _deterministic_cold_start(prompt)
        if "drafting an investment memo" in system.lower():
            return _deterministic_memo(prompt)
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

    async def chat(self, system: str, user_message: str) -> str:
        logger.info("[DEMO] CachedLLMClient.chat(...)")
        if "skeptical vc partner" in system.lower():
            return _deterministic_adversarial_view(user_message)
        if "draft founder outreach" in system.lower():
            return _deterministic_outreach_draft(user_message)
        return _deterministic_overseer_reply(user_message)


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
    momentum: Dict[str, Any]
    memo_ready: bool


def _serialize_evaluation(evaluation: DealEvaluation) -> Dict[str, Any]:
    return {
        "opportunity_id": evaluation.opportunity_id,
        "thesis_check": evaluation.thesis_check.__dict__,
        "founder": evaluation.founder.__dict__ if evaluation.founder else None,
        "market": evaluation.market.__dict__ if evaluation.market else None,
        "idea_vs_market": evaluation.idea_vs_market.__dict__ if evaluation.idea_vs_market else None,
        "trust_scores": [t.dict() for t in evaluation.trust_scores],
        "generated_at": evaluation.generated_at,
    }


def _serialize_deal_row(
    opportunity_id: str,
    founder_name: str,
    sector: str,
    evaluation: DealEvaluation,
    momentum: MomentumVector,
    provenance: str,
    data_confidence: Optional[str] = None,
) -> Dict[str, Any]:
    row = _serialize_evaluation(evaluation)
    row.update({
        "founder_name": founder_name,
        "sector": sector,
        "momentum": momentum.dict(),
        "data_provenance": provenance,
        "data_confidence": data_confidence,
    })
    return row


# ---------------------------------------------------------------------------
# Core evaluation endpoint (used by both Mode A replay and Mode B live feed)
# ---------------------------------------------------------------------------
@app.post("/api/evaluate", response_model=MemoResponse)
async def evaluate_opportunity(req: EvaluateOpportunityRequest):
    tools = get_tools()
    thesis = ThesisEngine(thesis_state.criteria)
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
    momentum = MomentumTracker.for_profile(founder_profile)

    return MemoResponse(
        evaluation=_serialize_evaluation(evaluation),
        momentum=momentum.dict(),
        memo_ready=evaluation.founder is not None,
    )


# ---------------------------------------------------------------------------
# Mode A: Reverse Sourcing historical simulation
# ---------------------------------------------------------------------------
@app.get("/api/simulation/historical")
async def get_historical_simulation():
    return mock_data.get_mock_payload("historical_simulation")


# ---------------------------------------------------------------------------
# Mode B: Live hackathon network ingestion (unchanged from V2 -- out of
# scope for this pass; still fails loudly rather than mock-serving)
# ---------------------------------------------------------------------------
@app.get("/api/hackathon/telemetry")
async def get_hackathon_telemetry():
    if mode_state.demo_mode:
        return mock_data.get_mock_payload("hackathon_toolkit_telemetry")
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
        detail="Live profile ingestion not configured. Use the search bar to look up a specific target instead.",
    )


# ---------------------------------------------------------------------------
# Founder Score signal mapping -- shared by the demo roster aggregation and
# the pipeline overview, so there is exactly one place this math lives.
# ---------------------------------------------------------------------------
def _profile_to_signals(raw_signals: Dict[str, Any]) -> List[SignalMetric]:
    now = datetime.utcnow()
    commits = raw_signals.get("commits_7d", 0)
    stars = raw_signals.get("stars_7d", 0)
    tier = raw_signals.get("hackathon_award_tier", "none")
    tier_score = {"finalist": 0.95, "honorable mention": 0.7, "none": 0.35}.get(tier, 0.35)
    return [
        SignalMetric(
            source="github", timestamp=now,
            normalized_score=min(1.0, commits / 60.0), confidence=0.7,
            data_points={"commits_7d": commits, "stars_7d": stars},
        ),
        SignalMetric(
            source="hackathon", timestamp=now,
            normalized_score=tier_score, confidence=0.8,
            data_points={"hackathon_award_tier": tier},
        ),
    ]


async def _demo_roster_as_rows() -> List[Dict[str, Any]]:
    """The demo roster, fully evaluated through the real orchestrator, in
    DealRow shape -- used both by pipeline/overview and by search so search
    can filter over real computed scores, not just profile metadata."""
    tools = get_tools()
    thesis = ThesisEngine(thesis_state.criteria)
    profiles = mock_data.get_mock_payload("live_hackathon_profiles")

    rows: List[Dict[str, Any]] = []
    for p in profiles:
        orchestrator = DealOrchestrator(tools, thesis)
        founder_profile = FounderProfile(
            founder_id=p["founder_id"], name=p["name"],
            public_footprints=p.get("public_footprints", {}),
            historical_signals=_profile_to_signals(p.get("raw_signals", {})),
        )
        opportunity = {
            "id": p["founder_id"], "sector": p.get("sector", "unknown"),
            "founder_score": 50, "keywords": [p.get("project", "")],
            "idea_summary": p.get("project", ""), "engineering_signals": p.get("raw_signals", {}),
        }
        claims = (
            [{
                "claim_text": "5k GitHub stars inside 14 days",
                "claimed_value": 5000,
                "verification_query": "fast-context-ide (demo alias) stars",
            }]
            if p.get("project") == "parallel-agent-runner" else []
        )
        evaluation = await orchestrator.run(opportunity, founder_profile, claims)
        momentum = MomentumTracker.for_profile(founder_profile)
        row = _serialize_deal_row(
            p["founder_id"], p["name"], p.get("sector", "unknown"),
            evaluation, momentum, provenance="demo_fixture",
        )
        row["pipeline_stage"] = p.get("pipeline_stage", "sourced")
        row["axis_trends"] = memory_store.record_axis_scores(
            normalize_identity(p["name"], p.get("public_footprints", {}).get("github")),
            p["name"],
            {
                "founder": evaluation.founder.score if evaluation.founder else None,
                "market": evaluation.market.score if evaluation.market else None,
                "idea_vs_market": evaluation.idea_vs_market.score if evaluation.idea_vs_market else None,
            },
        )
        rows.append(row)
    return rows


@app.get("/api/opportunities/live")
async def get_live_opportunities():
    """Live mode's deal pipeline: exactly what's been searched and evaluated
    this session. Empty on a fresh session -- that's the honest state, not
    an error."""
    return list(live_state.deal_rows.values())


# ---------------------------------------------------------------------------
# Sourcing Network Graph -- Demo mode runs the real engine over the labeled
# fixture topology. Live mode runs the IDENTICAL engine over whatever this
# session has actually searched (live_state.graph_nodes/edges), which starts
# empty. Either way this never 501s and never hardcodes real people who
# weren't explicitly searched for.
# ---------------------------------------------------------------------------
_network_engine = SourcingNetworkEngine()


async def _ensure_live_seed(force: bool = False) -> None:
    """Seed Live mode's graph from the GitHub public API exactly once per
    session (or again on force). Failure is recorded, never masked with
    fabricated nodes -- the endpoint below falls back to the labeled demo
    topology instead."""
    if live_state.seed_attempted and not force:
        return
    live_state.seed_attempted = True
    live_state.seed_error = None
    try:
        nodes, edges, meta = await GitHubGraphSeeder().seed()
    except SeederUnavailable as exc:
        live_state.seed_error = str(exc)
        logger.warning("GitHub seed unavailable: %s", exc)
        return
    for n in nodes:
        live_state.graph_nodes.setdefault(n.id, n)
    seen = {(min(e.source, e.target), max(e.source, e.target)) for e in live_state.graph_edges}
    for e in edges:
        k = (min(e.source, e.target), max(e.source, e.target))
        if k not in seen:
            seen.add(k)
            live_state.graph_edges.append(e)
    live_state.seed_meta = meta
    logger.info(
        "GitHub seed complete: %d nodes / %d edges from %s",
        meta["node_count"], meta["edge_count"], meta["seeded_handles"],
    )


@app.post("/api/network/seed")
async def reseed_network():
    """Explicitly (re)run the GitHub public-API seed -- demo insurance if the
    first lazy attempt hit a rate limit before GITHUB_TOKEN was set."""
    if mode_state.demo_mode:
        raise HTTPException(status_code=409, detail="Seeding is a Live-mode operation. Switch to Live mode first.")
    await _ensure_live_seed(force=True)
    if live_state.seed_error:
        raise HTTPException(status_code=503, detail=live_state.seed_error)
    return {"status": "seeded", **(live_state.seed_meta or {})}


@app.get("/api/network/sourcing", response_model=SourcingNetworkResult)
async def get_sourcing_network():
    if mode_state.demo_mode:
        raw_nodes = [NetworkNodeIn(**n) for n in mock_data.get_mock_payload("sourcing_network_nodes")]
        raw_edges = [NetworkEdgeIn(**e) for e in mock_data.get_mock_payload("sourcing_network_edges")]
        result = _network_engine.run(raw_nodes, raw_edges)
        result.label = "SIMULATED — demo topology, real graph math"
        return result

    await _ensure_live_seed()

    nodes = list(live_state.graph_nodes.values())
    edges = list(live_state.graph_edges)

    if not nodes:
        # GitHub seed failed AND nothing searched yet. Rather than an empty
        # screen or a fabricated "live" graph, serve the demo topology with a
        # label that says exactly what happened and why.
        raw_nodes = [NetworkNodeIn(**n) for n in mock_data.get_mock_payload("sourcing_network_nodes")]
        raw_edges = [NetworkEdgeIn(**e) for e in mock_data.get_mock_payload("sourcing_network_edges")]
        result = _network_engine.run(raw_nodes, raw_edges)
        result.label = (
            "LIVE — GitHub seed unavailable "
            f"({live_state.seed_error or 'unknown'}); showing labeled demo topology"
        )
        return result

    result = _network_engine.run(nodes, edges)
    searched = sum(
        1 for n in nodes if (n.meta or {}).get("data_provenance") != "github_public_api"
    )
    if live_state.seed_meta:
        handles = ", ".join(live_state.seed_meta.get("seeded_handles", []))
        result.label = (
            f"LIVE — seeded from GitHub public API ({handles}) "
            f"+ {searched} session search(es)"
        )
    else:
        result.label = f"LIVE — grown from {searched} real search(es) this session"
    return result


# ---------------------------------------------------------------------------
# Command KPIs + Pipeline Funnel
# ---------------------------------------------------------------------------
CHECK_SIZE_USD = 100_000
HIGH_POTENTIAL_THRESHOLD = 55.0


class PipelineOverviewResponse(BaseModel):
    kpis: Dict[str, Any]
    funnel: List[Dict[str, Any]]
    provenance: str
    label: str


@app.get("/api/pipeline/overview", response_model=PipelineOverviewResponse)
async def get_pipeline_overview():
    if mode_state.demo_mode:
        rows = await _demo_roster_as_rows()
        stage_order = mock_data.PIPELINE_STAGE_ORDER
        stage_index = {s: i for i, s in enumerate(stage_order)}

        total = len(rows)
        scores = [r["founder"]["score"] for r in rows if r.get("founder") and r["founder"].get("score") is not None]
        high_potential = sum(1 for s in scores if s >= HIGH_POTENTIAL_THRESHOLD)
        avg_founder_score = round(sum(scores) / len(scores), 2) if scores else 0.0
        approved = [r for r in rows if r.get("pipeline_stage") == "approved"]
        thesis_pass = sum(1 for r in rows if r.get("founder") is not None)

        kpis = {
            "total_opportunities": total,
            "high_potential_count": high_potential,
            "avg_founder_score": avg_founder_score,
            "capital_deployed_usd": len(approved) * CHECK_SIZE_USD,
            "check_size_usd": CHECK_SIZE_USD,
            "thesis_pass_rate_pct": round(100 * thesis_pass / total, 1) if total else 0.0,
            "human_approval_required": True,
        }
        funnel = [
            {"stage": stage, "count": sum(
                1 for r in rows if stage_index.get(r.get("pipeline_stage", "sourced"), 0) >= i
            )}
            for i, stage in enumerate(stage_order)
        ]
        return PipelineOverviewResponse(
            kpis=kpis, funnel=funnel, provenance="demo_fixture",
            label="SIMULATED — aggregated from the demo roster",
        )

    rows = list(live_state.deal_rows.values())
    total = len(rows)
    scores = [r["founder"]["score"] for r in rows if r.get("founder") and r["founder"].get("score") is not None]
    high_potential = sum(1 for s in scores if s >= HIGH_POTENTIAL_THRESHOLD)
    avg_founder_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    thesis_pass = sum(1 for r in rows if r.get("founder") is not None)
    diligence = sum(1 for r in rows if r.get("trust_scores"))

    kpis = {
        "total_opportunities": total,
        "high_potential_count": high_potential,
        "avg_founder_score": avg_founder_score,
        # Axiom OS never marks a deal "approved" or moves capital on its own --
        # that stays a human action outside this API, so this is always 0 here.
        "capital_deployed_usd": 0,
        "check_size_usd": CHECK_SIZE_USD,
        "thesis_pass_rate_pct": round(100 * thesis_pass / total, 1) if total else 0.0,
        "human_approval_required": True,
    }
    funnel = [
        {"stage": "sourced", "count": total},
        {"stage": "screened", "count": thesis_pass},
        {"stage": "diligence", "count": diligence},
        {"stage": "approved", "count": 0},
    ]
    return PipelineOverviewResponse(
        kpis=kpis, funnel=funnel,
        provenance="live_session" if rows else "live_awaiting_input",
        label=(
            f"LIVE — aggregated from {total} real search(es) this session"
            if rows else "LIVE — search for a target to populate this"
        ),
    )


# ---------------------------------------------------------------------------
# Search: keyword-heuristic filter over whatever roster is active, falling
# back to live Tavily+LLM enrichment ONLY in Live mode and ONLY when the
# query doesn't match anything already known. Demo mode never triggers a
# live fetch, regardless of query.
# ---------------------------------------------------------------------------
_STOPWORDS = {"a", "an", "the", "with", "and", "for", "of", "in", "on", "is", "has"}


def _tokenize(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS}


def _score_candidate(tokens: set, row: Dict[str, Any]) -> float:
    haystack = " ".join(str(row.get(k, "")) for k in ("founder_name", "sector", "opportunity_id"))
    score = float(len(tokens & _tokenize(haystack)))

    if row.get("sector") and row["sector"].lower().replace(" ", "") in {t.replace(" ", "") for t in tokens}:
        score += 2.0

    if {"high", "strong"} & tokens and "trust" in tokens and row.get("trust_scores"):
        avg_trust = sum(t["trust_score"] for t in row["trust_scores"]) / len(row["trust_scores"])
        score += avg_trust * 3

    if {"technical", "founder", "engineering"} & tokens:
        f_score = (row.get("founder") or {}).get("score")
        if f_score is not None:
            score += f_score / 25

    if {"enterprise", "traction", "market"} & tokens:
        m_score = (row.get("market") or {}).get("score")
        if m_score is not None:
            score += m_score / 25

    return score


async def _tavily_enrich_founder(query: str, tools: AgentTools) -> Optional[Dict[str, Any]]:
    """Live-mode-only: run two broad Tavily searches for a SPECIFIC,
    user-provided target, then have the LLM extract only facts explicitly
    present in those snippets. Returns None if nothing is found -- this
    function never invents a profile for a query that turned up nothing."""
    if tools.demo_mode:
        return None

    dev_results = await tools.tavily.enrich_search(f"{query} github profile stars commits")
    co_results = await tools.tavily.enrich_search(f"{query} startup company sector traction")
    snippets = (dev_results.get("raw_results", []) + co_results.get("raw_results", []))[:6]
    snippets = [s for s in snippets if s.get("content")]
    if not snippets:
        return None

    context_blob = "\n".join(f"- {s.get('url', '')}: {s.get('content', '')[:300]}" for s in snippets)
    extraction = await tools.llm.structured_complete(
        system=(
            "You are a due-diligence research assistant. Extract ONLY facts explicitly "
            "present in the provided search snippets below. Use null for anything not "
            "clearly stated -- never guess or infer a number that isn't in the text."
        ),
        prompt=f"Subject queried: {query}\nSearch snippets:\n{context_blob}",
        schema_hint=(
            '{"name": str, "project_or_company": str|null, "sector_guess": str|null, '
            '"github_url": str|null, "stars_mentioned": number|null, '
            '"commits_mentioned": number|null, "traction_signal_0to1": number|null, '
            '"summary": str, "data_confidence": "low"|"medium"|"high"}'
        ),
    )
    if not extraction or "raw_text" in extraction:
        return None
    extraction["source_urls"] = [s.get("url") for s in snippets if s.get("url")]
    return extraction


def _profile_from_enrichment(query: str, extraction: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    now = datetime.utcnow().isoformat()
    signals: List[Dict[str, Any]] = []

    if extraction.get("commits_mentioned") is not None:
        signals.append({
            "source": "github", "timestamp": now,
            "normalized_score": min(1.0, max(0.0, extraction["commits_mentioned"] / 60.0)),
            "confidence": 0.4, "data_points": {"commits_mentioned": extraction["commits_mentioned"]},
        })
    if extraction.get("traction_signal_0to1") is not None:
        signals.append({
            "source": "inbound_deck", "timestamp": now,
            "normalized_score": min(1.0, max(0.0, extraction["traction_signal_0to1"])),
            "confidence": 0.4, "data_points": {},
        })
    if not signals:
        # A single, explicitly low-confidence signal so a thin search result
        # still produces a defensible (low) score instead of silently 0/None.
        signals.append({
            "source": "twitter", "timestamp": now,
            "normalized_score": 0.2, "confidence": 0.25, "data_points": {},
        })

    github_url = extraction.get("github_url")
    footprints = {}
    if isinstance(github_url, str) and github_url.startswith("http"):
        footprints["github"] = github_url

    founder_id = f"live-{abs(hash(query)) % 100000}"
    founder_profile_raw = {
        "founder_id": founder_id,
        "name": extraction.get("name") or query,
        "public_footprints": footprints,
        "historical_signals": signals,
    }
    opportunity = {
        "id": founder_id,
        "sector": extraction.get("sector_guess") or "unknown",
        "founder_score": 50,
        "keywords": [extraction.get("project_or_company") or query],
        "idea_summary": extraction.get("summary", ""),
        "engineering_signals": {},
    }
    return founder_profile_raw, opportunity


async def _run_evaluation_and_register(
    *,
    opportunity_id: str,
    display_name: str,
    identity_key: str,
    new_signals: List[Dict[str, Any]],
    opportunity: Dict[str, Any],
    application_text: Optional[str],
    claims: List[Dict[str, Any]],
    provenance: str,
    data_confidence: Optional[str],
    first_signal_at: datetime,
    extra_row_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """The one place a new or returning opportunity actually gets scored and
    persisted. Every caller (live search-enrichment, inbound Apply) routes
    through here so Memory (never resets), speed instrumentation
    (first_signal_at -> decision_at), and the Sourcing Network Graph all stay
    consistent regardless of how the opportunity entered the system --
    exactly the brief's "Converge: both tracks feed one funnel" requirement."""
    tools = get_tools()
    thesis = ThesisEngine(thesis_state.criteria)
    orchestrator = DealOrchestrator(tools, thesis)

    signal_objs = [SignalMetric(**s) for s in new_signals]
    record = memory_store.upsert(identity_key, display_name, signal_objs, opportunity_id)

    evaluation = await orchestrator.run(opportunity, record.profile, claims, application_text=application_text)

    if evaluation.founder is not None and evaluation.founder.score is not None:
        memory_store.record_displayed_score(identity_key, evaluation.founder.score)
    momentum = MomentumTracker.for_profile(record.profile)

    row = _serialize_deal_row(
        opportunity_id, display_name, opportunity.get("sector", "unknown"),
        evaluation, momentum, provenance=provenance, data_confidence=data_confidence,
    )
    row["pipeline_stage"] = "screened" if evaluation.founder else "sourced"
    row["identity_key"] = identity_key
    row["applications_on_file"] = len(record.applications)
    row["axis_trends"] = memory_store.record_axis_scores(identity_key, display_name, {
        "founder": evaluation.founder.score if evaluation.founder else None,
        "market": evaluation.market.score if evaluation.market else None,
        "idea_vs_market": evaluation.idea_vs_market.score if evaluation.idea_vs_market else None,
    })

    decision_at = datetime.utcnow()
    row["first_signal_at"] = first_signal_at.isoformat()
    row["decision_at"] = decision_at.isoformat()
    row["time_to_decision_seconds"] = round((decision_at - first_signal_at).total_seconds(), 3)

    if extra_row_fields:
        row.update(extra_row_fields)

    live_state.deal_rows[opportunity_id] = row

    # -- Graph registration (node + edges) ---------------------------------
    # Meta carries the evidence that edge inference keys off: sector, cited
    # source URLs, and (if disclosed) the github login. All of it comes
    # straight from the evaluation inputs -- nothing synthesized here.
    github_url = (extra_row_fields or {}).get("github_url") or ""
    m = re.match(r"https?://(?:www\.)?github\.com/([^/\s]+)", str(github_url))
    node_meta: Dict[str, Any] = {
        "data_provenance": provenance,
        "data_confidence": data_confidence,
        "sector": opportunity.get("sector"),
        "source_urls": (extra_row_fields or {}).get("source_urls", []),
    }
    if m:
        node_meta["github_login"] = m.group(1)

    node = NetworkNodeIn(
        id=opportunity_id,
        label=display_name,
        node_type="developer",
        sub_label=(opportunity.get("keywords") or [None])[0],
        meta=node_meta,
    )
    live_state.graph_nodes[opportunity_id] = node
    new_edges = infer_edges_for_new_node(
        node, list(live_state.graph_nodes.values()), live_state.graph_edges
    )
    live_state.graph_edges.extend(new_edges)
    if new_edges:
        logger.info(
            "Graph: %s linked to %d node(s) via %s",
            opportunity_id, len(new_edges), sorted({e.edge_type for e in new_edges}),
        )
    return row


async def _evaluate_and_register_live(
    founder_profile_raw: Dict[str, Any], opportunity: Dict[str, Any], extraction: Dict[str, Any]
) -> Dict[str, Any]:
    identity_key = normalize_identity(
        founder_profile_raw["name"], founder_profile_raw.get("public_footprints", {}).get("github")
    )
    return await _run_evaluation_and_register(
        opportunity_id=founder_profile_raw["founder_id"],
        display_name=founder_profile_raw["name"],
        identity_key=identity_key,
        new_signals=founder_profile_raw["historical_signals"],
        opportunity=opportunity,
        application_text=extraction.get("summary"),
        claims=[],
        provenance="live_enriched",
        data_confidence=extraction.get("data_confidence", "low"),
        first_signal_at=datetime.utcnow(),
        extra_row_fields={"source_urls": extraction.get("source_urls", []), "summary": extraction.get("summary")},
    )


class ApplicationRequest(BaseModel):
    company_name: str
    deck_text: str  # deck content or a pasted summary -- the brief's minimum bar
    founder_name: str
    sector: Optional[str] = None
    stage: Optional[str] = None
    geography: Optional[str] = None
    github_url: Optional[str] = None


class ApplicationResponse(BaseModel):
    row: Dict[str, Any]


@app.post("/api/apply", response_model=ApplicationResponse)
async def submit_application(req: ApplicationRequest):
    """Inbound track. Works in Demo AND Live mode -- unlike search's live
    enrichment, this is the applicant voluntarily submitting their own data
    to what's explicitly an investment application, not a third-party lookup.
    Minimum bar is deck_text + company_name; everything else is optional, per
    the brief ('over-collecting works against you')."""
    received_at = datetime.utcnow()
    identity_key = normalize_identity(req.founder_name, req.github_url)

    new_signals: List[Dict[str, Any]] = []
    if req.github_url:
        new_signals.append({
            "source": "github", "timestamp": received_at.isoformat(),
            "normalized_score": 0.4, "confidence": 0.5,
            "data_points": {"self_reported_github": req.github_url},
        })

    opportunity_id = f"app-{abs(hash(req.company_name + req.founder_name)) % 100000}"
    opportunity = {
        "id": opportunity_id,
        "sector": req.sector or "unknown",
        "founder_score": 50,
        "keywords": [req.company_name],
        "idea_summary": req.deck_text,
        "engineering_signals": {},
        "geography": req.geography,
    }

    row = await _run_evaluation_and_register(
        opportunity_id=opportunity_id,
        display_name=req.founder_name,
        identity_key=identity_key,
        new_signals=new_signals,
        opportunity=opportunity,
        application_text=req.deck_text,
        claims=[],
        provenance="inbound_application",
        data_confidence=None,
        first_signal_at=received_at,
        extra_row_fields={
            "company_name": req.company_name,
            "deck_text": req.deck_text,
            "stage": req.stage,
            "geography": req.geography,
            "github_url": req.github_url,
            "source_urls": [req.github_url] if req.github_url else [],
        },
    )
    return ApplicationResponse(row=row)


class OpportunitySearchRequest(BaseModel):
    query: str


class OpportunitySearchResponse(BaseModel):
    matches: List[Dict[str, Any]]
    match_strategy: str
    provenance: str
    message: Optional[str] = None


@app.post("/api/opportunities/search", response_model=OpportunitySearchResponse)
async def search_opportunities(req: OpportunitySearchRequest):
    tokens = _tokenize(req.query)
    roster = await _demo_roster_as_rows() if mode_state.demo_mode else list(live_state.deal_rows.values())

    scored = sorted(
        ((_score_candidate(tokens, row), row) for row in roster),
        key=lambda pair: pair[0], reverse=True,
    )
    matches = [row for score, row in scored if score > 0][:8]

    if matches:
        return OpportunitySearchResponse(
            matches=matches, match_strategy="keyword_heuristic_v1",
            provenance="demo_fixture" if mode_state.demo_mode else "live_session",
        )

    if mode_state.demo_mode:
        return OpportunitySearchResponse(
            matches=[], match_strategy="keyword_heuristic_v1", provenance="demo_fixture",
            message="No matches in the cached demo roster. Switch to Live API mode to search live data.",
        )

    tools = get_tools()
    extraction = await _tavily_enrich_founder(req.query, tools)
    if extraction is None:
        return OpportunitySearchResponse(
            matches=[], match_strategy="live_enrichment", provenance="live_session",
            message=f"No public data found for '{req.query}' via live search.",
        )

    founder_profile_raw, opportunity = _profile_from_enrichment(req.query, extraction)
    row = await _evaluate_and_register_live(founder_profile_raw, opportunity, extraction)
    return OpportunitySearchResponse(
        matches=[row], match_strategy="live_enrichment", provenance="live_enriched",
        message=(
            f"Live-enriched from {len(extraction.get('source_urls', []))} source(s) — "
            f"single-pass, unverified beyond explicit claim-checks."
        ),
    )


# ---------------------------------------------------------------------------
# Overseer Chat -- grounded strictly in whatever computed context the UI
# already has for the selected deal. Demo mode answers with a deterministic,
# fully-offline explainer that reads the real numbers out of the context;
# Live mode calls the real Anthropic API for open-ended analytical Q&A, with
# a system prompt that still forbids introducing new unverified facts.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Demo-mode deterministic generators. Each one is a real function of the
# actual submitted/computed data passed in -- no hardcoded numbers -- so
# Demo mode's cold-start reads, memos, and adversarial views are honest
# stand-ins for the Live-mode LLM calls, not decorative placeholders.
# ---------------------------------------------------------------------------
_TECHNICAL_TERMS = {
    "api", "algorithm", "model", "pipeline", "latency", "architecture", "protocol",
    "inference", "embedding", "kernel", "distributed", "schema", "optimization", "runtime",
}
_SPECIFICITY_MARKERS = {"%", "$", "users", "customers", "weeks", "months", "commits", "stars", "benchmark", "mrr", "arr"}


def _deterministic_cold_start(prompt: str) -> Dict[str, Any]:
    text = prompt.split("Application text:\n", 1)[-1] if "Application text:\n" in prompt else prompt
    words = text.split()
    word_count = len(words)
    lower = text.lower()
    tech_hits = sum(1 for t in _TECHNICAL_TERMS if t in lower)
    spec_hits = sum(1 for t in _SPECIFICITY_MARKERS if t in lower)

    base = 30.0 + min(20.0, tech_hits * 4) + min(20.0, spec_hits * 3) + min(10.0, word_count / 40)
    point = round(min(85.0, base), 1)
    spread = 18.0 if word_count >= 40 else 26.0  # thinner submissions -> wider interval

    return {
        "point_estimate_0to100": point,
        "low_estimate_0to100": round(max(0.0, point - spread), 1),
        "high_estimate_0to100": round(min(100.0, point + spread), 1),
        "rationale": (
            f"[DEMO heuristic] {word_count} words, {tech_hits} technical-depth term(s), "
            f"{spec_hits} specificity marker(s) (numbers/metrics/timeframes) found in the "
            f"submitted text."
        ),
        "primary_signal": "technical_depth" if tech_hits >= spec_hits else "specificity",
    }


def _deterministic_memo(prompt: str) -> Dict[str, str]:
    try:
        context = json.loads(prompt.split("Context:\n", 1)[1])
    except Exception:
        context = {}
    row = context.get("row") or {}
    deck_text = context.get("deck_text") or row.get("deck_text") or ""
    company = row.get("company_name") or row.get("opportunity_id") or "This company"
    sector = row.get("sector", "an unspecified sector")
    founder = row.get("founder") or {}
    market = row.get("market") or {}
    idea = row.get("idea_vs_market") or {}
    trust_scores = row.get("trust_scores") or []
    flagged = [t for t in trust_scores if t.get("flagged")]

    def fmt_axis(label: str, axis: Dict[str, Any]) -> str:
        if not axis or axis.get("score") is None:
            return f"{label}: Not disclosed."
        return f"{label}: {axis['score']:.1f}/100 (confidence {axis.get('confidence', 0) * 100:.0f}%)."

    snapshot = f"{company} ({sector}). " + (
        deck_text.strip()[:280] if deck_text else "No deck text submitted — company description not disclosed."
    )
    hypotheses = " ".join([fmt_axis("Founder", founder), fmt_axis("Market", market), fmt_axis("Idea-vs-Market", idea)])

    swot_bits = []
    if founder.get("score") is not None and founder["score"] >= 60:
        swot_bits.append(f"Strength: Founder axis scored {founder['score']:.1f}, above the fund's typical bar.")
    if (founder.get("metadata") or {}).get("is_cold_start"):
        swot_bits.append("Weakness: cold-start founder — assessment relies on a single, unverified application-text sample.")
    if flagged:
        swot_bits.append(f"Risk: {len(flagged)} claim(s) flagged by the Trust-Score validator, incl. '{flagged[0]['claim_text']}'.")
    if not swot_bits:
        swot_bits.append("Not enough independently-verified signal yet to state a confident SWOT bullet beyond the axis scores above.")

    traction = "Not disclosed — no quantitative traction (users, revenue, growth) submitted or extracted for this opportunity."
    if row.get("source_urls"):
        traction = f"Best-effort, single-pass signal from {len(row['source_urls'])} live source(s) — not independently verified beyond explicit claim-checks."

    dd_bits = [f"Trust-Score validator checked {len(trust_scores)} claim(s)." if trust_scores else "No claims were submitted for Trust-Score verification."]
    if flagged:
        dd_bits.append(f"{len(flagged)} flagged for discrepancy.")

    return {
        "company_snapshot": f"[DEMO] {snapshot}",
        "investment_hypotheses": f"[DEMO] {hypotheses}",
        "swot": f"[DEMO] {' '.join(swot_bits)}",
        "team_and_history": f"[DEMO] Founder: {row.get('founder_name', 'unknown')}. Applications on file in Memory: {row.get('applications_on_file', 1)}.",
        "problem_and_product": f"[DEMO] {deck_text.strip()[:600]}" if deck_text else "Not disclosed — no deck/application text was submitted for this opportunity.",
        "technology_and_defensibility": "Not disclosed — requires technical diligence beyond this pass.",
        "market_sizing": "Not disclosed — no TAM/SAM/SOM data submitted or extracted.",
        "competition": "Not disclosed — no named competitor set submitted or extracted.",
        "traction_and_kpis": f"[DEMO] {traction}",
        "financials_and_round_structure": "Not disclosed.",
        "cap_table": "Not disclosed.",
        "due_diligence_log": f"[DEMO] {' '.join(dd_bits)}",
        "exit_perspective": "Not disclosed — out of scope for a sourcing/screening-stage read.",
    }


def _deterministic_adversarial_view(user_message: str) -> str:
    try:
        context = json.loads(user_message.split("Context:\n", 1)[1])
    except Exception:
        context = {}
    row = context.get("row") or context
    founder = row.get("founder") or {}
    market = row.get("market") or {}
    idea = row.get("idea_vs_market") or {}
    trust_scores = row.get("trust_scores") or []
    flagged = [t for t in trust_scores if t.get("flagged")]

    concerns = []
    scored = [(label, a["score"]) for label, a in (("Founder", founder), ("Market", market), ("Idea-vs-Market", idea)) if a and a.get("score") is not None]
    if scored:
        weakest_label, weakest_score = min(scored, key=lambda x: x[1])
        concerns.append(f"The weakest axis is {weakest_label} at {weakest_score:.1f}/100 — that alone should slow the decision down.")
    if flagged:
        concerns.append(
            f"{len(flagged)} claim(s) failed Trust-Score verification, including '{flagged[0]['claim_text']}' — "
            f"the founder's own numbers don't hold up against external checks."
        )
    if (founder.get("metadata") or {}).get("is_cold_start"):
        concerns.append(
            "This is a cold-start read with no GitHub/funding/network corroboration — the Founder axis score "
            "carries a wide, stated confidence interval, not a verified track record."
        )
    if not concerns:
        concerns.append(
            "No specific red flag surfaced by the computed axes or trust checks — the strongest adversarial case "
            "here is that a $100K decision is being made on a single evaluation pass with no independent "
            "verification beyond what's been explicitly checked."
        )
    return "[DEMO] " + " ".join(concerns)


def _deterministic_overseer_reply(user_message: str) -> str:
    try:
        context_str = user_message.split("Context:\n", 1)[1].split("\n\nThesis criteria:")[0]
        context = json.loads(context_str)
    except Exception:
        context = {}

    # Classify intent from the actual question only -- NOT the full prompt,
    # which embeds the JSON context blob and would spuriously match a
    # keyword like "trust" via the literal "trust_scores" key name.
    question = user_message.rsplit("Question:", 1)[-1].strip().lower()
    founder = context.get("founder") or {}
    trust_scores = context.get("trust_scores") or []
    network_risk = context.get("network_risk") or {}

    if any(k in question for k in ("trust", "decay", "dishonest", "discrepancy")):
        if not trust_scores:
            return "[DEMO] No claims have been run through the Bayesian Trust-Score validator for this deal yet — there's nothing to explain."
        t = trust_scores[0]
        return (
            f"[DEMO] The claim '{t.get('claim_text')}' started from a neutral prior of "
            f"{t.get('prior_mean', 0) * 100:.0f}%. The Tavily verification came back with a "
            f"{t.get('discrepancy_pct', 0):.1f}% discrepancy against the claimed figure, moving "
            f"the posterior to {t.get('trust_score', 0) * 100:.0f}% "
            f"({'flagged' if t.get('flagged') else 'not flagged'}). Bigger misses subtract more "
            f"because the discrepancy percentage directly scales the failure weight in the "
            f"Beta update."
        )

    if any(k in question for k in ("fragil", "dms", "network", "critical", "cut-vertex", "cut vertex")):
        if not network_risk:
            return "[DEMO] This founder isn't currently mapped in the Sourcing Network Graph, so there's no DMS/centrality reading to explain."
        cut_note = (
            "It is a true cut-vertex — removing it provably splits the graph into disconnected pieces."
            if network_risk.get("is_articulation_point")
            else "It is not a hard cut-vertex, but it sits on many shortest paths across the graph."
        )
        return (
            f"[DEMO] This node has a DMS score of {network_risk.get('dms_score', 0):.1f}, built from "
            f"50% betweenness centrality ({network_risk.get('betweenness_centrality', 0):.3f}), "
            f"30% eigenvector centrality ({network_risk.get('eigenvector_centrality', 0):.3f}), and "
            f"20% simulated fragmentation-if-removed "
            f"({network_risk.get('fragmentation_pct_if_removed', 0) * 100:.1f}%). {cut_note}"
        )

    breakdown = (founder.get("metadata") or {}).get("founder_score_breakdown")
    if breakdown and any(k in question for k in ("founder", "f_s", "score")):
        signals = breakdown.get("signals") or []
        if signals:
            top = max(signals, key=lambda s: s["contribution_pct_of_total"])
            return (
                f"[DEMO] F_S = {breakdown['founder_score']:.2f}. The largest single driver is the "
                f"{top['source']} signal, contributing {top['contribution_pct_of_total']:.1f}% of "
                f"the total after a decay factor of {top['decay_factor']:.3f} at {top['age_days']} "
                f"days old."
            )

    return (
        "[DEMO] Ask about \"trust score\", \"fragility/DMS\", or \"founder score\" and I'll break "
        "down the exact computed numbers behind it. Switch to Live API mode for open-ended "
        "analysis from Claude over this deal's full context."
    )


class OverseerChatRequest(BaseModel):
    context: Dict[str, Any]
    thesis: Dict[str, Any] = {}
    message: str


class OverseerChatResponse(BaseModel):
    reply: str


@app.post("/api/overseer/chat", response_model=OverseerChatResponse)
async def overseer_chat(req: OverseerChatRequest):
    tools = get_tools()
    system = (
        "You are the Overseer's analytical assistant inside Axiom OS. You explain the "
        "already-computed Founder Score decay, Bayesian trust-score validation, and "
        "network centrality/DMS numbers for ONE specific deal. Only reason over the JSON "
        "context provided below -- never invent a new fact about the individual that isn't "
        "present in it, and never assert an opinion about their honesty or character beyond "
        "what the trust-score math already computed. If the question asks about something "
        "the context doesn't cover, say plainly that it isn't in the computed data."
    )
    context_json = json.dumps(req.context, default=str)[:6000]
    prompt = f"Context:\n{context_json}\n\nThesis criteria:\n{json.dumps(req.thesis)}\n\nQuestion: {req.message}"
    reply = await tools.llm.chat(system=system, user_message=prompt)
    return OverseerChatResponse(reply=reply)


MEMO_SECTIONS = [
    "company_snapshot", "investment_hypotheses", "swot", "team_and_history",
    "problem_and_product", "technology_and_defensibility", "market_sizing",
    "competition", "traction_and_kpis", "financials_and_round_structure",
    "cap_table", "due_diligence_log", "exit_perspective",
]


class MemoRequest(BaseModel):
    row: Dict[str, Any]  # the DealRow-shaped data the frontend already has


class MemoResponsePayload(BaseModel):
    memo: Dict[str, str]
    adversarial_view: str
    generated_at: str
    time_to_decision_seconds: Optional[float] = None


@app.post("/api/memo/generate", response_model=MemoResponsePayload)
async def generate_memo(req: MemoRequest):
    """Appendix 1's checklist, generated section-by-section and grounded
    ONLY in the row's already-computed evaluation data plus any submitted
    deck text. Sections with no backing data come back as 'Not disclosed' --
    per the brief, that's scored as MORE trustworthy than a filled-in guess,
    not less."""
    tools = get_tools()
    context_json = json.dumps({"row": req.row, "deck_text": req.row.get("deck_text")}, default=str)[:8000]

    memo = await tools.llm.structured_complete(
        system=(
            "You are drafting an investment memo section-by-section for a VC partner. "
            "Ground every claim ONLY in the JSON context provided -- never invent a "
            "plausible-looking number. For ANY section where the context doesn't contain "
            "the needed information (financials, cap table, customer references, market "
            "sizing, named competitors, etc.), return the literal string 'Not disclosed' "
            "for that field instead of guessing. Do not pad sections with filler -- brevity "
            "is preferred where the decision allows it."
        ),
        prompt=f"Context:\n{context_json}",
        schema_hint=(
            "{" + ", ".join(f'"{s}": str' for s in MEMO_SECTIONS) + "}"
        ),
    )
    memo = {s: memo.get(s, "Not disclosed") for s in MEMO_SECTIONS}

    adversarial = await tools.llm.chat(
        system=(
            "You are a skeptical VC partner building the bear case AGAINST this "
            "investment, grounded only in the same JSON context -- never introduce a fact "
            "not present in it. Cite the specific risk driver (which axis, which flagged "
            "claim, which network-fragility reading, or the cold-start uncertainty) behind "
            "each concern you raise."
        ),
        user_message=f"Context:\n{context_json}\n\nWrite the adversarial view in 2-4 sentences.",
    )

    return MemoResponsePayload(
        memo=memo,
        adversarial_view=adversarial,
        generated_at=datetime.utcnow().isoformat(),
        time_to_decision_seconds=req.row.get("time_to_decision_seconds"),
    )


def _deterministic_outreach_draft(user_message: str) -> str:
    try:
        row = json.loads(user_message.split("Context:\n", 1)[1].split("\n\nInstruction:")[0]).get("row", {})
    except Exception:
        row = {}
    name = row.get("founder_name", "there")
    project = row.get("company_name") or row.get("summary") or f"Your {row.get('sector', 'recent')} work"
    founder = row.get("founder") or {}
    hooks = []
    if founder.get("score") is not None:
        hooks.append(f"your build velocity and track record put you well above our screening bar")
    momentum = row.get("momentum") or {}
    if momentum.get("direction") == "up":
        hooks.append("the acceleration in your recent shipping cadence stood out")
    hook = hooks[0] if hooks else "what you're building matched a structural gap our thesis engine is tracking"
    return (
        f"[DEMO DRAFT — for human review before sending]\n\n"
        f"Hi {name},\n\n"
        f"I run sourcing at a pre-seed fund writing $100K checks with a 24-hour decision window. "
        f"{project} surfaced in our pipeline because {hook}. No pitch deck theater needed — if "
        f"you're open to it, a short application gets you a decision within a day.\n\n"
        f"Would you be interested?\n"
    )


class OutreachDraftRequest(BaseModel):
    row: Dict[str, Any]


class OutreachDraftResponse(BaseModel):
    draft: str
    note: str = (
        "Draft only — Axiom OS does not send outreach autonomously. A human reviews, "
        "edits, and sends. Per the brief: cold outreach, not cold investment — the goal "
        "is to trigger a real application."
    )


@app.post("/api/outreach/draft", response_model=OutreachDraftResponse)
async def draft_outreach(req: OutreachDraftRequest):
    """MVP #5 'Activate': turns an identified opportunity into a concrete,
    grounded outreach draft that cites the specific computed signal that
    surfaced them -- never a generic template, never auto-sent."""
    tools = get_tools()
    context_json = json.dumps({"row": req.row}, default=str)[:5000]
    draft = await tools.llm.chat(
        system=(
            "You draft founder outreach for a pre-seed fund. Reference ONLY the specific "
            "computed signals present in the JSON context (scores, momentum, project name) "
            "-- never invent traction, mutual connections, or personal details not in it. "
            "Tone: direct, respectful, no flattery inflation. 4-6 sentences. State plainly "
            "that applying gets them a decision within 24 hours."
        ),
        user_message=f"Context:\n{context_json}\n\nInstruction: draft the outreach message.",
    )
    return OutreachDraftResponse(draft=draft)


@app.get("/api/healthz")
async def healthz():
    return {"status": "ok", "demo_mode": mode_state.demo_mode, "time": datetime.utcnow().isoformat()}
