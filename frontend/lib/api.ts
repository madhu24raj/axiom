/**
 * api.ts
 * ------
 * Thin fetch layer for the Axiom OS FastAPI backend. Every function returns
 * a FetchResult<T> ({ data, error }) instead of throwing, so components can
 * always render an explicit "[Connection: Not Established]" state instead
 * of silently showing stale or fabricated numbers.
 */

import type {
  ApplicationResponse,
  DealRow,
  FetchResult,
  HackathonProfile,
  MemoResponsePayload,
  ModeResponse,
  OpportunitySearchResponse,
  OutreachDraftResponse,
  OverseerChatResponse,
  PipelineOverview,
  SourcingNetworkResult,
  ThesisCriteria,
} from "./types";

const API_BASE =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE_URL) ||
  "http://localhost:8000";

async function safeFetch<T>(path: string, init?: RequestInit): Promise<FetchResult<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`, init);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return {
        data: null,
        error: `[${res.status}] ${body?.detail ?? "Request failed"}`,
      };
    }
    const data = (await res.json()) as T;
    return { data, error: null };
  } catch (err) {
    return {
      data: null,
      error: "[Connection: Not Established — check NEXT_PUBLIC_API_BASE_URL / backend is running]",
    };
  }
}

export async function getMode(): Promise<FetchResult<ModeResponse>> {
  return safeFetch<ModeResponse>("/api/mode");
}

export async function setMode(demoMode: boolean): Promise<FetchResult<ModeResponse>> {
  return safeFetch<ModeResponse>(`/api/mode?demo_mode=${demoMode}`, { method: "POST" });
}

export async function getHackathonProfiles(): Promise<FetchResult<HackathonProfile[]>> {
  return safeFetch<HackathonProfile[]>("/api/hackathon/profiles");
}

export async function getSourcingNetwork(): Promise<FetchResult<SourcingNetworkResult>> {
  return safeFetch<SourcingNetworkResult>("/api/network/sourcing");
}

export async function getPipelineOverview(): Promise<FetchResult<PipelineOverview>> {
  return safeFetch<PipelineOverview>("/api/pipeline/overview");
}

/**
 * Evaluates a single hackathon profile through the 3-axis agent mesh and
 * shapes the response into a DealRow the table/radar/trace panel can render.
 */
async function evaluateProfile(profile: HackathonProfile): Promise<DealRow | null> {
  const payload = {
    opportunity: {
      id: profile.founder_id,
      sector: profile.sector,
      founder_score: 50, // pre-thesis-filter placeholder; the real F_S is computed inside
      keywords: [profile.project],
      idea_summary: profile.project,
      engineering_signals: profile.raw_signals,
    },
    founder_profile: {
      founder_id: profile.founder_id,
      name: profile.name,
      public_footprints: profile.public_footprints,
      historical_signals: [
        {
          source: "github",
          timestamp: new Date().toISOString(),
          normalized_score: Math.min(1, (profile.raw_signals?.commits_7d ?? 0) / 60),
          confidence: 0.7,
          raw_data: {},
          data_points: profile.raw_signals,
        },
        {
          source: "hackathon",
          timestamp: new Date().toISOString(),
          normalized_score:
            profile.raw_signals?.hackathon_award_tier === "finalist"
              ? 0.95
              : profile.raw_signals?.hackathon_award_tier === "honorable mention"
              ? 0.7
              : 0.35,
          confidence: 0.8,
          raw_data: {},
          data_points: { hackathon_award_tier: profile.raw_signals?.hackathon_award_tier },
        },
      ],
    },
    claims_to_verify:
      profile.project === "parallel-agent-runner"
        ? [
            {
              claim_text: "5k GitHub stars inside 14 days",
              claimed_value: 5000,
              verification_query: "fast-context-ide (demo alias) stars",
            },
          ]
        : [],
  };

  const result = await safeFetch<{
    evaluation: {
      opportunity_id: string;
      founder: DealRow["founder"];
      market: DealRow["market"];
      idea_vs_market: DealRow["idea_vs_market"];
      trust_scores: DealRow["trust_scores"];
      thesis_check: DealRow["thesis_check"];
    };
    momentum: DealRow["momentum"];
  }>("/api/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!result.data) return null;
  const { evaluation, momentum } = result.data;
  return {
    opportunity_id: evaluation.opportunity_id,
    founder_name: profile.name,
    sector: profile.sector,
    founder: evaluation.founder,
    market: evaluation.market,
    idea_vs_market: evaluation.idea_vs_market,
    trust_scores: evaluation.trust_scores,
    thesis_check: evaluation.thesis_check,
    momentum,
    data_provenance: "demo_fixture",
  };
}

export async function fetchDealPipeline(): Promise<FetchResult<DealRow[]>> {
  const profilesResult = await getHackathonProfiles();
  if (!profilesResult.data) {
    return { data: null, error: profilesResult.error };
  }
  const rows = await Promise.all(profilesResult.data.map(evaluateProfile));
  const clean = rows.filter((r): r is DealRow => r !== null);
  if (clean.length === 0 && profilesResult.data.length > 0) {
    return { data: null, error: "[Pipeline evaluation unavailable — Not Disclosed]" };
  }
  return { data: clean, error: null };
}

/**
 * Live mode's pipeline: exactly what's been searched + evaluated this
 * session (backend/main.py's LiveSessionState). Empty on a fresh session --
 * that's the honest state, not an error.
 */
export async function getLiveOpportunities(): Promise<FetchResult<DealRow[]>> {
  return safeFetch<DealRow[]>("/api/opportunities/live");
}

/**
 * Keyword-heuristic filter over the active roster. In Live mode, a query
 * that matches nothing triggers a real Tavily+LLM enrichment pass on the
 * backend for that specific target -- see main.py's search_opportunities.
 */
export async function searchOpportunities(
  query: string
): Promise<FetchResult<OpportunitySearchResponse>> {
  return safeFetch<OpportunitySearchResponse>("/api/opportunities/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
}

/**
 * Ask the Overseer about one specific deal's already-computed numbers.
 * `context` should be the DealRow (plus an optional `network_risk` entry
 * merged in by the caller) -- the backend only ever reasons over exactly
 * what's passed here.
 */
export async function postOverseerChat(
  context: Record<string, any>,
  thesis: Record<string, any>,
  message: string
): Promise<FetchResult<OverseerChatResponse>> {
  return safeFetch<OverseerChatResponse>("/api/overseer/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ context, thesis, message }),
  });
}

// ---------------------------------------------------------------------------
// Thesis Engine -- required MVP #1: investor-configurable sectors, stage,
// geography, check size, ownership targets, and risk appetite.
// ---------------------------------------------------------------------------
export async function getThesis(): Promise<FetchResult<ThesisCriteria>> {
  return safeFetch<ThesisCriteria>("/api/thesis");
}

export async function setThesis(criteria: ThesisCriteria): Promise<FetchResult<ThesisCriteria>> {
  return safeFetch<ThesisCriteria>("/api/thesis", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(criteria),
  });
}

// ---------------------------------------------------------------------------
// Inbound Application -- required MVP #4: deck + company name minimum bar.
// Works in both Demo and Live mode (self-disclosed applicant data).
// ---------------------------------------------------------------------------
export async function submitApplication(payload: {
  company_name: string;
  deck_text: string;
  founder_name: string;
  sector?: string;
  stage?: string;
  geography?: string;
  github_url?: string;
}): Promise<FetchResult<ApplicationResponse>> {
  return safeFetch<ApplicationResponse>("/api/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Investment Memo -- Appendix 1's structure, grounded in the row's own
// already-computed data; missing sections come back as "Not disclosed."
// ---------------------------------------------------------------------------
export async function generateMemo(row: DealRow): Promise<FetchResult<MemoResponsePayload>> {
  return safeFetch<MemoResponsePayload>("/api/memo/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ row }),
  });
}

// ---------------------------------------------------------------------------
// Outbound Activate (MVP #5) -- outreach DRAFT for human review, never
// auto-sent by the system.
// ---------------------------------------------------------------------------
export async function draftOutreach(row: DealRow): Promise<FetchResult<OutreachDraftResponse>> {
  return safeFetch<OutreachDraftResponse>("/api/outreach/draft", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ row }),
  });
}
