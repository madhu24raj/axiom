/**
 * api.ts
 * ------
 * Thin fetch layer for the Axiom OS FastAPI backend. Every function returns
 * a FetchResult<T> ({ data, error }) instead of throwing, so components can
 * always render an explicit "[Connection: Not Established]" state instead
 * of silently showing stale or fabricated numbers.
 */

import type {
  DealRow,
  FetchResult,
  HackathonProfile,
  ModeResponse,
  PipelineOverview,
  SourcingNetworkResult,
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
    momentum,
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
