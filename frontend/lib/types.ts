/**
 * types.ts
 * --------
 * Mirrors backend/*.py schemas field-for-field. Keep this file in sync with
 * scoring.py, agents.py, network_analysis.py, and main.py response models --
 * it is the single source of truth the whole dashboard imports from.
 */

// ---------------------------------------------------------------------------
// Agentic evaluation (agents.py / scoring.py)
// ---------------------------------------------------------------------------
export interface ReasoningStep {
  step: string;
  detail: string;
  source_ref: string | null;
  timestamp: string;
}

export interface SignalContribution {
  source: string;
  age_days: number;
  normalized_score: number;
  source_weight: number;
  decay_factor: number;
  contribution: number;
  contribution_pct_of_total: number;
}

export interface FounderScoreBreakdown {
  founder_score: number;
  lambda_decay: number;
  signals: SignalContribution[];
}

export interface AxisResult {
  axis: "founder" | "market" | "idea_vs_market" | string;
  score: number | null;
  confidence: number;
  reasoning_trace: ReasoningStep[];
  raw_refs: string[];
  metadata: Record<string, any> | null;
}

export interface ClaimVerification {
  claim_text: string;
  claimed_value: number | null;
  extracted_value: number | null;
  source_url: string | null;
  evidence_excerpt: string | null;
  verified: boolean;
}

export interface TrustScoreResult {
  claim_text: string;
  trust_score: number;
  discrepancy_pct: number | null;
  flagged: boolean;
  prior_mean: number;
  posterior_successes: number;
  posterior_failures: number;
  evidence: ClaimVerification[];
}

export type MomentumDirection = "up" | "down" | "pivot" | "flat";

export interface MomentumVector {
  direction: MomentumDirection;
  arrow: string;
  velocity: number;
  prior_velocity: number | null;
  accelerating: boolean;
  basis: "score_history" | "signal_frequency" | "insufficient_data" | string;
  note: string;
}

export type DataProvenance = "demo_fixture" | "live_enriched" | "live_session" | string;

export interface DealRow {
  opportunity_id: string;
  founder_name: string;
  sector: string;
  founder: AxisResult | null;
  market: AxisResult | null;
  idea_vs_market: AxisResult | null;
  trust_scores: TrustScoreResult[];
  momentum: MomentumVector;
  data_provenance: DataProvenance;
  data_confidence?: string | null;
  pipeline_stage?: string;
  source_urls?: string[];
  summary?: string | null;
  company_name?: string;
  deck_text?: string;
  stage?: string | null;
  geography?: string | null;
  applications_on_file?: number;
  identity_key?: string;
  first_signal_at?: string;
  decision_at?: string;
  time_to_decision_seconds?: number;
  axis_trends?: Record<string, "improving" | "declining" | "stable">;
}

export interface ColdStartRead {
  timestamp: string;
  point_estimate_0to100: number;
  low_estimate_0to100: number;
  high_estimate_0to100: number;
  rationale: string;
  primary_signal: string;
}

export interface OutreachDraftResponse {
  draft: string;
  note: string;
}

// ---------------------------------------------------------------------------
// Thesis Engine (main.py: /api/thesis)
// ---------------------------------------------------------------------------
export interface ThesisCriteria {
  min_check_fit_usd: number;
  target_sectors: string[];
  excluded_sectors: string[];
  min_founder_score: number;
  stage: string;
  geography: string[];
  ownership_target_pct: number;
  risk_appetite: "conservative" | "balanced" | "aggressive";
}

// ---------------------------------------------------------------------------
// Inbound Application (main.py: /api/apply)
// ---------------------------------------------------------------------------
export interface ApplicationRequest {
  company_name: string;
  deck_text: string;
  founder_name: string;
  sector?: string;
  stage?: string;
  geography?: string;
  github_url?: string;
}

export interface ApplicationResponse {
  row: DealRow;
}

