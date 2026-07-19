"""
network_analysis.py
--------------------
Graph-theoretic engine for Axiom OS's "Reverse Sourcing" network view.

This module owns ALL of the math behind the Sourcing Network Graph and the
"Structural Risk" panel. It is intentionally separated from mock_data.py:

    mock_data.py         -> raw, labeled DEMO topology (who talked to whom)
    network_analysis.py  -> real graph algorithms run ON TOP of that topology

Nothing in this file invents a centrality score, a fragmentation percentage,
or a risk tier. Every number is the direct output of a graph algorithm
(NetworkX) applied to whatever node/edge list it is given -- swap the demo
topology for a live-ingested one and the exact same math runs unchanged.

Concepts implemented:

1. Eigenvector Centrality  -- "how connected are your connections" -- surfaces
   nodes central because they're linked to other well-connected nodes (e.g.
   a dev who collaborates with other high-signal devs), not just high-degree
   nodes.
2. Betweenness Centrality   -- how often a node sits on the shortest path
   between two other nodes -- surfaces brokers/bridges whose removal would
   force information (or deal flow) to reroute.
3. Articulation Points      -- classic graph-theory "cut vertices": nodes
   whose removal literally increases the number of connected components.
   Every articulation point is, by definition, a single point of failure.
4. Dead-Man-Switch (DMS) Score -- a composite fragility score in [0, 100]
   we define as:

       DMS = 100 * ( 0.5 * betweenness_norm
                    + 0.3 * eigenvector_norm
                    + 0.2 * fragmentation_if_removed )

   where fragmentation_if_removed is measured by actually deleting the node
   from a copy of the graph and computing:

       fragmentation = 1 - ( largest_component_size_after / n_nodes_before )

   i.e. "what fraction of the network's reachable mass falls out of the
   giant component if this node disappears tonight." This is a real
   simulation (networkx connected_components before/after node removal),
   not a lookup table.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
from pydantic import BaseModel, Field

logger = logging.getLogger("vc_brain.network_analysis")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class NetworkNodeIn(BaseModel):
    """Raw node as supplied by mock_data.py (or, in Live mode, an ingestion
    adapter). Purely descriptive -- carries no computed math."""

    id: str
    label: str
    node_type: str  # "developer" | "repo" | "hackathon"
    sub_label: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class NetworkEdgeIn(BaseModel):
    source: str
    target: str
    weight: float = 1.0
    edge_type: str = "collaboration"  # "collaboration" | "contribution" | "mentorship"


class NetworkNodeOut(NetworkNodeIn):
    """Node enriched with computed graph metrics. Every field below is a
    direct algorithm output -- see module docstring."""

    degree: int
    eigenvector_centrality: float
    betweenness_centrality: float
    is_articulation_point: bool
    fragmentation_pct_if_removed: float
    dms_score: float
    risk_tier: str  # "critical" | "elevated" | "nominal"


class StructuralRisk(BaseModel):
    """A single row in the 'Structural Risks' side panel -- always sorted
    by DMS score, descending."""

    node_id: str
    label: str
    node_type: str
    eigenvector_centrality: float
    betweenness_centrality: float
    is_articulation_point: bool
    fragmentation_pct_if_removed: float
    dms_score: float
    risk_tier: str
    narrative: str


class NetworkStats(BaseModel):
    num_nodes: int
    num_edges: int
    density: float
    num_connected_components: int
    largest_component_size: int
    avg_clustering_coefficient: float
    articulation_point_count: int


class SourcingNetworkResult(BaseModel):
    nodes: List[NetworkNodeOut]
    edges: List[NetworkEdgeIn]
    structural_risks: List[StructuralRisk]
    stats: NetworkStats
    label: str = "[DEMO DATA — illustrative topology, real graph math]"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class SourcingNetworkEngine:
    """Stateless -- call `.run(nodes, edges)` with any topology. main.py owns
    whether that topology came from mock_data.py or a live ingestion feed."""

    RISK_CRITICAL = 66.0
    RISK_ELEVATED = 33.0

    def _tier(self, dms_score: float) -> str:
        if dms_score >= self.RISK_CRITICAL:
            return "critical"
        if dms_score >= self.RISK_ELEVATED:
            return "elevated"
        return "nominal"

    @staticmethod
    def _normalize(values: Dict[str, float]) -> Dict[str, float]:
        if not values:
            return {}
        max_v = max(values.values())
        if max_v <= 0:
            return {k: 0.0 for k in values}
        return {k: v / max_v for k, v in values.items()}

    def _fragmentation_if_removed(self, graph: nx.Graph, node_id: str, n_before: int) -> float:
        """Actually remove the node from a scratch copy and measure how much
        of the network's mass falls out of the giant component."""
        if n_before <= 1:
            return 0.0
        working = graph.copy()
        working.remove_node(node_id)
        if working.number_of_nodes() == 0:
            return 1.0
        components = list(nx.connected_components(working))
        largest_after = max((len(c) for c in components), default=0)
        # n_before - 1 because the removed node itself was part of "before"
        remaining_pool = max(n_before - 1, 1)
        fragmentation = 1.0 - (largest_after / remaining_pool)
        return round(max(0.0, min(1.0, fragmentation)), 4)

    def run(
        self, nodes: List[NetworkNodeIn], edges: List[NetworkEdgeIn]
    ) -> SourcingNetworkResult:
        if not nodes:
            # The null graph has no meaningful centrality/fragmentation math --
            # return a valid, honestly-empty result rather than raising or
            # (worse) fabricating placeholder nodes to avoid an empty screen.
            return SourcingNetworkResult(
                nodes=[],
                edges=[],
                structural_risks=[],
                stats=NetworkStats(
                    num_nodes=0, num_edges=0, density=0.0,
                    num_connected_components=0, largest_component_size=0,
                    avg_clustering_coefficient=0.0, articulation_point_count=0,
                ),
            )

        graph = nx.Graph()
        for n in nodes:
            graph.add_node(n.id, **n.model_dump())
        for e in edges:
            graph.add_edge(e.source, e.target, weight=e.weight, edge_type=e.edge_type)

        n_before = graph.number_of_nodes()

        # Eigenvector centrality can fail to converge on disconnected /
        # pathological graphs -- the numpy variant is a robust closed-form
        # fallback that still returns a real algorithmic result rather than
        # a fabricated placeholder.
        try:
            eig = nx.eigenvector_centrality(graph, max_iter=1000, weight="weight")
        except (nx.PowerIterationFailedConvergence, nx.AmbiguousSolution, nx.NetworkXError):
            eig = nx.eigenvector_centrality_numpy(graph, weight="weight")

        betw = nx.betweenness_centrality(graph, weight="weight", normalized=True)
        articulation_points = set(nx.articulation_points(graph)) if n_before > 2 else set()

        eig_norm = self._normalize(eig)
        betw_norm = self._normalize(betw)

        fragmentation: Dict[str, float] = {}
        dms: Dict[str, float] = {}
        for node_id in graph.nodes:
            frag = self._fragmentation_if_removed(graph, node_id, n_before)
            fragmentation[node_id] = frag
            score = 100.0 * (
                0.5 * betw_norm.get(node_id, 0.0)
                + 0.3 * eig_norm.get(node_id, 0.0)
                + 0.2 * frag
            )
            dms[node_id] = round(score, 2)

        nodes_out: List[NetworkNodeOut] = []
        for n in nodes:
            nodes_out.append(
                NetworkNodeOut(
                    **n.model_dump(),
                    degree=graph.degree[n.id],
                    eigenvector_centrality=round(eig.get(n.id, 0.0), 4),
                    betweenness_centrality=round(betw.get(n.id, 0.0), 4),
                    is_articulation_point=n.id in articulation_points,
                    fragmentation_pct_if_removed=fragmentation.get(n.id, 0.0),
                    dms_score=dms.get(n.id, 0.0),
                    risk_tier=self._tier(dms.get(n.id, 0.0)),
                )
            )

        risks: List[StructuralRisk] = []
        for n in nodes_out:
            if n.dms_score < self.RISK_ELEVATED and not n.is_articulation_point:
                continue  # only surface nodes that matter to the Overseer
            cut_note = (
                "a true cut-vertex — removing it splits the network into disconnected pieces"
                if n.is_articulation_point
                else "not a hard cut-vertex, but high-leverage in shortest paths across the graph"
            )
            risks.append(
                StructuralRisk(
                    node_id=n.id,
                    label=n.label,
                    node_type=n.node_type,
                    eigenvector_centrality=n.eigenvector_centrality,
                    betweenness_centrality=n.betweenness_centrality,
                    is_articulation_point=n.is_articulation_point,
                    fragmentation_pct_if_removed=n.fragmentation_pct_if_removed,
                    dms_score=n.dms_score,
                    risk_tier=n.risk_tier,
                    narrative=(
                        f"If {n.label} leaves the network, the graph fragments by "
                        f"{n.fragmentation_pct_if_removed * 100:.1f}% ({cut_note})."
                    ),
                )
            )
        risks.sort(key=lambda r: r.dms_score, reverse=True)

        components = list(nx.connected_components(graph))
        stats = NetworkStats(
            num_nodes=graph.number_of_nodes(),
            num_edges=graph.number_of_edges(),
            density=round(nx.density(graph), 4),
            num_connected_components=len(components),
            largest_component_size=max((len(c) for c in components), default=0),
            avg_clustering_coefficient=(
                round(nx.average_clustering(graph), 4) if graph.number_of_nodes() > 0 else 0.0
            ),
            articulation_point_count=len(articulation_points),
        )

        return SourcingNetworkResult(
            nodes=nodes_out,
            edges=edges,
            structural_risks=risks,
            stats=stats,
        )


