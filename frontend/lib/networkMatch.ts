import type { DealRow, SourcingNetworkResult, StructuralRisk } from "./types";

/**
 * Looks up a DealRow's corresponding node in the Sourcing Network Graph's
 * structural-risk list, matching by id first (exact) and falling back to a
 * case-insensitive label match. Returns null rather than a best-effort guess
 * if nothing matches -- the Overseer chat should say "not mapped" rather
 * than fabricate a network reading.
 */
export function findStructuralRisk(
  network: SourcingNetworkResult | null,
  row: DealRow
): StructuralRisk | null {
  if (!network) return null;
  const byId = network.structural_risks.find((r) => r.node_id === row.opportunity_id);
  if (byId) return byId;
  const byLabel = network.structural_risks.find(
    (r) => r.label.toLowerCase() === row.founder_name.toLowerCase()
  );
  return byLabel ?? null;
}
