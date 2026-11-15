# Heimdall frontend

React + Vite + TypeScript + Tailwind. "Checkpoint ledger" theme: calm dark pine, paper text, stamp-ink verdicts.

## Run it

Needs Node 20+, [uv](https://docs.astral.sh/uv/) (Python 3.11 is installed by uv), and Docker Desktop for starting agents.
Put API keys in `.env` at the repo root (copy `.env.example`).

```bash
cd frontend
npm run setup   # first time: npm packages + the Python environment (uv sync)
npm run dev     # UI (web) + Flask (api) together -> http://localhost:5173
```

- UI only, without Flask: `npm run dev:web`
- The desktop app: `npm run build`, then from the repo root `uv run python run.py`

## How it talks to the backend

Call the backend as `/api/<route>` (e.g. `fetch("/api/response", ...)`, `new EventSource("/api/events")`).
Vite forwards `/api/*` to Flask on 127.0.0.1:8765 in development; in the desktop app Flask serves the UI and `/api` itself.

## Layout

- `src/index.css`: theme colors and fonts (`bg-ground`, `bg-raised`, `text-paper`, `text-lichen`, `border-rule`, `text-allowed` / `text-blocked` / `text-waiting`)
- `src/components/Header.tsx`: app name, tabs, Stop all agents
- `src/pages/`: Agents (home), Activity, Flow
- `src/data/tools.ts`: plain-language names for tools (never show raw ids like `files_read`)
- `src/lib/api.ts`: calls to the back end (agents, launch, stop, kill)
- `src/data/agents.ts`: the agents and the permissions Start sends, until there's a permissions screen
- `src/data/sample.ts`: SAMPLE firewall events for Activity and Flow (temporary)

## Design rules (from the frontend-design skill)

- Sentence case everywhere; no all-caps labels, no "A · B" strings, no arrows on buttons.
- Monospace only for literal paths and URLs.
- Colors carry meaning: sage = allowed, oxide red = blocked, ochre = waiting. No glows or neon.
- The stamps in Activity are the one bold element; keep everything else quiet.
