# The VC Brain — Autonomous Venture Investment Operating System

An end-to-end sourcing → screening → diligence → decisioning pipeline built to
demo cleanly on flaky Wi-Fi and to run for real once API keys are set.

## Layout

```
backend/
  main.py        FastAPI app: routes, global Live/Demo toggle, Live+Cached
                  tool implementations for Tavily and the LLM
  scoring.py      FounderScoreEngine (decayed multi-source F_S) and the
                  Bayesian TrustScoreEngine used by the Validator Agent
  agents.py       ThesisEngine + independent Founder / Market / Idea-vs-Market
                  axis agents + ValidatorAgent + DealOrchestrator
  mock_data.py    Labeled fixtures for Demo Mode (historical simulation +
                  live-hackathon-mode fallback data)
frontend/
  components/Dashboard.tsx   Next.js 14 client dashboard ("Bloomberg Terminal
                              meets Notion"): pipeline grid, Live/Demo toggle,
                              per-claim trust badges, Agentic Traceability
                              slide-over panel
```

## Running the backend

```bash
cd backend
pip install fastapi uvicorn pydantic httpx
uvicorn main:app --reload --port 8000
```

Defaults to **Demo Mode** (`demo_mode=True`) so it's fully functional with
zero API keys — every external call routes through `mock_data.py`.

To go live, set:

```bash
export OPENAI_API_KEY=...      # reserved for future GPT-4o structured calls
export ANTHROPIC_API_KEY=...   # used by LiveLLMClient (claude-sonnet-4-6)
export TAVILY_API_KEY=...
```

then `POST /api/mode?demo_mode=false` (or flip the toggle in the UI).

## Running the frontend

```bash
cd frontend
# inside a Next.js 14 App Router project with Tailwind configured:
#   npm install ibm-plex-mono ibm-plex-sans   (or load via next/font)
#   drop components/Dashboard.tsx into app/dashboard/page.tsx or import it
export NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

## Design decisions worth knowing about

- **No averaging across axes.** Founder / Market / Idea-vs-Market scores are
  computed by three independent, concurrently-running agents and are never
  collapsed into a single blended number — that's a product requirement, not
  an oversight.
- **Nothing is fabricated.** Every agent returns `None`/`null` for a metric it
  doesn't have grounded data for; the UI renders that as `[Not Disclosed]`
  rather than inventing a plausible-looking number.
- **Live vs. Cached is a routing decision, not an agent decision.** Agents
  only ever talk to the `TavilyClient` / `LLMClient` protocols in
  `agents.py`; `main.py` is the only place that decides whether those
  protocols are backed by real HTTP calls or `mock_data.py`.
- **The historical "reverse sourcing" scenario in `mock_data.py` is explicitly
  labeled as an illustrative simulation**, not a factual claim about any real
  company's history — it exists solely to demo the scoring pipeline end to
  end.

## Tests run during development

`backend/scoring.py` and `backend/agents.py` were exercised directly
(Founder Score decay math, Bayesian trust scoring, full async orchestrator
fan-out) and `backend/main.py` was booted with FastAPI's `TestClient` to
confirm `/api/healthz`, `/api/mode`, `/api/simulation/historical`,
`/api/hackathon/telemetry`, and `/api/evaluate` all return correctly in Demo
Mode, and that Live Mode fails loudly (`503`) instead of silently
mock-serving data when no API keys are configured. `frontend/components/Dashboard.tsx`
was syntax-checked by transpiling it through the TypeScript compiler.
