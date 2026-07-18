"""
scoring.py
----------
Core quantitative engines for The VC Brain:

1. FounderScoreEngine   -> exponentially-decayed, multi-source Founder Score (F_S)
2. TrustScoreEngine     -> Bayesian per-claim trust scoring against Tavily
                            verification evidence
3. MomentumTracker      -> helper for turning score_history into a directional
                            arrow ( up / flat / down ) for the pipeline UI

All models are pure-Python / Pydantic with no framework dependencies so they
can be unit-tested in isolation from FastAPI or any LLM call.
"""

from __future__ import annotations

import math
import logging
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field, HttpUrl

logger = logging.getLogger("vc_brain.scoring")


# ---------------------------------------------------------------------------
# Shared enums / models (mirrors the schema in the developer prompt)
# ---------------------------------------------------------------------------
class SignalSource(str, Enum):
    GITHUB = "github"
    HACKATHON = "hackathon"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    ARXIV = "arxiv"
    INBOUND_DECK = "inbound_deck"


class SignalMetric(BaseModel):
    source: SignalSource
    timestamp: datetime
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    normalized_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    data_points: Dict[str, Any] = Field(default_factory=dict)


class FounderProfile(BaseModel):
    founder_id: str
    name: str
    public_footprints: Dict[str, HttpUrl] = Field(default_factory=dict)
    historical_signals: List[SignalMetric] = Field(default_factory=list)
    current_founder_score: float = 0.0
    score_history: List[Dict[str, Any]] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class MomentumDirection(str, Enum):
    UP = "up"
    FLAT = "flat"
    DOWN = "down"


# ---------------------------------------------------------------------------
# 1. Founder Score Engine
#
#   F_S = sum_i  w_i * ( S_i * e^(-lambda * t_i) )
#
# w_i     -> source-specific weight (predictive-value prior)
# S_i     -> normalized signal strength in [0, 1]
# t_i     -> age of the signal in days
# lambda  -> decay constant; higher = more emphasis on *recent* velocity
#            over absolute historical scale
# ---------------------------------------------------------------------------
class FounderScoreEngine:
    def __init__(self, lambda_decay: float = 0.05):
        self.lambda_decay = lambda_decay
        self.weights: Dict[SignalSource, float] = {
            SignalSource.GITHUB: 0.35,
            SignalSource.HACKATHON: 0.30,
            SignalSource.ARXIV: 0.15,
            SignalSource.TWITTER: 0.10,
            SignalSource.LINKEDIN: 0.10,
            SignalSource.INBOUND_DECK: 0.20,
        }

    def calculate_score(self, signals: List[SignalMetric]) -> float:
        """Returns a 0-100 Founder Score."""
        if not signals:
            return 0.0

        total = 0.0
        now = datetime.utcnow()

        for sig in signals:
            t_days = max(0, (now - sig.timestamp).days)
            decay = math.exp(-self.lambda_decay * t_days)
            weight = self.weights.get(sig.source, 0.10)
            contribution = weight * sig.normalized_score * decay
            total += contribution
            logger.debug(
                "signal=%s age_days=%d decay=%.4f weight=%.2f contribution=%.4f",
                sig.source.value, t_days, decay, weight, contribution,
            )

        score = min(100.0, round(total * 100, 2))
        logger.info("Computed Founder Score = %.2f from %d signals", score, len(signals))
        return score

    def score_and_update(self, profile: FounderProfile) -> FounderProfile:
        """Recompute F_S, append to score_history, and return the mutated profile."""
        new_score = self.calculate_score(profile.historical_signals)
        profile.score_history.append(
            {"timestamp": datetime.utcnow().isoformat(), "score": new_score}
        )
        profile.current_founder_score = new_score
        profile.last_updated = datetime.utcnow()
        return profile


