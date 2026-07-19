"use client";

/**
 * ApplyForm.tsx
 * -------------
 * Required MVP #4: "Apply: deck + company name is the minimum bar; any
 * further fields are the minimum needed for a confident 24-hour decision."
 * This is the inbound track -- a founder submitting their own data directly,
 * as opposed to search's VC-initiated live enrichment of a named target.
 * Works in both Demo and Live mode since nothing here is scraped.
 */

import { useState } from "react";
import { X, Send, Loader2 } from "lucide-react";
import type { DealRow } from "../../lib/types";
import { submitApplication } from "../../lib/api";

export default function ApplyForm({
  onClose,
  onSubmitted,
}: {
  onClose: () => void;
  onSubmitted: (row: DealRow) => void;
}) {
  const [companyName, setCompanyName] = useState("");
  const [founderName, setFounderName] = useState("");
  const [deckText, setDeckText] = useState("");
  const [sector, setSector] = useState("");
  const [stage, setStage] = useState("");
  const [geography, setGeography] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DealRow | null>(null);

  const canSubmit = companyName.trim().length > 0 && founderName.trim().length > 0 && deckText.trim().length > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || submitting) return;
    setSubmitting(true);
    setError(null);
    const res = await submitApplication({
      company_name: companyName,
      founder_name: founderName,
      deck_text: deckText,
      sector: sector || undefined,
      stage: stage || undefined,
      geography: geography || undefined,
      github_url: githubUrl || undefined,
    });
    setSubmitting(false);
    if (res.data) {
      setResult(res.data.row);
      onSubmitted(res.data.row);
    } else {
      setError(res.error);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/70 p-4 backdrop-blur-sm">
      <div className="axiom-fade-in flex max-h-[90vh] w-full max-w-xl flex-col rounded-lg border border-hair bg-panel shadow-2xl">
        <div className="flex items-center justify-between border-b border-hair px-5 py-4">
          <h3 className="font-mono text-xs uppercase tracking-wider text-muted">Apply for Funding</h3>
          <button onClick={onClose} className="text-dim hover:text-primary">
            <X size={14} />
          </button>
        </div>

        {result ? (
          <div className="axiom-scrollbar flex-1 overflow-y-auto px-5 py-5">
            <p className="mb-3 font-mono text-xs text-bull">
              Application received and screened in {result.time_to_decision_seconds?.toFixed(2)}s.
            </p>
            <div className="grid grid-cols-3 gap-3 rounded border border-hair bg-panel-raised p-3">
              <div>
                <p className="font-mono text-[9px] uppercase text-dim">Founder</p>
                <p className="font-mono text-sm text-primary">{result.founder?.score?.toFixed(1) ?? "—"}</p>
              </div>
              <div>
                <p className="font-mono text-[9px] uppercase text-dim">Market</p>
                <p className="font-mono text-sm text-primary">{result.market?.score?.toFixed(1) ?? "—"}</p>
              </div>
              <div>
                <p className="font-mono text-[9px] uppercase text-dim">Idea vs Mkt</p>
                <p className="font-mono text-sm text-primary">{result.idea_vs_market?.score?.toFixed(1) ?? "—"}</p>
              </div>
            </div>
            {result.founder?.metadata?.is_cold_start && (
              <p className="mt-3 font-mono text-[10px] text-dim">
                Cold-start read (no GitHub/funding/network on file) — blended across{" "}
                {result.founder.metadata.cold_start_history?.length ?? 1} application(s) from this founder.
              </p>
            )}
            <p className="mt-3 font-mono text-[10px] text-dim">
              {result.founder ? "Passed the thesis filter — now visible in the Deal Pipeline below." : "Did not pass the current thesis filter."}
            </p>
            <button
              onClick={onClose}
              className="mt-4 w-full rounded border border-accent/50 bg-accent/10 py-2 font-mono text-xs uppercase tracking-wider text-accent hover:bg-accent/20"
            >
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="axiom-scrollbar flex-1 overflow-y-auto px-5 py-4">
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-dim">
                    Company Name *
                  </label>
                  <input
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    required
                    className="w-full rounded border border-hair bg-panel-inset px-2 py-1.5 font-mono text-xs text-primary"
                  />
                </div>
                <div>
                  <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-dim">
                    Your Name *
                  </label>
                  <input
                    value={founderName}
                    onChange={(e) => setFounderName(e.target.value)}
                    required
                    className="w-full rounded border border-hair bg-panel-inset px-2 py-1.5 font-mono text-xs text-primary"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-dim">
                  Deck / Application Summary *
                </label>
                <textarea
                  value={deckText}
                  onChange={(e) => setDeckText(e.target.value)}
                  required
                  rows={6}
                  placeholder="Paste your deck content or a summary: problem, product, traction, why now…"
                  className="w-full resize-none rounded border border-hair bg-panel-inset px-2 py-1.5 font-mono text-xs text-primary placeholder:text-dim"
                />
                <p className="mt-1 font-mono text-[9px] text-dim">
                  No GitHub or track record? That's fine — this is read by a cold-start-aware assessment, not
                  penalized as a blank slate.
                </p>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-dim">Sector</label>
                  <input
                    value={sector}
                    onChange={(e) => setSector(e.target.value)}
                    placeholder="infra"
                    className="w-full rounded border border-hair bg-panel-inset px-2 py-1.5 font-mono text-xs text-primary placeholder:text-dim"
                  />
                </div>
                <div>
                  <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-dim">Stage</label>
                  <input
                    value={stage}
                    onChange={(e) => setStage(e.target.value)}
                    placeholder="pre-seed"
                    className="w-full rounded border border-hair bg-panel-inset px-2 py-1.5 font-mono text-xs text-primary placeholder:text-dim"
                  />
                </div>
                <div>
                  <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-dim">Geography</label>
                  <input
                    value={geography}
                    onChange={(e) => setGeography(e.target.value)}
                    placeholder="US"
                    className="w-full rounded border border-hair bg-panel-inset px-2 py-1.5 font-mono text-xs text-primary placeholder:text-dim"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-dim">
                  GitHub URL (optional)
                </label>
                <input
                  value={githubUrl}
                  onChange={(e) => setGithubUrl(e.target.value)}
                  placeholder="https://github.com/yourhandle"
                  className="w-full rounded border border-hair bg-panel-inset px-2 py-1.5 font-mono text-xs text-primary placeholder:text-dim"
                />
              </div>

              {error && <p className="font-mono text-[10px] text-bear">{error}</p>}

              <button
                type="submit"
                disabled={!canSubmit || submitting}
                className="mt-1 flex items-center justify-center gap-2 rounded border border-accent/50 bg-accent/10 py-2 font-mono text-xs uppercase tracking-wider text-accent hover:bg-accent/20 disabled:opacity-40"
              >
                {submitting ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                {submitting ? "Screening…" : "Submit Application"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
