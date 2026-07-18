"""
mock_data.py
------------
Cached fixtures for "Demo Mode". Every payload here mirrors the exact
schema that a live Tavily / GitHub / LLM call would return, so the
orchestrator in main.py can route to either source with zero branching
logic downstream. Nothing here is invented data presented as real-world
fact in the product UI -- it is explicitly labeled DEMO/simulated data
and is only ever served when demo_mode=True.
"""

from datetime import datetime, timedelta


def _iso(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).isoformat()


# ---------------------------------------------------------------------------
# MODE A: "Reverse Sourcing" historical simulation
# A fictionalized, clearly-labeled walkthrough of what an early, obscure
# developer-tooling signal might have looked like -- used purely to
# demonstrate the scoring pipeline. Not a factual claim about any real
# company's actual funding history.
# ---------------------------------------------------------------------------
HISTORICAL_SIMULATION = {
    "scenario_id": "sim-2023-devtools-001",
    "label": "[DEMO DATA — illustrative scenario, not a factual record]",
    "macro_landscape": {
        "period": "Q2 2023 (simulated)",
        "saturation_index": 0.87,
        "notes": (
            "Simulated index showing heavy saturation in generic "
            "generative-wrapper apps and thinning differentiation "
            "in the application layer."
        ),
        "sub_segments": [
            {"segment": "LLM wrapper apps", "saturation": 0.91, "trend": "bear"},
            {"segment": "Dev productivity / IDE tooling", "saturation": 0.22, "trend": "bull"},
            {"segment": "Context-window infra", "saturation": 0.18, "trend": "bull"},
        ],
    },
    "structural_gap": {
        "gap_id": "gap-ide-orchestration",
        "description": (
            "Simulated structural bottleneck: standard context windows "
            "collapsing under real repo size, local multi-file orchestration "
            "fragmented across ad-hoc scripts, no native IDE-level automation."
        ),
        "confidence": 0.82,
    },
    "discovery_vector": {
        "source": "hackathon",
        "alias": "anon-dev-0091",
        "payload": {
            "repo_name": "fast-context-ide (demo alias)",
            "commit_message": "prototype: multi-file diff planner w/ local context cache",
            "stars_at_discovery": 11,
            "commit_velocity_7d": 42,
            "hackathon_placement": "honorable mention",
        },
        "ingested_at": _iso(0),
    },
    "system_output": {
        "founder_score": 88.4,
        "gap_fit_match_pct": 98.0,
        "recommended_action": "DRAFT_OUTREACH",
        "outreach_draft": (
            "[DEMO] Auto-generated outreach referencing the specific "
            "commit velocity and gap-fit match — see agents.py "
            "OutreachAgent for live generation logic."
        ),
        "memo_ready": True,
        "check_size_usd": 100_000,
        "decision_window_hours": 24,
    },
}


# ---------------------------------------------------------------------------
# MODE B: Live hackathon network ingestion (cached fallback)
# ---------------------------------------------------------------------------
HACKATHON_TOOLKIT_TELEMETRY = {
    "emdash": [
        {
            "project": "parallel-agent-runner",
            "dev_alias": "@kai_ships",
            "parallel_loops": 6,
            "avg_loop_latency_ms": 340,
            "success_rate": 0.91,
        },
        {
            "project": "swarm-eval-harness",
            "dev_alias": "@nadia.codes",
            "parallel_loops": 3,
            "avg_loop_latency_ms": 510,
            "success_rate": 0.78,
        },
    ],
    "lovable": [
        {
            "project": "instant-crm-builder",
            "dev_alias": "@marcusdev",
            "features_shipped_24h": 14,
            "regression_rate": 0.06,
        }
    ],
    "woz_perf_logs": [
        {
            "tool": "claude_code",
            "dev_alias": "@kai_ships",
            "median_task_completion_s": 92,
            "tool_call_success_rate": 0.94,
        },
        {
            "tool": "cursor",
            "dev_alias": "@nadia.codes",
            "median_task_completion_s": 121,
            "tool_call_success_rate": 0.88,
        },
    ],
}

LIVE_HACKATHON_PROFILES = [
    {
        "founder_id": "hack-001",
        "name": "Kai (demo alias)",
        "public_footprints": {"github": "https://github.com/example-kai"},
        "project": "parallel-agent-runner",
        "raw_signals": {
            "commits_7d": 63,
            "stars_7d": 24,
            "hackathon_award_tier": "finalist",
        },
    },
    {
        "founder_id": "hack-002",
        "name": "Nadia (demo alias)",
        "public_footprints": {"github": "https://github.com/example-nadia"},
        "project": "swarm-eval-harness",
        "raw_signals": {
            "commits_7d": 38,
            "stars_7d": 9,
            "hackathon_award_tier": "honorable mention",
        },
    },
    {
        "founder_id": "hack-003",
        "name": "Marcus (demo alias)",
        "public_footprints": {"github": "https://github.com/example-marcus"},
        "project": "instant-crm-builder",
        "raw_signals": {
            "commits_7d": 21,
            "stars_7d": 4,
            "hackathon_award_tier": "none",
        },
    },
]


# ---------------------------------------------------------------------------
# Cached Tavily-shaped responses for the Validator Agent demo path
# ---------------------------------------------------------------------------
TAVILY_CACHED_VERIFICATIONS = {
    "fast-context-ide (demo alias)": {
        "claim": "5k GitHub stars inside 14 days",
        "query": "site:github.com fast-context-ide stargazers",
        "results_summary": (
            "[DEMO] Cached stargazer timeline shows ~1.1k stars in the "
            "first 14 days, not 5k — flagged as a discrepancy."
        ),
        "extracted_value": 1100,
        "claimed_value": 5000,
        "discrepancy_pct": round((5000 - 1100) / 5000 * 100, 1),
        "verified": False,
    }
}


def get_mock_payload(kind: str):
    """Single lookup surface so main.py never branches on data shape."""
    registry = {
        "historical_simulation": HISTORICAL_SIMULATION,
        "hackathon_toolkit_telemetry": HACKATHON_TOOLKIT_TELEMETRY,
        "live_hackathon_profiles": LIVE_HACKATHON_PROFILES,
        "tavily_verifications": TAVILY_CACHED_VERIFICATIONS,
    }
    if kind not in registry:
        raise KeyError(f"No mock payload registered for '{kind}'")
    return registry[kind]
