"use client";

/**
 * ThesisConfigPanel.tsx
 * ---------------------
 * Required MVP #1 from the brief: "Investor sets sectors, stage, geography,
 * check size, ownership targets, and risk appetite. Every recommendation is
 * filtered and scored through this fund-specific lens." This isn't a
 * display-only settings screen -- risk_appetite actually shifts the
 * effective founder-score bar server-side (see agents.py's
 * ThesisEngine.RISK_ADJUSTMENT), and every evaluation path reads this same
 * config.
 */

import { useEffect, useState } from "react";
import { X, Sliders } from "lucide-react";
import type { ThesisCriteria } from "../../lib/types";
import { getThesis, setThesis } from "../../lib/api";

const SECTOR_OPTIONS = ["dev tools", "infra", "agentic systems", "fintech", "healthtech", "climate"];
const STAGE_OPTIONS = ["pre-seed", "seed", "series-a"];
const RISK_OPTIONS: { value: ThesisCriteria["risk_appetite"]; label: string; note: string }[] = [
  { value: "conservative", label: "Conservative", note: "+15 to the F_S bar" },
  { value: "balanced", label: "Balanced", note: "no adjustment" },
  { value: "aggressive", label: "Aggressive", note: "−15 to the F_S bar" },
];

function Toggle({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded border px-2 py-1 font-mono text-[11px] transition-colors ${
        active ? "border-accent/50 bg-accent/10 text-accent" : "border-hair text-muted hover:text-primary"
      }`}
    >
      {label}
    </button>
  );
}

export default function ThesisConfigPanel({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [criteria, setCriteria] = useState<ThesisCriteria | null>(null);
  const [geographyInput, setGeographyInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getThesis().then((r) => {
      if (r.data) {
        setCriteria(r.data);
        setGeographyInput(r.data.geography.join(", "));
      } else {
        setError(r.error);
      }
    });
  }, []);

  function toggleSector(sector: string) {
    if (!criteria) return;
    const has = criteria.target_sectors.includes(sector);
    setCriteria({
      ...criteria,
      target_sectors: has ? criteria.target_sectors.filter((s) => s !== sector) : [...criteria.target_sectors, sector],
    });
  }

  async function handleSave() {
    if (!criteria) return;
    setSaving(true);
    setError(null);
    const geography = geographyInput
      .split(",")
      .map((g) => g.trim())
      .filter(Boolean);
    const result = await setThesis({ ...criteria, geography });
    setSaving(false);
    if (result.data) {
      onSaved();
      onClose();
    } else {
      setError(result.error);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/70 backdrop-blur-sm">
      <div className="axiom-fade-in w-full max-w-lg rounded-lg border border-hair bg-panel shadow-2xl">
        <div className="flex items-center justify-between border-b border-hair px-5 py-4">
          <div className="flex items-center gap-2">
            <Sliders size={14} className="text-accent" />
            <h3 className="font-mono text-xs uppercase tracking-wider text-muted">Thesis Engine</h3>
          </div>
          <button onClick={onClose} className="text-dim hover:text-primary">
            <X size={14} />
          </button>
        </div>

        {!criteria ? (
          <div className="px-5 py-8 text-center font-mono text-xs text-dim">
            {error ?? "Loading thesis criteria…"}
          </div>
        ) : (
          <div className="flex flex-col gap-4 px-5 py-4">
            <div>
              <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-dim">
                Target Sectors
              </label>
              <div className="flex flex-wrap gap-1.5">
                {SECTOR_OPTIONS.map((s) => (
                  <Toggle key={s} label={s} active={criteria.target_sectors.includes(s)} onClick={() => toggleSector(s)} />
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-dim">Stage</label>
                <select
                  value={criteria.stage}
                  onChange={(e) => setCriteria({ ...criteria, stage: e.target.value })}
                  className="w-full rounded border border-hair bg-panel-inset px-2 py-1.5 font-mono text-xs text-primary"
                >
                  {STAGE_OPTIONS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-dim">
                  Check Size (USD)
                </label>
                <input
                  type="number"
                  value={criteria.min_check_fit_usd}
                  onChange={(e) => setCriteria({ ...criteria, min_check_fit_usd: Number(e.target.value) })}
                  className="w-full rounded border border-hair bg-panel-inset px-2 py-1.5 font-mono text-xs text-primary"
                />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-dim">
                Geography (comma-separated, blank = no restriction)
              </label>
              <input
                value={geographyInput}
                onChange={(e) => setGeographyInput(e.target.value)}
                placeholder="e.g. US, EU, Remote"
                className="w-full rounded border border-hair bg-panel-inset px-2 py-1.5 font-mono text-xs text-primary placeholder:text-dim"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-dim">
                  Min Founder Score
                </label>
                <input
                  type="number"
                  value={criteria.min_founder_score}
                  onChange={(e) => setCriteria({ ...criteria, min_founder_score: Number(e.target.value) })}
                  className="w-full rounded border border-hair bg-panel-inset px-2 py-1.5 font-mono text-xs text-primary"
                />
              </div>
              <div>
                <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-dim">
                  Ownership Target %
                </label>
                <input
                  type="number"
                  value={criteria.ownership_target_pct}
                  onChange={(e) => setCriteria({ ...criteria, ownership_target_pct: Number(e.target.value) })}
                  className="w-full rounded border border-hair bg-panel-inset px-2 py-1.5 font-mono text-xs text-primary"
                />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-dim">
                Risk Appetite
              </label>
              <div className="flex gap-1.5">
                {RISK_OPTIONS.map((r) => (
                  <button
                    key={r.value}
                    type="button"
                    onClick={() => setCriteria({ ...criteria, risk_appetite: r.value })}
                    className={`flex-1 rounded border px-2 py-1.5 text-center transition-colors ${
                      criteria.risk_appetite === r.value
                        ? "border-accent/50 bg-accent/10 text-accent"
                        : "border-hair text-muted hover:text-primary"
                    }`}
                  >
                    <div className="font-mono text-[11px]">{r.label}</div>
                    <div className="font-mono text-[9px] text-dim">{r.note}</div>
                  </button>
                ))}
              </div>
            </div>

            {error && <p className="font-mono text-[10px] text-bear">{error}</p>}

            <button
              onClick={handleSave}
              disabled={saving}
              className="mt-1 rounded border border-accent/50 bg-accent/10 py-2 font-mono text-xs uppercase tracking-wider text-accent hover:bg-accent/20 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Apply Thesis"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