# ===========================================================================
# LIVE GRAPH GROWTH LAYER
# ---------------------------------------------------------------------------
# Two additions that make Live mode's graph real instead of empty:
#
#   1. infer_edges_for_new_node(...) -- deterministic, evidence-based edge
#      inference for nodes added by session searches. Fixes the bug where
#      live_state.graph_edges was declared but never written: nodes were
#      registered, edges never were, so eigenvector/betweenness/DMS were
#      computed over an edgeless graph (all zeros).
#
#   2. GitHubGraphSeeder -- seeds Live mode with REAL public GitHub data:
#      configured org/user handles -> their top public repos (by stars) ->
#      those repos' top public contributors. Every node and edge is a direct
#      readout of the GitHub REST API (with source URLs + fetched_at stamped
#      into node.meta), never invented. If GitHub is unreachable (rate limit,
#      no network), the seeder raises SeederUnavailable and main.py falls
#      back to the clearly-labeled demo topology -- honest fallback, never a
#      silently fabricated "live" graph.
# ===========================================================================

import math
import os
import re as _re
from datetime import datetime, timezone

import httpx


# ---------------------------------------------------------------------------
# 1) Session edge inference
# ---------------------------------------------------------------------------
def _edge_key(e: NetworkEdgeIn) -> Tuple[str, str]:
    return (min(e.source, e.target), max(e.source, e.target))