# ---------------------------------------------------------------------------
# 2. Bayesian Trust Score Engine
#
# For each atomic claim extracted from a deck / social footprint, we treat
# "claim is true" as a hidden variable and update a Beta-distributed belief
# using Tavily verification evidence as (successes, failures) pseudo-counts.
#
#   posterior_mean = (alpha_prior + successes) / (alpha_prior + beta_prior + n)
#
# Discrepancy magnitude scales how much a single verification "counts" --
# a claim that is off by 3% moves the score far less than one off by 90%.
# ---------------------------------------------------------------------------
class ClaimVerification(BaseModel):
    claim_text: str
    claimed_value: Optional[float] = None
    extracted_value: Optional[float] = None
    source_url: Optional[str] = None
    verified: bool


class TrustScoreResult(BaseModel):
    claim_text: str
    trust_score: float = Field(..., ge=0.0, le=1.0)
    discrepancy_pct: Optional[float] = None
    flagged: bool
    evidence: List[ClaimVerification]


class TrustScoreEngine:
    def __init__(self, alpha_prior: float = 2.0, beta_prior: float = 2.0):
        # Weakly-informative symmetric prior: no assumption of honesty or
        # dishonesty before any evidence is gathered.
        self.alpha_prior = alpha_prior
        self.beta_prior = beta_prior

    @staticmethod
    def _discrepancy_pct(claimed: float, extracted: float) -> float:
        if claimed == 0:
            return 0.0 if extracted == 0 else 100.0
        return round(abs(claimed - extracted) / abs(claimed) * 100, 1)

    def score_claim(
        self, claim_text: str, evidence: List[ClaimVerification]
    ) -> TrustScoreResult:
        if not evidence:
            # No verification attempted yet -> return prior mean, unflagged
            # but implicitly low-confidence (n=0).
            prior_mean = self.alpha_prior / (self.alpha_prior + self.beta_prior)
            return TrustScoreResult(
                claim_text=claim_text,
                trust_score=round(prior_mean, 3),
                discrepancy_pct=None,
                flagged=False,
                evidence=[],
            )

        successes = 0.0
        failures = 0.0
        max_discrepancy = 0.0

        for ev in evidence:
            if ev.claimed_value is not None and ev.extracted_value is not None:
                disc = self._discrepancy_pct(ev.claimed_value, ev.extracted_value)
                max_discrepancy = max(max_discrepancy, disc)
                weight = disc / 100.0
                if ev.verified and disc <= 5.0:
                    successes += 1.0
                else:
                    failures += 1.0 + weight  # bigger miss = stronger penalty
            else:
                successes += 1.0 if ev.verified else 0.0
                failures += 0.0 if ev.verified else 1.0

        n = successes + failures
        posterior_mean = (self.alpha_prior + successes) / (
            self.alpha_prior + self.beta_prior + n
        )
        flagged = max_discrepancy >= 15.0 or posterior_mean < 0.4

        result = TrustScoreResult(
            claim_text=claim_text,
            trust_score=round(posterior_mean, 3),
            discrepancy_pct=max_discrepancy or None,
            flagged=flagged,
            evidence=evidence,
        )
        logger.info(
            "Trust score for claim %r = %.3f (flagged=%s, max_discrepancy=%.1f%%)",
            claim_text, result.trust_score, flagged, max_discrepancy,
        )
        return result


# ---------------------------------------------------------------------------
# 3. Momentum Tracker -- converts score_history into a UI-ready direction
# ---------------------------------------------------------------------------
class MomentumTracker:
    @staticmethod
    def direction(score_history: List[Dict[str, Any]], flat_epsilon: float = 1.5) -> MomentumDirection:
        if len(score_history) < 2:
            return MomentumDirection.FLAT
        delta = score_history[-1]["score"] - score_history[-2]["score"]
        if delta > flat_epsilon:
            return MomentumDirection.UP
        if delta < -flat_epsilon:
            return MomentumDirection.DOWN
        return MomentumDirection.FLAT

    @staticmethod
    def arrow(direction: MomentumDirection) -> str:
        return {"up": "\u2197", "flat": "\u2192", "down": "\u2198"}[direction.value]
