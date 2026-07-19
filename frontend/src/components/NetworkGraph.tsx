"use client";

/**
 * NetworkGraph.tsx
 * ----------------
 * Renders the Sourcing Network Graph: hackathon developers + repos as nodes,
 * collaboration/contribution/mentorship as edges. Node positions are computed
 * client-side with d3-force (a real physics simulation, not a fixed layout);
 * every other visual property -- radius, ring color, pulse -- is driven
 * directly by fields network_analysis.py computed on the backend
 * (eigenvector centrality, betweenness centrality, articulation-point
 * status, DMS score). This file draws the math; it never invents it.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { ShieldAlert, Radio } from "lucide-react";
import type { NetworkEdge, NetworkNodeOut, SourcingNetworkResult, RiskTier } from "../lib/types";

type SimNode = NetworkNodeOut & SimulationNodeDatum;
type SimLink = SimulationLinkDatum<SimNode> & { weight: number; edge_type: string };

const WIDTH = 760;
const HEIGHT = 460;

const NODE_TYPE_COLOR: Record<string, string> = {
  developer: "var(--color-primary)",
  repo: "var(--color-muted)",
  hackathon: "var(--color-accent)",
};

const RISK_RING_COLOR: Record<RiskTier, string | null> = {
  critical: "var(--color-risk-critical)",
  elevated: "var(--color-risk-elevated)",
  nominal: null,
};

function radiusFor(node: NetworkNodeOut): number {
  const base = node.node_type === "hackathon" ? 14 : node.node_type === "developer" ? 9 : 7;
  return base + node.dms_score / 12; // structurally critical nodes read as visually larger
}

function edgeDash(edgeType: string): string | undefined {
  if (edgeType === "mentorship") return "2 3";
  if (edgeType === "shared_evidence") return "5 4";
  return undefined;
}

function RiskBadge({ tier }: { tier: RiskTier }) {
  const cls =
    tier === "critical"
      ? "bg-risk-critical/15 text-risk-critical border-risk-critical/30"
      : tier === "elevated"
      ? "bg-risk-elevated/15 text-risk-elevated border-risk-elevated/30"
      : "bg-risk-nominal/15 text-risk-nominal border-hair";
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider ${cls}`}>
      {tier}
    </span>
  );
}

export default function NetworkGraph({
  data,
  loading,
  error,
}: {
  data: SourcingNetworkResult | null;
  loading: boolean;
  error: string | null;
}) {
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [hovered, setHovered] = useState<string | null>(null);
  const [selectedRisk, setSelectedRisk] = useState<string | null>(null);
  const simRef = useRef<Simulation<SimNode, undefined> | null>(null);

  const nodesById = useMemo(() => {
    const map = new Map<string, NetworkNodeOut>();
    data?.nodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [data]);

  useEffect(() => {
    if (!data || data.nodes.length === 0) return;

    const simNodes: SimNode[] = data.nodes.map((n) => ({ ...n }));
    const simLinks: SimLink[] = data.edges.map((e) => ({ ...e, source: e.source, target: e.target }));

    const sim = forceSimulation<SimNode>(simNodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance((l) => 90 / Math.max(0.2, l.weight))
          .strength(0.6)
      )
      .force("charge", forceManyBody().strength(-260))
      .force("center", forceCenter(WIDTH / 2, HEIGHT / 2))
      .force(
        "collide",
        forceCollide<SimNode>().radius((d) => radiusFor(d) + 14)
      )
      .alphaDecay(0.02)
      .stop();

    simRef.current = sim;
    let frame: number;
    let ticks = 0;
    const maxTicks = 220;

    const step = () => {
      sim.tick();
      ticks += 1;
      const next: Record<string, { x: number; y: number }> = {};
      simNodes.forEach((n) => {
        next[n.id] = {
          x: Math.max(24, Math.min(WIDTH - 24, n.x ?? WIDTH / 2)),
          y: Math.max(24, Math.min(HEIGHT - 24, n.y ?? HEIGHT / 2)),
        };
      });
      setPositions(next);
      if (ticks < maxTicks && sim.alpha() > 0.01) {
        frame = requestAnimationFrame(step);
      }
    };
    frame = requestAnimationFrame(step);

    return () => {
      cancelAnimationFrame(frame);
      sim.stop();
    };
  }, [data]);

  if (loading) {
    return <div className="h-[460px] animate-pulse rounded-lg border border-hair bg-panel" />;
  }

  if (error || !data) {
    return (
      <div className="flex h-[460px] items-center justify-center rounded-lg border border-hair bg-panel font-mono text-xs text-dim">
        {error ?? "[Sourcing network: Not Disclosed]"}
      </div>
    );
  }

  const { stats, structural_risks } = data;

  if (stats.num_nodes === 0) {
    return (
      <div className="axiom-fade-in flex h-[220px] flex-col items-center justify-center gap-2 rounded-lg border border-hair bg-panel text-center">
        <span className="font-mono text-xs uppercase tracking-wider text-muted">{data.label}</span>
        <p className="max-w-sm font-sans text-xs text-dim">
          Search for a founder, GitHub handle, or startup above — the graph grows from real
          diligence activity instead of a canned roster.
        </p>
      </div>
    );
  }

  return (
    <div className="axiom-fade-in grid grid-cols-1 gap-3 lg:grid-cols-[1.6fr_1fr]">
      {/* Graph canvas */}
      <div className="rounded-lg border border-hair bg-panel p-3">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-mono text-xs uppercase tracking-wider text-muted">
            Reverse Sourcing — Collaboration Graph
          </h3>
          <div className="flex gap-3 font-mono text-[10px] text-dim">
            <span>{stats.num_nodes} nodes</span>
            <span>{stats.num_edges} edges</span>
            <span>density {stats.density.toFixed(3)}</span>
            <span>{stats.articulation_point_count} cut-vertices</span>
          </div>
        </div>
        <p className="mb-2 font-mono text-[10px] text-dim">{data.label}</p>
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" role="img" aria-label="Sourcing network graph">
          <g>
            {data.edges.map((e: NetworkEdge, i: number) => {
              const s = positions[e.source];
              const t = positions[e.target];
              if (!s || !t) return null;
              const highlighted = hovered === e.source || hovered === e.target;
              return (
                <line
                  key={i}
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  stroke={highlighted ? "var(--color-accent)" : "var(--color-hair-strong)"}
                  strokeWidth={highlighted ? 1.6 : Math.max(0.6, e.weight)}
                  strokeDasharray={edgeDash(e.edge_type)}
                  opacity={highlighted ? 0.9 : 0.55}
                />
              );
            })}
          </g>
          <g>
            {data.nodes.map((n) => {
              const p = positions[n.id];
              if (!p) return null;
              const r = radiusFor(n);
              const ringColor = RISK_RING_COLOR[n.risk_tier];
              return (
                <g
                  key={n.id}
                  transform={`translate(${p.x}, ${p.y})`}
                  onMouseEnter={() => setHovered(n.id)}
                  onMouseLeave={() => setHovered((h) => (h === n.id ? null : h))}
                  style={{ cursor: "pointer" }}
                >
                  {ringColor && (
                    <circle
                      r={r + 5}
                      fill="none"
                      stroke={ringColor}
                      strokeWidth={2}
                      className={n.risk_tier === "critical" ? "axiom-pulse" : undefined}
                      opacity={0.8}
                    />
                  )}
                  <circle
                    r={r}
                    fill={NODE_TYPE_COLOR[n.node_type] ?? "var(--color-muted)"}
                    opacity={n.node_type === "repo" ? 0.55 : 0.92}
                    stroke="var(--color-void)"
                    strokeWidth={1}
                  />
                  {(hovered === n.id || selectedRisk === n.id) && (
                    <g>
                      <rect
                        x={r + 6}
                        y={-30}
                        width={190}
                        height={60}
                        rx={4}
                        fill="var(--color-panel-raised)"
                        stroke="var(--color-hair)"
                      />
                      <text x={r + 12} y={-14} fill="var(--color-primary)" fontSize={11} fontFamily="IBM Plex Sans">
                        {n.label}
                      </text>
                      <text x={r + 12} y={0} fill="var(--color-dim)" fontSize={9} fontFamily="IBM Plex Mono">
                        DMS {n.dms_score.toFixed(1)} · betw {n.betweenness_centrality.toFixed(3)}
                      </text>
                      <text x={r + 12} y={13} fill="var(--color-dim)" fontSize={9} fontFamily="IBM Plex Mono">
                        eig {n.eigenvector_centrality.toFixed(3)} · deg {n.degree}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
        <div className="mt-2 flex flex-wrap gap-4 font-mono text-[10px] text-dim">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: NODE_TYPE_COLOR.developer }} />
            developer
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full opacity-55" style={{ background: NODE_TYPE_COLOR.repo }} />
            repo
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: NODE_TYPE_COLOR.hackathon }} />
            hackathon
          </span>
          <span className="flex items-center gap-1.5">
            <Radio size={11} className="text-risk-critical" /> critical cut-vertex (pulsing)
          </span>
        </div>
      </div>

      {/* Structural Risk panel */}
      <div className="flex max-h-[460px] flex-col rounded-lg border border-hair bg-panel">
        <div className="flex items-center gap-2 border-b border-hair px-4 py-3">
          <ShieldAlert size={14} className="text-accent" />
          <h3 className="font-mono text-xs uppercase tracking-wider text-muted">Structural Risks</h3>
        </div>
        <div className="axiom-scrollbar flex-1 overflow-y-auto px-4 py-3">
          {structural_risks.length === 0 && (
            <p className="font-mono text-xs text-dim">No elevated-risk nodes detected in this topology.</p>
          )}
          <ul className="flex flex-col gap-2.5">
            {structural_risks.map((r) => (
              <li
                key={r.node_id}
                onMouseEnter={() => setSelectedRisk(r.node_id)}
                onMouseLeave={() => setSelectedRisk((s) => (s === r.node_id ? null : s))}
                className={`cursor-default rounded border px-3 py-2.5 transition-colors ${
                  r.risk_tier === "critical" ? "border-risk-critical/30 bg-risk-critical/5" : "border-hair bg-panel-raised"
                }`}
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="font-sans text-xs text-primary">{r.label}</span>
                  <RiskBadge tier={r.risk_tier} />
                </div>
                <p className="font-sans text-[11px] leading-relaxed text-muted">{r.narrative}</p>
                <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[10px] text-dim">
                  <span>DMS {r.dms_score.toFixed(1)}</span>
                  <span>betweenness {r.betweenness_centrality.toFixed(3)}</span>
                  <span>eigenvector {r.eigenvector_centrality.toFixed(3)}</span>
                  {r.is_articulation_point && <span className="text-risk-critical">true cut-vertex</span>}
                </div>
              </li>
            ))}
          </ul>
        </div>
        <div className="border-t border-hair px-4 py-2 font-mono text-[10px] text-dim">
          {stats.num_connected_components} component{stats.num_connected_components === 1 ? "" : "s"} · avg
          clustering {stats.avg_clustering_coefficient.toFixed(3)}
        </div>
      </div>
    </div>
  );
}