def _domains_from_urls(urls: List[str]) -> set:
    out = set()
    for u in urls or []:
        m = _re.match(r"https?://(?:www\.)?([^/]+)", str(u))
        if m:
            out.add(m.group(1).lower())
    return out


def infer_edges_for_new_node(
    new_node: NetworkNodeIn,
    existing_nodes: List[NetworkNodeIn],
    existing_edges: List[NetworkEdgeIn],
) -> List[NetworkEdgeIn]:
    """Deterministic edges between a freshly-searched node and the graph.

    Every edge corresponds to a stated, checkable relationship in node meta --
    no similarity model, no randomness, no invented links:

      * shared evidence domain  (both nodes cite a source on the same domain)
        -> weight 2.0, edge_type "shared_evidence"
      * same sector             (identical, known sector strings)
        -> weight 1.0, edge_type "collaboration"
      * github handle linkage   (searched node's github login appears among a
        seeded repo's contributors, or matches a seeded developer node)
        -> weight 3.0, edge_type "contribution"

    If nothing matches, the node legitimately stays an isolate -- the engine
    handles disconnected graphs, and an honest isolate beats a fake edge.
    """
    seen = {_edge_key(e) for e in existing_edges}
    out: List[NetworkEdgeIn] = []

    def _add(target_id: str, weight: float, edge_type: str):
        e = NetworkEdgeIn(source=new_node.id, target=target_id, weight=weight, edge_type=edge_type)
        k = _edge_key(e)
        if k not in seen and new_node.id != target_id:
            seen.add(k)
            out.append(e)

    new_domains = _domains_from_urls(new_node.meta.get("source_urls", []))
    new_sector = (new_node.meta.get("sector") or "").strip().lower()
    new_login = (new_node.meta.get("github_login") or "").strip().lower()

    for other in existing_nodes:
        if other.id == new_node.id:
            continue
        o_meta = other.meta or {}

        if new_login:
            if (o_meta.get("github_login") or "").strip().lower() == new_login:
                _add(other.id, 3.0, "contribution")
                continue
            contributors = {str(c).lower() for c in o_meta.get("contributor_logins", [])}
            if new_login in contributors:
                _add(other.id, 3.0, "contribution")
                continue

        shared = new_domains & _domains_from_urls(o_meta.get("source_urls", []))
        if shared:
            _add(other.id, 2.0, "shared_evidence")
            continue

        o_sector = (o_meta.get("sector") or "").strip().lower()
        if new_sector and o_sector and new_sector == o_sector and new_sector != "unknown":
            _add(other.id, 1.0, "collaboration")

    return out


