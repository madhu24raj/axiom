"""
agents.py
---------
Asynchronous agent mesh for The VC Brain / Axiom OS.

    Thesis Engine Filter
            |
            v
   +--------+--------+--------+
   |        |        |        |
Founder  Market   Idea-vs-Mkt   (independent, NOT averaged)
   |        |        |
   +--------+--------+
            |
            v
     Validator Agent (Tavily truth-gap)
            |
            v
   Traceable AxisResult[] -> Investment Memo

Every agent returns an AxisResult that carries its own chain-of-thought
trace and raw source references, so the frontend's Agentic Traceability
panel has something real to render rather than a black box.

Design choices:
- All agents are `async def` so the orchestrator can run the three axes
  concurrently with `asyncio.gather`.
- Each agent accepts a `demo_mode: bool` flag and an injected `tools`
  object (OpenAIClient / TavilyClient wrappers) so main.py owns all
  live-vs-cached routing -- agents never decide that for themselves.
- No agent silently fabricates a number. If a data point is missing,
  it is returned as None and the caller is responsible for rendering
  the "[Not Disclosed]" placeholder -- this file never invents values.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

from scoring import (
    FounderScoreEngine,
    FounderProfile,
    TrustScoreEngine,
    ClaimVerification,
    TrustScoreResult,
)

logger = logging.getLogger("vc_brain.agents")


# ---------------------------------------------------------------------------
# Tool protocols -- main.py supplies concrete Live or Cached implementations
# that satisfy these interfaces. Agents only ever talk to these interfaces.
# ---------------------------------------------------------------------------
class TavilyClient(Protocol):
    async def search(self, query: str) -> Dict[str, Any]: ...


class LLMClient(Protocol):
    async def structured_complete(
        self, system: str, prompt: str, schema_hint: str
    ) -> Dict[str, Any]: ...


@dataclass
class AgentTools:
    tavily: TavilyClient
    llm: LLMClient
    demo_mode: bool = False


# ---------------------------------------------------------------------------
# Shared result envelope -- powers the Agentic Traceability UI
# ---------------------------------------------------------------------------
class MacroStance(str, Enum):
    BULL = "bull"
    NEUTRAL = "neutral"
    BEAR = "bear"


@dataclass
class ReasoningStep:
    step: str
    detail: str
    source_ref: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class AxisResult:
    axis: str
    score: Optional[float]              # None -> "[Not Disclosed]" in UI, never fabricated
    confidence: float
    reasoning_trace: List[ReasoningStep]
    raw_refs: List[str]
    # Structured, axis-specific math the Overseer panel can render directly
    # (e.g. the Founder axis's per-signal F_S breakdown). Left as a plain
    # dict so each axis can carry its own shape without a proliferation of
    # near-identical dataclasses; always populated from a real computation,
    # never fabricated for display.
    metadata: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 0. Thesis Engine Filter -- LP-configurable JSON criteria gate
# ---------------------------------------------------------------------------
@dataclass
class ThesisCriteria:
    min_check_fit_usd: int = 100_000
    target_sectors: List[str] = field(default_factory=lambda: ["dev tools", "infra", "agentic systems"])
    excluded_sectors: List[str] = field(default_factory=list)
    min_founder_score: float = 40.0
    stage: str = "pre-seed"


class ThesisEngine:
    """Filters raw opportunities against LP-set thesis criteria before any
    agent spends compute on deep evaluation."""

    def __init__(self, criteria: ThesisCriteria):
        self.criteria = criteria

    def passes(self, opportunity: Dict[str, Any]) -> ReasoningStep:
        sector = opportunity.get("sector", "unknown")
        founder_score = opportunity.get("founder_score", 0.0)

        sector_ok = (
            not self.criteria.target_sectors
            or sector in self.criteria.target_sectors
        ) and sector not in self.criteria.excluded_sectors
        score_ok = founder_score >= self.criteria.min_founder_score

        passed = sector_ok and score_ok
        detail = (
            f"sector='{sector}' (target={self.criteria.target_sectors}, "
            f"excluded={self.criteria.excluded_sectors}) -> {sector_ok}; "
            f"founder_score={founder_score} >= {self.criteria.min_founder_score} -> {score_ok}"
        )
        logger.info("ThesisEngine.passes(%s) = %s", opportunity.get("id"), passed)
        return ReasoningStep(
            step="thesis_filter",
            detail=f"PASS: {detail}" if passed else f"REJECT: {detail}",
        )


# ---------------------------------------------------------------------------
# 1. Founder Axis Agent
# ---------------------------------------------------------------------------
class FounderAxisAgent:
    def __init__(self, tools: AgentTools):
        self.tools = tools
        self.score_engine = FounderScoreEngine()

    async def evaluate(self, profile: FounderProfile) -> AxisResult:
        trace: List[ReasoningStep] = []
        refs: List[str] = list(profile.public_footprints.values()) if profile.public_footprints else []

        breakdown = self.score_engine.calculate_score_breakdown(profile.historical_signals)
        f_s = breakdown.founder_score
        trace.append(ReasoningStep(
            step="founder_score_calc",
            detail=(
                f"F_S computed from {len(profile.historical_signals)} decayed signals = {f_s} "
                f"(lambda={breakdown.lambda_decay})"
            ),
        ))

        # Skill matrix / grit -- delegated to the LLM for qualitative read,
        # grounded only in the raw signal payloads actually present.
        if profile.historical_signals:
            llm_result = await self.tools.llm.structured_complete(
                system="You are a VC founder-diligence analyst. Only use provided signals.",
                prompt=f"Assess skill matrix and grit from signals: {profile.historical_signals}",
                schema_hint='{"skill_notes": str, "grit_notes": str}',
            )
            trace.append(ReasoningStep(
                step="skill_grit_assessment",
                detail=str(llm_result),
            ))
        else:
            trace.append(ReasoningStep(
                step="skill_grit_assessment",
                detail="[Skill/Grit: Not Disclosed — no signals available]",
            ))

        confidence = min(1.0, 0.3 + 0.1 * len(profile.historical_signals))
        return AxisResult(
            axis="founder", score=f_s, confidence=round(confidence, 2),
            reasoning_trace=trace, raw_refs=[str(r) for r in refs],
            metadata={"founder_score_breakdown": breakdown.model_dump()},
        )


# ---------------------------------------------------------------------------
# 2. Market Axis Agent (Tavily-backed competitor clustering + macro read)
# ---------------------------------------------------------------------------
class MarketAxisAgent:
    def __init__(self, tools: AgentTools):
        self.tools = tools

    async def evaluate(self, sector: str, keywords: List[str]) -> AxisResult:
        trace: List[ReasoningStep] = []
        refs: List[str] = []

        query = f"competitors in {sector}: {', '.join(keywords)}"
        search_result = await self.tools.tavily.search(query)
        trace.append(ReasoningStep(
            step="tavily_competitor_search", detail=f"query='{query}'",
            source_ref=search_result.get("source_label"),
        ))
        refs.extend(search_result.get("urls", []))

        competitor_count = search_result.get("competitor_count")
        saturation = search_result.get("saturation_index")

        if saturation is None:
            macro = MacroStance.NEUTRAL
            trace.append(ReasoningStep(step="macro_stance", detail="[Saturation index: Not Disclosed]"))
            score = None
        else:
            macro = MacroStance.BEAR if saturation > 0.7 else (
                MacroStance.BULL if saturation < 0.35 else MacroStance.NEUTRAL
            )
            score = round((1 - saturation) * 100, 2)
            trace.append(ReasoningStep(
                step="macro_stance",
                detail=f"saturation={saturation} -> stance={macro.value}, market_score={score}",
            ))

        trace.append(ReasoningStep(
            step="competitor_clustering",
            detail=f"competitor_count={competitor_count if competitor_count is not None else '[Not Disclosed]'}",
        ))

        return AxisResult(
            axis="market", score=score, confidence=0.6 if score is not None else 0.2,
            reasoning_trace=trace, raw_refs=refs,
            metadata={"saturation_index": saturation, "macro_stance": macro.value, "competitor_count": competitor_count},
        )


# ---------------------------------------------------------------------------
# 3. Idea-vs-Market Axis Agent
# ---------------------------------------------------------------------------
class IdeaMarketAxisAgent:
    def __init__(self, tools: AgentTools):
        self.tools = tools

    async def evaluate(self, idea_summary: str, engineering_signals: Dict[str, Any]) -> AxisResult:
        trace: List[ReasoningStep] = []

        prompt = (
            "Given idea summary and engineering velocity signals, answer: "
            "if this market shifts, does this engineering core have the "
            "velocity to successfully pivot? Ground your answer only in "
            f"the provided data.\nIdea: {idea_summary}\nSignals: {engineering_signals}"
        )
        llm_result = await self.tools.llm.structured_complete(
            system="You are a structural-defensibility analyst for early-stage venture bets.",
            prompt=prompt,
            schema_hint='{"pivot_velocity_score": float (0-100), "rationale": str}',
        )
        trace.append(ReasoningStep(step="pivot_defensibility_llm_call", detail=str(llm_result)))

        score = llm_result.get("pivot_velocity_score")
        return AxisResult(
            axis="idea_vs_market",
            score=score,
            confidence=0.55,
            reasoning_trace=trace,
            raw_refs=[],
            metadata={"rationale": llm_result.get("rationale")},
        )


# ---------------------------------------------------------------------------
# 4. Validator Agent -- Bayesian Trust-Score cross-referencing via Tavily
# ---------------------------------------------------------------------------
class ValidatorAgent:
    def __init__(self, tools: AgentTools):
        self.tools = tools
        self.trust_engine = TrustScoreEngine()

    async def verify_claim(
        self, claim_text: str, claimed_value: Optional[float], verification_query: str
    ) -> TrustScoreResult:
        search_result = await self.tools.tavily.search(verification_query)
        extracted_value = search_result.get("extracted_value")

        verified_flag = search_result.get("verified")
        if verified_flag is None:
            # Tool didn't tell us explicitly -> derive from numeric closeness,
            # but only if we actually have both numbers to compare.
            verified_flag = bool(
                extracted_value is not None
                and claimed_value is not None
                and abs(extracted_value - claimed_value) / max(abs(claimed_value), 1) < 0.05
            )

        evidence = [ClaimVerification(
            claim_text=claim_text,
            claimed_value=claimed_value,
            extracted_value=extracted_value,
            source_url=(search_result.get("urls") or [None])[0],
            evidence_excerpt=search_result.get("evidence_excerpt"),
            verified=verified_flag,
        )]
        result = self.trust_engine.score_claim(claim_text, evidence)
        logger.info("ValidatorAgent verified claim=%r -> trust=%.2f flagged=%s",
                    claim_text, result.trust_score, result.flagged)
        return result


# ---------------------------------------------------------------------------
# Orchestrator -- fan-out the 3 independent axes, then validate, without
# ever collapsing the three axis scores into a single averaged number
# (per the "No Averaging!" requirement).
# ---------------------------------------------------------------------------
@dataclass
class DealEvaluation:
    opportunity_id: str
    thesis_check: ReasoningStep
    founder: Optional[AxisResult]
    market: Optional[AxisResult]
    idea_vs_market: Optional[AxisResult]
    trust_scores: List[TrustScoreResult]
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class DealOrchestrator:
    def __init__(self, tools: AgentTools, thesis: ThesisEngine):
        self.tools = tools
        self.thesis = thesis
        self.founder_agent = FounderAxisAgent(tools)
        self.market_agent = MarketAxisAgent(tools)
        self.idea_agent = IdeaMarketAxisAgent(tools)
        self.validator = ValidatorAgent(tools)

    async def run(
        self,
        opportunity: Dict[str, Any],
        founder_profile: FounderProfile,
        claims_to_verify: List[Dict[str, Any]],
    ) -> DealEvaluation:
        thesis_check = self.thesis.passes(opportunity)
        if thesis_check.step == "thesis_filter" and thesis_check.detail.startswith("REJECT"):
            return DealEvaluation(
                opportunity_id=opportunity.get("id", "unknown"),
                thesis_check=thesis_check,
                founder=None, market=None, idea_vs_market=None,
                trust_scores=[],
            )

        # Independent, concurrent, NOT averaged.
        founder_res, market_res, idea_res = await asyncio.gather(
            self.founder_agent.evaluate(founder_profile),
            self.market_agent.evaluate(
                opportunity.get("sector", "unknown"), opportunity.get("keywords", [])
            ),
            self.idea_agent.evaluate(
                opportunity.get("idea_summary", ""), opportunity.get("engineering_signals", {})
            ),
        )

        trust_results = await asyncio.gather(*[
            self.validator.verify_claim(
                c["claim_text"], c.get("claimed_value"), c["verification_query"]
            )
            for c in claims_to_verify
        ]) if claims_to_verify else []

        return DealEvaluation(
            opportunity_id=opportunity.get("id", "unknown"),
            thesis_check=thesis_check,
            founder=founder_res,
            market=market_res,
            idea_vs_market=idea_res,
            trust_scores=list(trust_results),
        )
