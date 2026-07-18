"""
mock_data.py
------------
Cached fixtures for "Demo Mode". Every payload here mirrors the exact
schema that a live Tavily / GitHub / LLM call would return, so the
orchestrator in main.py can route to either source with zero branching
logic downstream. Nothing here is invented data presented as real-world
fact in the product UI -- it is explicitly labeled DEMO/simulated data
and is only ever served when demo_mode=True.

IMPORTANT re: the Sourcing Network Graph below -- the NODES and EDGES in
SOURCING_NETWORK_NODES / SOURCING_NETWORK_EDGES are a labeled, fictionalized
demo topology (who-talked-to-whom at a simulated hackathon). They are the
only "invented" part. Every centrality score, articulation point, and
Dead-Man-Switch number the product displays for that topology is computed
for real by backend/network_analysis.py -- this file never hardcodes a
centrality or fragmentation number.
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
        "sector": "dev tools",
        "raw_signals": {
            "commits_7d": 63,
            "stars_7d": 24,
            "hackathon_award_tier": "finalist",
        },
        "pipeline_stage": "diligence",
    },
    {
        "founder_id": "hack-002",
        "name": "Nadia (demo alias)",
        "public_footprints": {"github": "https://github.com/example-nadia"},
        "project": "swarm-eval-harness",
        "sector": "agentic systems",
        "raw_signals": {
            "commits_7d": 38,
            "stars_7d": 9,
            "hackathon_award_tier": "honorable mention",
        },
        "pipeline_stage": "screened",
    },
    {
        "founder_id": "hack-003",
        "name": "Marcus (demo alias)",
        "public_footprints": {"github": "https://github.com/example-marcus"},
        "project": "instant-crm-builder",
        "sector": "dev tools",
        "raw_signals": {
            "commits_7d": 21,
            "stars_7d": 4,
            "hackathon_award_tier": "none",
        },
        "pipeline_stage": "screened",
    },
    {
        "founder_id": "hack-004",
        "name": "Priya (demo alias)",
        "public_footprints": {"github": "https://github.com/example-priya"},
        "project": "ctx-cache-runtime",
        "sector": "infra",
        "raw_signals": {
            "commits_7d": 51,
            "stars_7d": 31,
            "hackathon_award_tier": "finalist",
        },
        "pipeline_stage": "approved",
    },
    {
        "founder_id": "hack-005",
        "name": "Owen (demo alias)",
        "public_footprints": {"github": "https://github.com/example-owen"},
        "project": "repo-graph-indexer",
        "sector": "infra",
        "raw_signals": {
            "commits_7d": 17,
            "stars_7d": 3,
            "hackathon_award_tier": "none",
        },
        "pipeline_stage": "sourced",
    },
    {
        "founder_id": "hack-006",
        "name": "Théo (demo alias)",
        "public_footprints": {"github": "https://github.com/example-theo"},
        "project": "agent-eval-bench",
        "sector": "agentic systems",
        "raw_signals": {
            "commits_7d": 44,
            "stars_7d": 18,
            "hackathon_award_tier": "honorable mention",
        },
        "pipeline_stage": "diligence",
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


# ---------------------------------------------------------------------------
# Sourcing Network Graph -- labeled DEMO topology only.
# All centrality / fragmentation / DMS math is computed live by
# network_analysis.SourcingNetworkEngine from this raw node/edge list --
# nothing quantitative below is hand-authored.
#
# Topology sketch (18 nodes): a hackathon collaboration graph with two
# developer "hubs" bridging otherwise separate project clusters, so the
# demo has a genuine structural story to tell (real cut-vertices emerge
# from this shape, they are not asserted).
# ---------------------------------------------------------------------------
SOURCING_NETWORK_NODES = [
    {"id": "dev-kai", "label": "@kai_ships", "node_type": "developer",
     "sub_label": "parallel-agent-runner", "meta": {"hackathon_tier": "finalist"}},
    {"id": "dev-nadia", "label": "@nadia.codes", "node_type": "developer",
     "sub_label": "swarm-eval-harness", "meta": {"hackathon_tier": "honorable mention"}},
    {"id": "dev-marcus", "label": "@marcusdev", "node_type": "developer",
     "sub_label": "instant-crm-builder", "meta": {"hackathon_tier": "none"}},
    {"id": "dev-priya", "label": "@priya.dev", "node_type": "developer",
     "sub_label": "ctx-cache-runtime", "meta": {"hackathon_tier": "finalist"}},
    {"id": "dev-owen", "label": "@owen_builds", "node_type": "developer",
     "sub_label": "repo-graph-indexer", "meta": {"hackathon_tier": "none"}},
    {"id": "dev-theo", "label": "@theo.codes", "node_type": "developer",
     "sub_label": "agent-eval-bench", "meta": {"hackathon_tier": "honorable mention"}},
    {"id": "dev-lin", "label": "@lin_ml", "node_type": "developer",
     "sub_label": "context-router", "meta": {"hackathon_tier": "none"}},
    {"id": "dev-sam", "label": "@sam_writes_go", "node_type": "developer",
     "sub_label": "diff-planner-core", "meta": {"hackathon_tier": "none"}},
    {"id": "dev-anysphere", "label": "@anysphere_mentor", "node_type": "developer",
     "sub_label": "cross-team mentor / judge", "meta": {"hackathon_tier": "mentor"}},
    {"id": "repo-parallel-agent-runner", "label": "parallel-agent-runner", "node_type": "repo",
     "sub_label": "emdash toolkit", "meta": {"stars": 24}},
    {"id": "repo-swarm-eval-harness", "label": "swarm-eval-harness", "node_type": "repo",
     "sub_label": "emdash toolkit", "meta": {"stars": 9}},
    {"id": "repo-instant-crm-builder", "label": "instant-crm-builder", "node_type": "repo",
     "sub_label": "lovable toolkit", "meta": {"stars": 4}},
    {"id": "repo-ctx-cache-runtime", "label": "ctx-cache-runtime", "node_type": "repo",
     "sub_label": "infra", "meta": {"stars": 31}},
    {"id": "repo-repo-graph-indexer", "label": "repo-graph-indexer", "node_type": "repo",
     "sub_label": "infra", "meta": {"stars": 3}},
    {"id": "repo-agent-eval-bench", "label": "agent-eval-bench", "node_type": "repo",
     "sub_label": "agentic systems", "meta": {"stars": 18}},
    {"id": "repo-context-router", "label": "context-router", "node_type": "repo",
     "sub_label": "infra", "meta": {"stars": 6}},
    {"id": "repo-diff-planner-core", "label": "diff-planner-core", "node_type": "repo",
     "sub_label": "dev tools", "meta": {"stars": 11}},
    {"id": "hackathon-main", "label": "Hackathon: AgentWeek SF", "node_type": "hackathon",
     "sub_label": "2026-06 cohort", "meta": {"participants": 210}},
]

SOURCING_NETWORK_EDGES = [
    # Cluster 1: emdash / parallel-agent tooling
    {"source": "dev-kai", "target": "repo-parallel-agent-runner", "weight": 1.0, "edge_type": "contribution"},
    {"source": "dev-nadia", "target": "repo-swarm-eval-harness", "weight": 1.0, "edge_type": "contribution"},
    {"source": "dev-kai", "target": "dev-nadia", "weight": 0.8, "edge_type": "collaboration"},
    {"source": "dev-nadia", "target": "repo-parallel-agent-runner", "weight": 0.4, "edge_type": "collaboration"},

    # Cluster 2: lovable / CRM builder (deliberately thin -- only Marcus)
    {"source": "dev-marcus", "target": "repo-instant-crm-builder", "weight": 1.0, "edge_type": "contribution"},

    # Cluster 3: infra (ctx-cache-runtime + repo-graph-indexer + context-router)
    {"source": "dev-priya", "target": "repo-ctx-cache-runtime", "weight": 1.0, "edge_type": "contribution"},
    {"source": "dev-owen", "target": "repo-repo-graph-indexer", "weight": 1.0, "edge_type": "contribution"},
    {"source": "dev-lin", "target": "repo-context-router", "weight": 1.0, "edge_type": "contribution"},
    {"source": "dev-priya", "target": "dev-owen", "weight": 0.6, "edge_type": "collaboration"},
    {"source": "dev-owen", "target": "dev-lin", "weight": 0.5, "edge_type": "collaboration"},

    # Cluster 4: agentic systems eval bench + diff planner
    {"source": "dev-theo", "target": "repo-agent-eval-bench", "weight": 1.0, "edge_type": "contribution"},
    {"source": "dev-sam", "target": "repo-diff-planner-core", "weight": 1.0, "edge_type": "contribution"},
    {"source": "dev-theo", "target": "dev-sam", "weight": 0.5, "edge_type": "collaboration"},

    # Bridges -- the mentor and Kai are the only paths between clusters.
    # This is what makes them structurally load-bearing (a real, emergent
    # cut-vertex property of this topology, not an assertion).
    {"source": "dev-anysphere", "target": "dev-kai", "weight": 0.7, "edge_type": "mentorship"},
    {"source": "dev-anysphere", "target": "dev-priya", "weight": 0.7, "edge_type": "mentorship"},
    {"source": "dev-anysphere", "target": "dev-theo", "weight": 0.6, "edge_type": "mentorship"},
    {"source": "dev-anysphere", "target": "dev-marcus", "weight": 0.4, "edge_type": "mentorship"},
    {"source": "dev-kai", "target": "hackathon-main", "weight": 0.3, "edge_type": "collaboration"},
    {"source": "dev-priya", "target": "hackathon-main", "weight": 0.3, "edge_type": "collaboration"},
    {"source": "dev-theo", "target": "hackathon-main", "weight": 0.3, "edge_type": "collaboration"},
    {"source": "dev-marcus", "target": "hackathon-main", "weight": 0.3, "edge_type": "collaboration"},
    {"source": "dev-owen", "target": "hackathon-main", "weight": 0.2, "edge_type": "collaboration"},
]


# ---------------------------------------------------------------------------
# Pipeline funnel -- stage counts are aggregated (in main.py) from
# LIVE_HACKATHON_PROFILES' pipeline_stage field rather than hand-typed
# totals, so the funnel numbers always agree with the underlying rows.
# ---------------------------------------------------------------------------
PIPELINE_STAGE_ORDER = ["sourced", "screened", "diligence", "approved"]


def get_mock_payload(kind: str):
    """Single lookup surface so main.py never branches on data shape."""
    registry = {
        "historical_simulation": HISTORICAL_SIMULATION,
        "hackathon_toolkit_telemetry": HACKATHON_TOOLKIT_TELEMETRY,
        "live_hackathon_profiles": LIVE_HACKATHON_PROFILES,
        "tavily_verifications": TAVILY_CACHED_VERIFICATIONS,
        "sourcing_network_nodes": SOURCING_NETWORK_NODES,
        "sourcing_network_edges": SOURCING_NETWORK_EDGES,
    }
    if kind not in registry:
        raise KeyError(f"No mock payload registered for '{kind}'")
    return registry[kind]
