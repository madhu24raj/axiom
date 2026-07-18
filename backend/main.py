"""
main.py
-------
FastAPI entrypoint for The VC Brain.

Responsibilities:
- Own the global Live / Demo mode toggle (single source of truth, exposed
  via GET/POST /api/mode so the frontend context can read + flip it).
- Implement LiveTavilyClient / CachedTavilyClient and LiveLLMClient /
  CachedLLMClient, both satisfying the Protocols in agents.py, so the
  agent mesh never has to know which one it's talking to.
- Expose the pipeline: thesis filter -> 3-axis screen -> validator ->
  investment memo, for both Mode A (historical simulation replay) and
  Mode B (live/cached hackathon ingestion).

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
from scoring import FounderProfile, SignalMetric, MomentumTracker
from agents import (
    AgentTools, ThesisEngine, ThesisCriteria, DealOrchestrator, DealEvaluation,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("vc_brain.main")

app = FastAPI(title="The VC Brain", version="0.1.0")

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
        # Normalize Tavily's raw shape into the schema our agents expect.
        return {
            "source_label": "tavily_live",
            "urls": [r.get("url") for r in data.get("results", [])],
            "competitor_count": len(data.get("results", [])),
            "saturation_index": None,   # requires downstream LLM synthesis of raw results
            "extracted_value": None,    # claim-specific extraction happens in ValidatorAgent's caller
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
                    "verified": v["verified"],
                }
        # Generic fallback demo response
        return {
            "source_label": "tavily_cached",
            "urls": ["https://example.com/demo-source"],
            "competitor_count": 5,
            "saturation_index": 0.30,
            "extracted_value": None,
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
# Mode A: Reverse Sourcing historical simulation replay
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


@app.get("/api/healthz")
async def healthz():
    return {"status": "ok", "demo_mode": mode_state.demo_mode, "time": datetime.utcnow().isoformat()}
