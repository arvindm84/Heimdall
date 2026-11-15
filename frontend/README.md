# Heimdall frontend

React + Vite + TypeScript + Tailwind. "Checkpoint ledger" theme: calm dark pine, paper text, stamp-ink verdicts.

## Run it

Needs Node 20+ and Python 3.11 with pip.

```bash
cd frontend
npm run setup   # first time: installs npm packages + the backend's Python requirements
npm run dev     # starts the UI (web) and Flask (api) together
```

Open http://localhost:5173. Ctrl+C stops both.

- UI only, without Flask: `npm run dev:web`
- Using a virtualenv? Activate it before `npm run setup` / `npm run dev`; both use `python3`.

## How it talks to the backend

Call the backend as `/api/<route>` (e.g. `fetch("/api/response", ...)`, `new EventSource("/api/events")`).
Vite forwards `/api/*` to Flask on 127.0.0.1:5000 with `/api` removed, so there's no CORS setup.

## Layout

- `src/index.css`: theme colors and fonts (`bg-ground`, `bg-raised`, `text-paper`, `text-lichen`, `border-rule`, `text-allowed` / `text-blocked` / `text-waiting`)
- `src/components/Header.tsx`: app name, tabs, Stop all agents
- `src/pages/`: Agents (home), Activity, Flow
- `src/data/tools.ts`: plain-language names for tools (never show raw ids like `files_read`)
- `src/data/agents.ts`: MOCK agents until the backend has a list endpoint
- `src/data/sample.ts`: SAMPLE firewall events for Activity and Flow (temporary)

## Design rules (from the frontend-design skill)

- Sentence case everywhere; no all-caps labels, no "A · B" strings, no arrows on buttons.
- Monospace only for literal paths and URLs.
- Colors carry meaning: sage = allowed, oxide red = blocked, ochre = waiting. No glows or neon.
- The stamps in Activity are the one bold element; keep everything else quiet.
