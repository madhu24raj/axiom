"use client";

/**
 * MemoView.tsx
 * ------------
 * Renders Appendix 1's Investment Memo checklist. Required sections
 * (Company snapshot, Investment hypotheses, SWOT, Problem & product,
 * Traction & KPIs) render first and are visually marked; optional sections
 * follow. Any section the backend returned as "Not disclosed" renders in a
 * distinct dim/dashed style -- per the brief, a memo that marks its own
 * gaps is MORE trustworthy, so that state is designed to look intentional,
 * not broken.
 */

import { useEffect, useState } from "react";
import { X, FileText, Swords, Clock } from "lucide-react";
import type { DealRow, MemoResponsePayload } from "../../lib/types";
import { MEMO_SECTION_ORDER } from "../../lib/types";
import { generateMemo } from "../../lib/api";

function SectionCard({ label, required, text }: { label: string; required: boolean; text: string }) {
  const isNotDisclosed = text.trim().toLowerCase().startsWith("not disclosed");
  return (
    <div className={`rounded border px-3 py-2.5 ${isNotDisclosed ? "border-dashed border-hair bg-panel-inset" : "border-hair bg-panel-raised"}`}>
      <div className="mb-1 flex items-center gap-2">
        <h5 className="font-mono text-[10px] uppercase tracking-wider text-muted">{label}</h5>
        {required && <span className="rounded bg-accent/10 px-1 py-0.5 font-mono text-[8px] text-accent">required</span>}
      </div>
      <p className={`font-sans text-xs leading-relaxed ${isNotDisclosed ? "italic text-dim" : "text-primary"}`}>
        {text.replace(/^\[DEMO\]\s*/, "")}
      </p>
    </div>
  );
}

export default function MemoView({ row, onClose }: { row: DealRow; onClose: () => void }) {
  const [memo, setMemo] = useState<MemoResponsePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    generateMemo(row).then((r) => {
      if (cancelled) return;
      setLoading(false);
      if (r.data) setMemo(r.data);
      else setError(r.error);
    });
    return () => {
      cancelled = true;
    };
  }, [row]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/70 p-4 backdrop-blur-sm">
      <div className="axiom-fade-in flex max-h-[90vh] w-full max-w-2xl flex-col rounded-lg border border-hair bg-panel shadow-2xl">
        <div className="flex items-center justify-between border-b border-hair px-5 py-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wider text-dim">Investment Memo</p>
            <h3 className="font-sans text-base font-semibold text-primary">
              {row.company_name ?? row.founder_name}
            </h3>
          </div>
          <button onClick={onClose} className="text-dim hover:text-primary">
            <X size={14} />
          </button>
        </div>

        <div className="axiom-scrollbar flex-1 overflow-y-auto px-5 py-4">
          {loading && (
            <div className="flex items-center gap-2 py-8 justify-center font-mono text-xs text-dim">
              <FileText size={14} className="animate-pulse" /> Drafting memo from computed evaluation data…
            </div>
          )}
          {!loading && error && <p className="font-mono text-xs text-bear">{error}</p>}

          {!loading && memo && (
            <div className="flex flex-col gap-4">
              {memo.time_to_decision_seconds !== null && memo.time_to_decision_seconds !== undefined && (
                <div className="flex items-center gap-1.5 font-mono text-[10px] text-dim">
                  <Clock size={11} /> Sourced to decision in {memo.time_to_decision_seconds.toFixed(2)}s this pass
                </div>
              )}

              <div className="flex flex-col gap-2.5">
                {MEMO_SECTION_ORDER.map(({ key, label, required }) => (
                  <SectionCard key={key} label={label} required={required} text={memo.memo[key] ?? "Not disclosed"} />
                ))}
              </div>

              <div>
                <div className="mb-2 flex items-center gap-2">
                  <Swords size={13} className="text-bear" />
                  <h4 className="font-mono text-xs uppercase tracking-wider text-muted">Adversarial View</h4>
                </div>
                <p className="rounded border border-bear/30 bg-bear/5 px-3 py-2.5 font-sans text-xs leading-relaxed text-muted">
                  {memo.adversarial_view.replace(/^\[DEMO\]\s*/, "")}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
