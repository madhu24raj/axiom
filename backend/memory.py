"""
memory.py
---------
The Memory layer (per the brief: "Nothing discarded... Houses the Founder
Score -- persists across applications, never resets").

This is deliberately separate from the per-opportunity 3-axis screen in
agents.py. The brief's FAQ #6 is explicit that these are NOT the same thing:
the Founder Score lives here, follows a person across different companies
over time, and is one INPUT into the Founder axis -- not a substitute for it.

A production system would back this with a real database and verified
identity (OAuth/email); kept in-process here for the same zero-setup
reason as ModeState/LiveSessionState in main.py, with that limitation
stated plainly rather than hidden.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from scoring import FounderProfile, SignalMetric, FounderScoreEngine


def normalize_identity(name: str, github_url: Optional[str] = None) -> str:
    """Best-effort stable key for 'the same human' across applications.
    Prefers a GitHub handle (harder to collide) over a normalized name."""
    if github_url:
        handle = github_url.rstrip("/").split("/")[-1].lower()
        if handle:
            return f"github:{handle}"
    return f"name:{re.sub(r'[^a-z0-9]', '', name.lower())}"


def _signal_fingerprint(sig: SignalMetric) -> str:
    """Two signals are treated as duplicates if they share a source and land
    on the same UTC day with the same rounded strength -- an explicit,
    auditable dedup rule rather than a fuzzy embedding-similarity one."""
    day = sig.timestamp.strftime("%Y-%m-%d")
    return f"{sig.source.value}:{day}:{round(sig.normalized_score, 2)}"


@dataclass
class FounderMemoryRecord:
    identity_key: str
    display_name: str
    profile: FounderProfile
    applications: List[str] = field(default_factory=list)  # opportunity_ids over time
    # Per-axis score history ("founder" / "market" / "idea_vs_market") --
    # what powers the brief's "each axis also shows trend" requirement.
    # Change-only appends (see record_axis_scores) so repeated identical
    # evaluations don't manufacture a fake time series.
    axis_history: Dict[str, List[float]] = field(default_factory=dict)
    first_seen_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class FounderMemoryStore:
    TREND_EPSILON = 1.5

    def __init__(self):
        self._records: Dict[str, FounderMemoryRecord] = {}
        self._score_engine = FounderScoreEngine()

    def get(self, identity_key: str) -> Optional[FounderMemoryRecord]:
        return self._records.get(identity_key)

    def _ensure_record(self, identity_key: str, display_name: str) -> FounderMemoryRecord:
        record = self._records.get(identity_key)
        if record is None:
            profile = FounderProfile(founder_id=identity_key, name=display_name)
            record = FounderMemoryRecord(identity_key=identity_key, display_name=display_name, profile=profile)
            self._records[identity_key] = record
        return record

    def record_axis_scores(
        self, identity_key: str, display_name: str, scores: Dict[str, Optional[float]]
    ) -> Dict[str, str]:
        """Appends each axis's new score ONLY when it actually changed, then
        classifies the trend from the last two distinct observations:
        improving / declining / stable. A single observation is 'stable' --
        no trend is asserted from one data point."""
        record = self._ensure_record(identity_key, display_name)
        trends: Dict[str, str] = {}
        for axis, score in scores.items():
            if score is None:
                trends[axis] = "stable"
                continue
            history = record.axis_history.setdefault(axis, [])
            if not history or abs(history[-1] - score) > 0.01:
                history.append(score)
            if len(history) < 2:
                trends[axis] = "stable"
            else:
                delta = history[-1] - history[-2]
                trends[axis] = (
                    "improving" if delta > self.TREND_EPSILON
                    else "declining" if delta < -self.TREND_EPSILON
                    else "stable"
                )
        return trends

    def upsert(
        self,
        identity_key: str,
        display_name: str,
        new_signals: List[SignalMetric],
        opportunity_id: str,
    ) -> FounderMemoryRecord:
        record = self._ensure_record(identity_key, display_name)

        existing_fingerprints = {_signal_fingerprint(s) for s in record.profile.historical_signals}
        for sig in new_signals:
            fp = _signal_fingerprint(sig)
            if fp not in existing_fingerprints:
                record.profile.historical_signals.append(sig)
                existing_fingerprints.add(fp)

        if opportunity_id not in record.applications:
            record.applications.append(opportunity_id)
        return record

    def record_displayed_score(self, identity_key: str, score: float) -> None:
        """Called once the real, DISPLAYED Founder axis score is known --
        which for a cold-start founder is the blended cold-start read, not
        the (still-zero) multi-source formula output. score_history has to
        track whatever was actually shown, or momentum ends up measuring an
        internal number nobody sees instead of the founder's real trend."""
        record = self._records.get(identity_key)
        if record is None:
            return
        record.profile.score_history.append({
            "timestamp": datetime.utcnow().isoformat(), "score": score,
        })
        record.profile.current_founder_score = score
        record.profile.last_updated = datetime.utcnow()

    def all_records(self) -> List[FounderMemoryRecord]:
        return list(self._records.values())


memory_store = FounderMemoryStore()
