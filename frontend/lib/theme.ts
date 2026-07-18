/**
 * theme.ts
 * --------
 * Single source of truth for Axiom OS's visual tokens. Injected once (by
 * Dashboard.tsx) as a raw <style> tag so every sub-component can rely on the
 * same class names without each file re-declaring CSS variables.
 *
 * Palette rationale:
 *  - bg-void / bg-panel / bg-panel-raised give three elevations of near-black,
 *    the base "quantitative terminal" surface.
 *  - accent (signal amber, #E8A33D) is reserved for live-mode state, primary
 *    actions, and the Founder axis -- it never becomes a background wash.
 *  - bull / bear / neutral are the ONLY colors that ever encode "good / bad /
 *    unclear" -- they are not reused for decoration elsewhere.
 *  - axis-market (cyan) and axis-idea (violet) exist purely to distinguish
 *    the two other axes on the Radar chart from the Founder axis's amber --
 *    they carry no bull/bear semantic meaning.
 *  - risk-critical / risk-elevated / risk-nominal drive the Structural Risk
 *    panel's tier badges, deliberately distinct from bull/bear so "network
 *    fragility" reads as its own dimension, not a reused good/bad scale.
 */

export const themeCSS = `
  :root {
    --color-void: #0A0C10;
    --color-panel: #12151B;
    --color-panel-raised: #181C24;
    --color-panel-inset: #0D1015;
    --color-hair: #262B35;
    --color-hair-strong: #333A47;
    --color-primary: #E8EAED;
    --color-muted: #8A93A3;
    --color-dim: #545B68;
    --color-accent: #E8A33D;
    --color-accent-dim: #8A6326;
    --color-bull: #4FD1A5;
    --color-bear: #F06464;
    --color-neutral: #8A93A3;
    --color-axis-founder: #E8A33D;
    --color-axis-market: #5EC8F2;
    --color-axis-idea: #B084F0;
    --color-risk-critical: #F06464;
    --color-risk-elevated: #E8A33D;
    --color-risk-nominal: #4A5261;
  }

  .axiom-root { background-color: var(--color-void); color: var(--color-primary); }
  .bg-void { background-color: var(--color-void); }
  .text-void { color: var(--color-void); }
  .bg-panel { background-color: var(--color-panel); }
  .bg-panel-raised { background-color: var(--color-panel-raised); }
  .bg-panel-inset { background-color: var(--color-panel-inset); }
  .border-hair { border-color: var(--color-hair); }
  .border-hair-strong { border-color: var(--color-hair-strong); }
  .text-primary { color: var(--color-primary); }
  .text-muted { color: var(--color-muted); }
  .text-dim { color: var(--color-dim); }
  .text-accent { color: var(--color-accent); }
  .bg-accent { background-color: var(--color-accent); }
  .border-accent { border-color: var(--color-accent); }
  .text-bull { color: var(--color-bull); }
  .text-bear { color: var(--color-bear); }
  .text-neutral { color: var(--color-neutral); }
  .bg-bull { background-color: var(--color-bull); }
  .bg-bear { background-color: var(--color-bear); }
  .bg-neutral { background-color: var(--color-neutral); }
  .text-axis-founder { color: var(--color-axis-founder); }
  .text-axis-market { color: var(--color-axis-market); }
  .text-axis-idea { color: var(--color-axis-idea); }
  .bg-risk-critical { background-color: var(--color-risk-critical); }
  .bg-risk-elevated { background-color: var(--color-risk-elevated); }
  .bg-risk-nominal { background-color: var(--color-risk-nominal); }
  .text-risk-critical { color: var(--color-risk-critical); }
  .text-risk-elevated { color: var(--color-risk-elevated); }
  .text-risk-nominal { color: var(--color-risk-nominal); }

  .font-mono { font-family: 'IBM Plex Mono', ui-monospace, 'SF Mono', monospace; }
  .font-sans { font-family: 'IBM Plex Sans', ui-sans-serif, system-ui; }

  .axiom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
  .axiom-scrollbar::-webkit-scrollbar-track { background: var(--color-panel); }
  .axiom-scrollbar::-webkit-scrollbar-thumb { background: var(--color-hair-strong); border-radius: 3px; }

  @keyframes axiom-pulse-ring {
    0% { stroke-opacity: 0.9; stroke-width: 2px; }
    70% { stroke-opacity: 0; stroke-width: 10px; }
    100% { stroke-opacity: 0; stroke-width: 10px; }
  }
  .axiom-pulse { animation: axiom-pulse-ring 2.2s cubic-bezier(0.2, 0.6, 0.4, 1) infinite; }

  @keyframes axiom-fade-in {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .axiom-fade-in { animation: axiom-fade-in 0.35s ease-out both; }

  @media (prefers-reduced-motion: reduce) {
    .axiom-pulse, .axiom-fade-in { animation: none !important; }
  }
`;
