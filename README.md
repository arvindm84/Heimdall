# Heimdall

Heimdall runs AI agents (OpenClaw and Hermes) in sealed Docker containers. One firewall sits between each agent and your files, your mail, the web and the AI model, and it asks you before your data leaves.

Built at MadHacks 2026.

## What it does

- **Sealed agents.** Each agent runs in its own container with a fake API key. The real keys stay in the firewall, which swaps them in on the way out.
- **Folder access.** Before an agent's first start, you pick the folders it may see and label each one Public, Private or Confidential. Folders you don't pick don't exist for the agent. Shared folders are read only.
- **Placeholders.** Personal details in files, mail and web pages (names, email addresses, ID numbers such as SSNs) are swapped for placeholders like `{{EMAIL_1}}` before the agent sees them. The real values go back in only when you approve sending an email.
- **It asks before data leaves.**
  - Sending an email always asks you first.
  - Fetching a web page asks once the agent has read Private data or untrusted content (an email or a web page).
  - Text from a Confidential file needs your consent before it goes to a cloud AI model. Deny it and the model gets a "withheld" note instead.
- **Hidden text is cut out.** Text hidden in a page or email (`display:none`, HTML comments, zero-width characters) is removed before the agent reads it. If you add an Anthropic key, a second check also flags content that looks like a prompt injection.
- **Secret scan.** A request that carries a secret is blocked before it leaves. That covers the real API keys, common key formats from other services, and the agents' fake keys, which only show up somewhere else if something is trying to steal them. The real keys are caught even when split up, reversed, or encoded as hex or base64.
- **Dashboard.**
  - **Agents:** start and stop agents, set folder access, and get each chat's login.
  - **Activity:** every decision the firewall made, with its rule and reason.
  - **Flow:** a live graph of each request as it crosses the firewall.
- **Clean exit.** "Stop all agents" kills every agent at once. Closing the app window kills every Heimdall container.

## Limits today

- **Gmail is a test inbox.** The agent reads made-up `.eml` files from `tests/firewall/fixtures/inbox`. A "sent" email is saved as an `.eml` file, not delivered. Live Gmail isn't set up yet.
- **The app starts agents on Gemini.** The back end also supports Anthropic and a local Ollama model, but the app has no setting to pick one yet.
- **Agents can't write to your folders.** The folder popup has no write option.
- **Docker Desktop is required.** The first start of each agent builds its container, which takes a few minutes.
- **It runs from this repo.** It isn't packaged as a standalone app yet.
- **macOS only so far.** It's the only system we've run it on.

## Requirements

- Docker Desktop, running
- Python 3.11 and [uv](https://docs.astral.sh/uv/)
- Node 22 (comes with npm)
- A Gemini API key. An Anthropic key is optional; it turns on the prompt-injection check.

## Setup

```
git clone <this repo>
cd Heimdall
uv sync
cd frontend && npm install && npm run build && cd ..
```

Create `.env` in the repo root. Git ignores it, so never commit it.

```
GEMINI_API_KEY=your-key
ANTHROPIC_API_KEY=your-key    # optional
```

## Run

```
uv run python run.py
```

This opens the Heimdall window. Start Docker Desktop first.

To work on the UI with live reload instead, run `cd frontend && npm run dev`. It starts the back end too. Then open http://localhost:5173 in your browser.

## Try it

Use made-up files only.

```
mkdir -p ~/heimdall-test/Taxes ~/heimdall-test/Recipes
echo "Tax return 2025. SSN 123-45-6789. Refund: \$4,210." > ~/heimdall-test/Taxes/return.txt
echo "Pancakes: 2 eggs, 1 cup flour, 1 cup milk." > ~/heimdall-test/Recipes/pancakes.txt
```

1. On **Agents**, click **Folder access** for an agent. Tick `Recipes` as Public and `Taxes` as Confidential, then save.
2. Click **Start**. When it's running, the card shows a username and password.
3. Click **Open chat**. Your browser asks for that username and password.
4. Ask the agent to read `pancakes.txt`. Nothing asks you; it's Public.
5. Ask it to read `return.txt`. A consent card appears in Heimdall before the text reaches the AI model.
6. Watch **Activity** and **Flow** while you do this.

## How it fits together

```
Heimdall window (React)
        |
Back end (Flask, 127.0.0.1:8765): starts and stops agents, shows the firewall's questions
        |
docker compose
   |-- agent containers: OpenClaw, Hermes (fake key, no access to your files)
   |-- gateway: the firewall
         |-- tools the agents call: files, test Gmail, web fetch
         |-- model proxy: every AI model call goes through it
         |-- asks you through the back end (/api/raise) and reports each decision (/api/event)
```

## Repo layout

| Path | What's in it |
|---|---|
| `frontend/` | The app's UI: Agents, Activity and Flow pages |
| `backend/` | Flask API: launching agents, folder labels, the firewall's questions and events |
| `core/` | The firewall: policy, labels, placeholders, hidden-text and secret scanning, model proxy |
| `agents/` | Agent images, the agent manager and the gateway's compose file |
| `run.py` | Opens the desktop window |
| `tests/` | Firewall tests, and seam tests between the parts |

## Tests

```
uv run pytest
```

The seam tests start their own back end on port 8765, so close the Heimdall app before running them.
