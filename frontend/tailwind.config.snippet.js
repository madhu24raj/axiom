/**
 * tailwind.config.snippet.js
 * --------------------------
 * Several components use Tailwind's opacity-modifier syntax on Axiom OS's
 * custom semantic colors (e.g. `bg-bear/5`, `border-risk-critical/30`,
 * `border-accent/50`). Tailwind can only generate those on colors it knows
 * about via `theme.extend.colors`, so merge this into your project's
 * tailwind.config.js. The plain `.bg-bear` / `.text-accent` / etc. classes
 * themselves are supplied at runtime by lib/theme.ts and work regardless --
 * this snippet only unlocks the `/NN` opacity variants.
 */
module.exports = {
  theme: {
    extend: {
      colors: {
        void: "#0A0C10",
        panel: "#12151B",
        "panel-raised": "#181C24",
        "panel-inset": "#0D1015",
        hair: "#262B35",
        "hair-strong": "#333A47",
        primary: "#E8EAED",
        muted: "#8A93A3",
        dim: "#545B68",
        accent: "#E8A33D",
        bull: "#4FD1A5",
        bear: "#F06464",
        neutral: "#8A93A3",
        "axis-founder": "#E8A33D",
        "axis-market": "#5EC8F2",
        "axis-idea": "#B084F0",
        "risk-critical": "#F06464",
        "risk-elevated": "#E8A33D",
        "risk-nominal": "#4A5261",
      },
    },
  },
};