# ---------------------------------------------------------------------------
# 2) GitHub public-API seeder
# ---------------------------------------------------------------------------
class SeederUnavailable(RuntimeError):
    """GitHub could not be reached / rate-limited. Callers must fall back to
    an honest labeled alternative, never to fabricated 'live' data."""


DEFAULT_SEED_HANDLES = ["getcursor", "anysphere"]  # Cursor's public GitHub orgs


class GitHubGraphSeeder:
    """Builds a (nodes, edges) topology from the GitHub REST API.

    Request budget per seed run (defaults): 1/handle profile + 1/org repo
    list + 1/repo contributor list ~= 8 requests total -- comfortably inside
    even the unauthenticated 60 req/hr limit. Set GITHUB_TOKEN for 5000/hr.
    """

    API = "https://api.github.com"

    def __init__(
        self,
        handles: Optional[List[str]] = None,
        top_repos_per_org: int = 2,
        top_contributors_per_repo: int = 6,
    ):
        env_handles = os.environ.get("SEED_GITHUB_HANDLES", "")
        self.handles = handles or (
            [h.strip() for h in env_handles.split(",") if h.strip()] or DEFAULT_SEED_HANDLES
        )
        self.top_repos_per_org = top_repos_per_org
        self.top_contributors_per_repo = top_contributors_per_repo
        token = os.environ.get("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "vc-brain-hackathon-prototype",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    async def _get(self, client: httpx.AsyncClient, path: str) -> Any:
        resp = await client.get(f"{self.API}{path}", headers=self.headers)
        if resp.status_code in (403, 429):
            raise SeederUnavailable(
                f"GitHub rate limit hit on {path} "
                "(set GITHUB_TOKEN to raise the limit to 5000 req/hr)"
            )
        if resp.status_code == 404:
            return None  # handle/repo doesn't exist -- skip, don't fail the run
        resp.raise_for_status()
        return resp.json()

    async def seed(self) -> Tuple[List[NetworkNodeIn], List[NetworkEdgeIn], Dict[str, Any]]:
        """Returns (nodes, edges, seed_meta). Raises SeederUnavailable if the
        API is unreachable. Skips (with a log line) any configured handle
        that doesn't exist -- it will never invent a profile for it."""
        fetched_at = datetime.now(timezone.utc).isoformat()
        nodes: Dict[str, NetworkNodeIn] = {}
        edges: List[NetworkEdgeIn] = []
        edge_seen: set = set()
        skipped: List[str] = []

        def _add_edge(src: str, dst: str, weight: float, edge_type: str):
            e = NetworkEdgeIn(source=src, target=dst, weight=weight, edge_type=edge_type)
            k = _edge_key(e)
            if k not in edge_seen and src != dst:
                edge_seen.add(k)
                edges.append(e)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for handle in self.handles:
                    profile = await self._get(client, f"/users/{handle}")
                    if profile is None:
                        skipped.append(handle)
                        logger.warning("Seed handle %r not found on GitHub -- skipped.", handle)
                        continue

                    is_org = profile.get("type") == "Organization"
                    org_id = f"gh-{profile['login'].lower()}"
                    nodes[org_id] = NetworkNodeIn(
                        id=org_id,
                        label=profile.get("name") or profile["login"],
                        node_type="hackathon" if is_org else "developer",
                        sub_label="GitHub org" if is_org else "GitHub user",
                        meta={
                            "github_login": profile["login"],
                            "followers": profile.get("followers"),
                            "public_repos": profile.get("public_repos"),
                            "source_urls": [profile.get("html_url")],
                            "data_provenance": "github_public_api",
                            "fetched_at": fetched_at,
                        },
                    )

                    repos_path = f"/orgs/{handle}/repos?per_page=30" if is_org \
                        else f"/users/{handle}/repos?per_page=30"
                    repos = await self._get(client, repos_path) or []
                    if not repos and is_org:
                        # Some orgs list repos only via the /users endpoint
                        repos = await self._get(client, f"/users/{handle}/repos?per_page=30") or []
                    repos = sorted(repos, key=lambda r: r.get("stargazers_count", 0), reverse=True)
                    for repo in repos[: self.top_repos_per_org]:
                        repo_id = f"gh-repo-{repo['full_name'].lower().replace('/', '-')}"
                        contributors = await self._get(
                            client,
                            f"/repos/{repo['full_name']}/contributors"
                            f"?per_page={self.top_contributors_per_repo}",
                        ) or []
                        contributor_logins = [
                            c["login"] for c in contributors if c.get("type") == "User"
                        ]
                        nodes[repo_id] = NetworkNodeIn(
                            id=repo_id,
                            label=repo["name"],
                            node_type="repo",
                            sub_label=f"★ {repo.get('stargazers_count', 0):,}",
                            meta={
                                "full_name": repo["full_name"],
                                "stars": repo.get("stargazers_count"),
                                "forks": repo.get("forks_count"),
                                "language": repo.get("language"),
                                "contributor_logins": contributor_logins,
                                "source_urls": [repo.get("html_url")],
                                "data_provenance": "github_public_api",
                                "fetched_at": fetched_at,
                            },
                        )
                        _add_edge(org_id, repo_id, 2.0, "collaboration")

                        for c in contributors:
                            if c.get("type") != "User":
                                continue  # skip bots
                            dev_id = f"gh-{c['login'].lower()}"
                            if dev_id not in nodes:
                                nodes[dev_id] = NetworkNodeIn(
                                    id=dev_id,
                                    label=c["login"],
                                    node_type="developer",
                                    sub_label=f"{c.get('contributions', 0):,} commits",
                                    meta={
                                        "github_login": c["login"],
                                        "contributions": c.get("contributions"),
                                        "source_urls": [c.get("html_url")],
                                        "data_provenance": "github_public_api",
                                        "fetched_at": fetched_at,
                                    },
                                )
                            # log-scale weight so a 2,000-commit maintainer
                            # doesn't visually flatten everyone else
                            w = 1.0 + math.log10(1 + max(0, c.get("contributions", 0)))
                            _add_edge(dev_id, repo_id, round(w, 3), "contribution")
        except SeederUnavailable:
            raise
        except (httpx.HTTPError, OSError) as exc:
            raise SeederUnavailable(f"GitHub API unreachable: {exc}") from exc

        if not nodes:
            raise SeederUnavailable(
                f"None of the configured seed handles exist on GitHub: {self.handles}"
            )

        seed_meta = {
            "seeded_handles": [h for h in self.handles if h not in skipped],
            "skipped_handles": skipped,
            "fetched_at": fetched_at,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }
        return list(nodes.values()), edges, seed_meta
