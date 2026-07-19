"""
scoring.py
----------
Core quantitative engines for The VC Brain / Axiom OS:

1. FounderScoreEngine   -> exponentially-decayed, multi-source Founder Score (F_S),
                            plus a per-signal breakdown for the Overseer panel
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
from datetime import datetime, timezone
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
    # Persistent log of cold-start (no-GitHub/no-funding/no-network) reads --
    # kept separate from historical_signals because it's a different kind of
    # evidence (a single unverified text sample) and blended, not formula-
    # weighted, across applications. See FounderAxisAgent._blend_cold_start.
    cold_start_history: List[Dict[str, Any]] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class MomentumDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    PIVOT = "pivot"     # a genuine trend reversal, not just noise
    FLAT = "flat"


# ---------------------------------------------------------------------------
# Momentum Vector -- direction + the actual velocity/acceleration numbers
# behind it, so the UI never has to take "up" or "down" on faith.
# ---------------------------------------------------------------------------
class MomentumVector(BaseModel):
    direction: MomentumDirection
    arrow: str
    velocity: float           # signed rate of change over the most recent window
    prior_velocity: Optional[float] = None
    accelerating: bool = False
    basis: str                # "score_history" | "signal_frequency" | "insufficient_data"
    note: str


# ---------------------------------------------------------------------------
# Per-signal breakdown -- powers the Overseer's "show your work" math panel.
# Every field here is read directly off the same computation the final F_S
# number comes from; nothing is recomputed or approximated for display.
# ---------------------------------------------------------------------------
class SignalContribution(BaseModel):
    source: SignalSource
    age_days: int
    normalized_score: float
    source_weight: float
    decay_factor: float
    contribution: float          # source_weight * normalized_score * decay_factor
    contribution_pct_of_total: float  # what % of F_S this single signal explains


class FounderScoreBreakdown(BaseModel):
    founder_score: float
    lambda_decay: float
    signals: List[SignalContribution]


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

    @staticmethod
    def _age_days(sig_timestamp: datetime, now: datetime) -> int:
        sig_time = sig_timestamp if sig_timestamp.tzinfo else sig_timestamp.replace(tzinfo=timezone.utc)
        safe_now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        return max(0, (safe_now - sig_time).days)

    def calculate_score(self, signals: List[SignalMetric]) -> float:
        """Returns a 0-100 Founder Score."""
        if not signals:
            return 0.0

        total = 0.0
        now = datetime.utcnow()

        for sig in signals:
            t_days = self._age_days(sig.timestamp, now)
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

    def calculate_score_breakdown(self, signals: List[SignalMetric]) -> FounderScoreBreakdown:
        """Same math as calculate_score, but returns the full per-signal
        ledger so the Overseer panel can render exactly how F_S was built,
        signal by signal, instead of a single opaque number."""
        if not signals:
            return FounderScoreBreakdown(
                founder_score=0.0, lambda_decay=self.lambda_decay, signals=[]
            )

        now = datetime.utcnow()
        raw_contributions: List[Dict[str, Any]] = []
        total = 0.0

        for sig in signals:
            t_days = self._age_days(sig.timestamp, now)
            decay = math.exp(-self.lambda_decay * t_days)
            weight = self.weights.get(sig.source, 0.10)
            contribution = weight * sig.normalized_score * decay
            total += contribution
            raw_contributions.append({
                "source": sig.source,
                "age_days": t_days,
                "normalized_score": sig.normalized_score,
                "source_weight": weight,
                "decay_factor": round(decay, 4),
                "contribution": contribution,
            })

        score = min(100.0, round(total * 100, 2))
        signal_rows = [
            SignalContribution(
                source=row["source"],
                age_days=row["age_days"],
                normalized_score=row["normalized_score"],
                source_weight=row["source_weight"],
                decay_factor=row["decay_factor"],
                contribution=round(row["contribution"] * 100, 3),
                contribution_pct_of_total=(
                    round((row["contribution"] / total) * 100, 2) if total > 0 else 0.0
                ),
            )
            for row in raw_contributions
        ]
        return FounderScoreBreakdown(
            founder_score=score, lambda_decay=self.lambda_decay, signals=signal_rows
        )

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
    evidence_excerpt: Optional[str] = None  # short cached/live snippet the Overseer can read
    verified: bool


class TrustScoreResult(BaseModel):
    claim_text: str
    trust_score: float = Field(..., ge=0.0, le=1.0)
    discrepancy_pct: Optional[float] = None
    flagged: bool
    prior_mean: float
    posterior_successes: float
    posterior_failures: float
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
        prior_mean = self.alpha_prior / (self.alpha_prior + self.beta_prior)

        if not evidence:
            # No verification attempted yet -> return prior mean, unflagged
            # but implicitly low-confidence (n=0).
            return TrustScoreResult(
                claim_text=claim_text,
                trust_score=round(prior_mean, 3),
                discrepancy_pct=None,
                flagged=False,
                prior_mean=round(prior_mean, 3),
                posterior_successes=0.0,
                posterior_failures=0.0,
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
            prior_mean=round(prior_mean, 3),
            posterior_successes=successes,
            posterior_failures=failures,
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
    """Classifies momentum from real deltas -- never a hardcoded fallback
    string. Two data sources, tried in order:

    1. score_history  -- if the profile has been scored 2+ times, compare
       consecutive deltas. A same-signed delta that's growing/shrinking is
       UP/DOWN; a delta that *reverses sign* against the prior delta (beyond
       noise) is classified PIVOT -- the founder's trajectory genuinely
       changed direction, which is a distinct, higher-attention signal than
       "just slightly down."
    2. signal_frequency -- for a profile with no score_history yet (e.g. a
       founder ingested moments ago via the live search bar), bucket its
       raw signals into three trailing 7-day windows by timestamp and run
       the identical reversal logic over bucket intensity instead of score.
       This is what lets momentum mean something on the very first
       evaluation of a live-enriched founder, instead of silently
       defaulting to FLAT.
    """

    ARROWS = {
        MomentumDirection.UP: "\u2197",      # ↗
        MomentumDirection.DOWN: "\u2198",    # ↘
        MomentumDirection.PIVOT: "\u21CC",   # ⇌
        MomentumDirection.FLAT: "\u2192",    # →
    }

    @classmethod
    def arrow(cls, direction: MomentumDirection) -> str:
        return cls.ARROWS[direction]

    @classmethod
    def _classify_deltas(
        cls, latest_delta: float, prior_delta: Optional[float], flat_epsilon: float
    ) -> MomentumDirection:
        if prior_delta is not None:
            reversed_up_to_down = prior_delta > flat_epsilon and latest_delta < -flat_epsilon
            reversed_down_to_up = prior_delta < -flat_epsilon and latest_delta > flat_epsilon
            if reversed_up_to_down or reversed_down_to_up:
                return MomentumDirection.PIVOT
        if latest_delta > flat_epsilon:
            return MomentumDirection.UP
        if latest_delta < -flat_epsilon:
            return MomentumDirection.DOWN
        return MomentumDirection.FLAT

    @classmethod
    def from_score_history(
        cls, score_history: List[Dict[str, Any]], flat_epsilon: float = 1.5
    ) -> MomentumVector:
        if len(score_history) < 2:
            return MomentumVector(
                direction=MomentumDirection.FLAT, arrow=cls.arrow(MomentumDirection.FLAT),
                velocity=0.0, basis="insufficient_data",
                note="Fewer than 2 score_history points — no trend to measure yet.",
            )

        deltas = [
            score_history[i]["score"] - score_history[i - 1]["score"]
            for i in range(1, len(score_history))
        ]
        latest_delta = deltas[-1]
        prior_delta = deltas[-2] if len(deltas) >= 2 else None
        direction = cls._classify_deltas(latest_delta, prior_delta, flat_epsilon)
        accelerating = prior_delta is not None and abs(latest_delta) > abs(prior_delta)

        note = f"Δscore latest={latest_delta:+.2f}"
        if prior_delta is not None:
            note += f", prior={prior_delta:+.2f}"
        if direction == MomentumDirection.PIVOT:
            note += " — trend reversed direction, not just decelerating."

        return MomentumVector(
            direction=direction, arrow=cls.arrow(direction),
            velocity=round(latest_delta, 2),
            prior_velocity=round(prior_delta, 2) if prior_delta is not None else None,
            accelerating=accelerating, basis="score_history", note=note,
        )

    @classmethod
    def from_signals(
        cls, signals: List[SignalMetric], window_days: int = 7, flat_epsilon: float = 0.08
    ) -> MomentumVector:
        """Fallback for founders with no score_history yet: bucket raw
        signals by age into three trailing windows and treat mean
        normalized_score per bucket as an intensity proxy, then run the
        same reversal-aware classifier over bucket-to-bucket deltas."""
        if not signals:
            return MomentumVector(
                direction=MomentumDirection.FLAT, arrow=cls.arrow(MomentumDirection.FLAT),
                velocity=0.0, basis="insufficient_data",
                note="No signals available to derive a momentum trend.",
            )

        now = datetime.utcnow()
        buckets = [[], [], []]  # [0-7d], [7-14d], [14-21d]
        for sig in signals:
            age = FounderScoreEngine._age_days(sig.timestamp, now)
            idx = age // window_days
            if idx <= 2:
                buckets[int(idx)].append(sig.normalized_score)

        def bucket_mean(vals: List[float]) -> Optional[float]:
            return round(sum(vals) / len(vals), 4) if vals else None

        recent, mid, old = (bucket_mean(b) for b in buckets)

        if recent is None or mid is None:
            return MomentumVector(
                direction=MomentumDirection.FLAT, arrow=cls.arrow(MomentumDirection.FLAT),
                velocity=0.0, basis="signal_frequency",
                note="Not enough signal history across trailing windows to derive a trend yet.",
            )

        latest_delta = recent - mid
        prior_delta = (mid - old) if old is not None else None
        # Signal-intensity deltas live on a 0-1 scale; scale threshold accordingly.
        direction = cls._classify_deltas(latest_delta, prior_delta, flat_epsilon)
        accelerating = prior_delta is not None and abs(latest_delta) > abs(prior_delta)

        note = f"Signal intensity Δ(0-7d vs 7-14d)={latest_delta:+.3f}"
        if prior_delta is not None:
            note += f", Δ(7-14d vs 14-21d)={prior_delta:+.3f}"
        if direction == MomentumDirection.PIVOT:
            note += " — activity direction reversed across trailing windows."

        return MomentumVector(
            direction=direction, arrow=cls.arrow(direction),
            velocity=round(latest_delta * 100, 2),  # rescaled to score-like units
            prior_velocity=round(prior_delta * 100, 2) if prior_delta is not None else None,
            accelerating=accelerating, basis="signal_frequency", note=note,
        )

    @classmethod
    def for_profile(cls, profile: FounderProfile) -> MomentumVector:
        if len(profile.score_history) >= 2:
            return cls.from_score_history(profile.score_history)
        return cls.from_signals(profile.historical_signals)

    # --- Backward-compatible shim for callers still using the old API ---
    @classmethod
    def direction(cls, score_history: List[Dict[str, Any]], flat_epsilon: float = 1.5) -> MomentumDirection:
        return cls.from_score_history(score_history, flat_epsilon).direction