// ---------------------------------------------------------------------------
// Investment Memo (main.py: /api/memo/generate)
// ---------------------------------------------------------------------------
export const MEMO_SECTION_ORDER: { key: string; label: string; required: boolean }[] = [
  { key: "company_snapshot", label: "Company Snapshot", required: true },
  { key: "investment_hypotheses", label: "Investment Hypotheses", required: true },
  { key: "swot", label: "SWOT", required: true },
  { key: "team_and_history", label: "Team & History", required: false },
  { key: "problem_and_product", label: "Problem & Product", required: true },
  { key: "technology_and_defensibility", label: "Technology & Defensibility", required: false },
  { key: "market_sizing", label: "Market Sizing", required: false },
  { key: "competition", label: "Competition", required: false },
  { key: "traction_and_kpis", label: "Traction & KPIs", required: true },
  { key: "financials_and_round_structure", label: "Financials & Round Structure", required: false },
  { key: "cap_table", label: "Cap Table", required: false },
  { key: "due_diligence_log", label: "Due Diligence Log", required: false },
  { key: "exit_perspective", label: "Exit Perspective", required: false },
];

export interface MemoResponsePayload {
  memo: Record<string, string>;
  adversarial_view: string;
  generated_at: string;
  time_to_decision_seconds: number | null;
}

export interface HackathonProfile {
  founder_id: string;
  name: string;
  public_footprints: Record<string, string>;
  project: string;
  sector: string;
  raw_signals: Record<string, any>;
  pipeline_stage: "sourced" | "screened" | "diligence" | "approved" | string;
}

// ---------------------------------------------------------------------------
// Sourcing Network Graph (network_analysis.py)
// ---------------------------------------------------------------------------
export type NetworkNodeType = "developer" | "repo" | "hackathon" | string;
export type RiskTier = "critical" | "elevated" | "nominal" | string;

export interface NetworkNodeOut {
  id: string;
  label: string;
  node_type: NetworkNodeType;
  sub_label: string | null;
  meta: Record<string, any>;
  degree: number;
  eigenvector_centrality: number;
  betweenness_centrality: number;
  is_articulation_point: boolean;
  fragmentation_pct_if_removed: number;
  dms_score: number;
  risk_tier: RiskTier;
}

export interface NetworkEdge {
  source: string;
  target: string;
  weight: number;
  edge_type: string;
}

export interface StructuralRisk {
  node_id: string;
  label: string;
  node_type: NetworkNodeType;
  eigenvector_centrality: number;
  betweenness_centrality: number;
  is_articulation_point: boolean;
  fragmentation_pct_if_removed: number;
  dms_score: number;
  risk_tier: RiskTier;
  narrative: string;
}

export interface NetworkStats {
  num_nodes: number;
  num_edges: number;
  density: number;
  num_connected_components: number;
  largest_component_size: number;
  avg_clustering_coefficient: number;
  articulation_point_count: number;
}

export interface SourcingNetworkResult {
  nodes: NetworkNodeOut[];
  edges: NetworkEdge[];
  structural_risks: StructuralRisk[];
  stats: NetworkStats;
  label: string;
}

// Client-side augmentation once d3-force has assigned coordinates.
export interface PositionedNode extends NetworkNodeOut {
  x: number;
  y: number;
  vx?: number;
  vy?: number;
}

// ---------------------------------------------------------------------------
// Pipeline Overview: Command KPIs + Funnel (main.py)
// ---------------------------------------------------------------------------
export interface PipelineKPIs {
  total_opportunities: number;
  high_potential_count: number;
  avg_founder_score: number;
  capital_deployed_usd: number;
  check_size_usd: number;
  thesis_pass_rate_pct: number;
  human_approval_required: boolean;
}

export interface FunnelStage {
  stage: string;
  count: number;
}

export interface PipelineOverview {
  kpis: PipelineKPIs;
  funnel: FunnelStage[];
  provenance: DataProvenance;
  label: string;
}

// ---------------------------------------------------------------------------
// Search (main.py: /api/opportunities/search)
// ---------------------------------------------------------------------------
export interface OpportunitySearchResponse {
  matches: DealRow[];
  match_strategy: "keyword_heuristic_v1" | "live_enrichment" | string;
  provenance: DataProvenance;
  message: string | null;
}

// ---------------------------------------------------------------------------
// Overseer Chat (main.py: /api/overseer/chat)
// ---------------------------------------------------------------------------
export interface OverseerChatResponse {
  reply: string;
}

export interface OverseerChatTurn {
  role: "user" | "assistant";
  text: string;
}

// ---------------------------------------------------------------------------
// Mode
// ---------------------------------------------------------------------------
export interface ModeResponse {
  demo_mode: boolean;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Generic result envelope used by lib/api.ts so components can render
// "[Connection: Not Established]" states instead of fabricating data.
// ---------------------------------------------------------------------------
export interface FetchResult<T> {
  data: T | null;
  error: string | null;
}
