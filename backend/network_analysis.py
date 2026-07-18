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
            avg_clustering_coefficient=round(nx.average_clustering(graph), 4),
            articulation_point_count=len(articulation_points),
        )

        return SourcingNetworkResult(
            nodes=nodes_out,
            edges=edges,
            structural_risks=risks,
            stats=stats,
        )
