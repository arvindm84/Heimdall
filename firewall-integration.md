# Integrating with the firewall

For B (agents) and C (back end and app), and the Claude sessions working for them. This describes the firewall as it is on Nov 15, with what B and C wire up to reach it. It replaces the earlier handoff files.

The to-do lists from the first version are done (GitHub issues #1 to #11). Section 5 lists what is still open.

## 1. The firewall in one page

The firewall is one container, `gateway`, built from `images/gateway/Dockerfile` and started by `agents/gateway/compose.yaml`. It listens on port 8080 on two networks: `agents-net`, which is internal (the agents' only network), and `outside`, which reaches the internet and the host.

| Path | What it serves | Who calls it |
|---|---|---|
| `http://gateway:8080/mcp` | MCP tools (streamable HTTP, no MCP sessions) | Agents |
| `http://gateway:8080/model/...` | Model proxy: swaps the fake key for the real one, scans, asks for consent | Agents |
| `http://host.docker.internal:8765/api/raise` | Questions to the user (approval and consent) | The gateway calls C's back end |
| `HEIMDALL_EVENTS_URL`, if set | Every event, one JSON object per POST | The gateway calls C's back end |

**The rules the firewall enforces.** Each one comes from `project-plan.md` sections 4 and 6:
- **Who an agent is:** its fake key. On MCP calls it travels as `Authorization: Bearer <fake key>`; on model calls, as `x-api-key` or Bearer. An unknown key is refused.
- **What an agent may do:** its `permissions.json` (section 2). Tools not listed are refused. Folders not listed don't exist for it. Model calls go only to the provider and model the user chose, or the local model.
- **Personal data** in file, mail and web text reaches the agent as typed placeholders (`{{EMAIL_1}}`). The real values stay in the gateway's vault (the `gateway-state` volume) and are filled in only in an email the user has approved.
- **Mail and web pages** are cleaned of hidden text before the agent sees them. Hidden text that looks like an instruction becomes a `hidden_instruction` event.
- **Approvals:** sending email always asks the user. After the agent has read mail or a web page, file writes and web fetches ask too.
- **Consent:** before text from a Confidential folder goes to a cloud model, the user is asked once per file per run, and can allow that file or the whole folder for the run. A deny strips the text and the request still goes out. The same applies to sends and fetches after a Confidential read. The local model is never asked about.
- **Memory:** Hermes keeps its own memory in its container (B's `heimdall-memory`: list, show, snapshot, rollback). It doesn't pass the firewall, so notes carry no label and a Confidential note reaches the model without a consent question (section 5).
- **Secrets:** a fake key or any other secret in a model request or a tool argument is blocked (`key_theft_attempt`, `secret_in_request`, `secret_in_tool_call`).

## 2. Agents (B)

### Model calls

Point the agent's model provider at the gateway, using the fake key as the API key. The gateway chooses the upstream from the API the agent speaks; the agent never names a host.

| Provider the user chose | Base URL | API style | Goes to |
|---|---|---|---|
| `gemini` | `http://gateway:8080/model` | OpenAI `chat/completions` | Gemini's OpenAI-compatible endpoint |
| `anthropic` | `http://gateway:8080/model` | Anthropic `messages` | Anthropic |
| `local` | `http://gateway:8080/model/local` | OpenAI `chat/completions` | Ollama on the host (`OLLAMA_URL`, default `http://host.docker.internal:11434/v1/chat/completions`). Default model `llama3.2:3b`: run `ollama pull llama3.2:3b` on the demo laptop |

OpenClaw sets this in `agents/openclaw/config.json` (`models.providers.heimdall`; `build_config` switches `baseUrl` for `local`). Hermes sets it with `GEMINI_BASE_URL` and `ANTHROPIC_BASE_URL` in `agents/hermes/compose.yaml`, and for `local` with `provider: custom` and `base_url` in its config. `gemini` runs live on both; `local` ran live on both against a stand-in Ollama server; `anthropic` is wired up but not run live (no key on the test laptop).

### MCP tools

```json
"url": "http://gateway:8080/mcp",
"headers": { "Authorization": "Bearer <the agent's fake key>" }
```

Use a tool timeout of 130 s: an approval can wait up to 125 s. Both agents' configs already do this. OpenClaw shows the tools to the model as `heimdall__<name>`; the gateway registers the bare names.

| Tool | Arguments | What the gateway does |
|---|---|---|
| `files_list` | `folder` (optional) | Lists the agent's folders, or the files in one |
| `files_read` | `path` = `<folder>/<path>` | Text or PDF; placeholders in place of personal data; Confidential text wrapped in `<<confidential:id>>` markers, which the agent should keep |
| `files_write` | `path`, `text` | Only in writable folders; asks after untrusted content, or when the session holds data above the folder's label |
| `gmail_read` | `query`, `limit` | Fixture inbox for now; cleaned and wrapped as untrusted |
| `gmail_draft` | `to`, `subject`, `body` | Saves a draft in the gateway; never asks |
| `gmail_send` | `to`, `subject`, `body` | Always asks; fills in placeholders after approval |
| `web_fetch` | `url` | GET only, public addresses only; asks after untrusted or private data |

Only the tools listed in the agent's permissions are offered to the model (`build_config` does this for both agents) and allowed by the gateway.

### `permissions.json`

`agents/manager.py` `write_permissions` writes `data/agents/<agent>/permissions.json`, which compose mounts read-only at `/config/agents`. The gateway reads it on every call, so a reopen takes effect at once.

```json
{
  "run_id": "a new random id every time the agent is opened",
  "fake_key": "sk-fake-openclaw-01",
  "provider": "gemini",
  "model": "gemini-flash-lite-latest",
  "permissions": { "folders": [...], "tools": [...], "skills": [...], "memory": false, "delegation": false }
}
```

- `run_id`: a new one starts a new session (new labels, new placeholder numbering, consent answers forgotten).
- `fake_key` must match the key the agent sends, or every call is refused. Without a readable file the agent gets no tools and no model calls (`no_permissions`).
- `permissions` is `AgentPermissions` from `core/contracts/agents.py`. Folder paths are stored resolved; the gateway finds each folder by its last path part.
- `provider`, `model`: the user's choice, written by `open_agent`. The gateway refuses model calls to any other cloud provider (`provider_not_chosen`) or another model there (`model_not_chosen`), as `project-plan.md` section 6 requires. The local model is always allowed.

### Folders

The manager mounts each allowed folder into the gateway, never into an agent, at `/data/folders/<last part of its path>`. It writes `data/gateway/compose.folders.yaml` and mounts read-only unless an agent may write. Two different folders with the same last name can't both be open; the manager refuses that. All of this is done.

### Gateway settings in `agents/gateway/compose.yaml`

| Variable | Set today | Meaning |
|---|---|---|
| `HEIMDALL_FAKE_KEYS` | yes | `agent:key` pairs; must match each agent's `FAKE_KEY` |
| `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` | yes | Real keys, from the app's key store (C's `key_service`) or `.env`. Only the gateway ever gets them; it reads them at start |
| `HEIMDALL_PROVIDER=mock` | optional, from `.env` | Scripted model, no network, for offline runs |
| `CORE_URL` | default `http://host.docker.internal:8765` | C's back end |
| `HEIMDALL_EVENTS_URL` | yes | `http://host.docker.internal:8765/api/event`: every event goes to the dashboard |
| `GMAIL_SOURCE` | default `fixture` | `live` is refused until the Gmail OAuth files are mounted |
| `OLLAMA_URL` | default as above | The local model |

Volumes: `gateway-state` (`/state`: the vault, drafts, outbox, consent answers; never mount it into an agent) and the fixture inbox at `/data/inbox`.

### Scene 4: a malicious skill

Decided (issue #5): no egress logger. OpenClaw runs with the `minimal` tool profile plus Heimdall's tools only, so a skill can't run `curl` or any other command. Its only ways out are the gateway's tools and model calls, and the key tripwire watches both (`key_theft_attempt`). The visible moment is the skill scan at install: the demo skill `weather-helper` is quarantined for reading a secrets file, sending data out and telling the agent to deceive. Forced in anyway, it got no tool calls from the agent in a live run. The demo script's line that "the attacker's screen receives only the fake key" doesn't match this; it needs rewording before the pitch.

## 3. Back end and app (C)

### Questions: `POST /api/raise`

The gateway posts JSON and waits up to 125 s. Anything but `{"decision": "approve"}` is a deny, and so is no answer or an error. Your back end's 120 s timeout answers first. This works with `backend/app.py` on main today, unchanged.

Always present: `kind` (`approval` or `consent`), `container_id` (the agent's name, `openclaw` or `hermes`, not a Docker id) and `question` (a sentence for the pop-up). The other fields depend on the case:

| Case | `kind` | Extra fields | What the pop-up should show |
|---|---|---|---|
| File write or web fetch after the agent read mail or a web page | `approval` | `tool`, `path` (file path or URL) | Who, what, where (`project-plan.md` section 5) |
| File write into a folder with a lower label than the data the agent holds | `consent` if the agent read Confidential data, else `approval` | `tool`, `path` | That the data would lose its label |
| `gmail_send` | `approval` | `tool`, `to`, `subject`, `body` | The final email with real values. The user approves exactly what is sent |
| `gmail_send` or `web_fetch` after a Confidential read | `consent` | as the two rows above | That Confidential data may be in it |
| A model call holding a Confidential file's text | `consent` | `file` (`taxes/return.txt`), `folder` (`taxes`), `provider` (`Gemini`, `Anthropic`) | "Hermes wants to send part of taxes/return.txt to Anthropic" |

- The `gmail_send` fields hold the user's real personal data. Show them in the pop-up, but don't log or store them.
- A consent answer on a model call holds for that file for the rest of the agent's run, and so does a deny, so the user isn't asked again on every model call.

### Consent answers

For `kind: consent` on a model call, the pop-up offers three answers, and `/api/response` takes `scope` with an approve:
- **Allow this file** (`scope: "once"`): this file, for the rest of the agent's run.
- **Always for this folder** (`scope: "folder"`): every file in that folder, for the rest of the run.
- **Deny**: the text is withheld for the rest of the run.

Reopening the agent starts a new run and asks again.

### Events

Every decision is one JSON object with a `kind` field. Today they go to the gateway's stdout (`docker compose logs gateway`), and they also go to `HEIMDALL_EVENTS_URL` when it's set. Events never hold keys or the real values behind placeholders. The one exception is `hidden_instruction`, which shows the hidden text found in an email or page as evidence.

| `kind` | Fields | Show it as |
|---|---|---|
| `tool_call` | `agent`, `tool`, `path`, `decision` (`allow`, `approved`, `deny`, `denied_by_user`), `rule_id`, `reason`, `label` (session label after the call), `placeholders` (counts by type); plus `hidden`, `flagged` for mail and web, and `filled` for sends | One feed line per tool call; red when `decision` is `deny` or `denied_by_user` |
| `tool_denied` | `tool`, `reason` | A call with no known key (no agent to name) |
| `hidden_instruction` | `agent`, `tool`, `rule_id`, `source` (which email or page), `where` (how it was hidden), `text`, `reason` | Scene 3's red flag: show the hidden text and where it was |
| `injection_check` | `agent`, `tool`, `verdict` (`flagged`, `not_flagged`, `not_checked`), `quote` or `reason`, `model` | The AI second opinion. `not_checked` must never be shown as "clean" |
| `model_call` | `agent`, `api_key` (always the fake key), `model`, `tools_offered` | Feed line; a line on the flow map |
| `model_forwarded` | `agent`, `url`, `model`, `status` | The call reached the provider |
| `model_blocked` | `agent` (missing for an unknown key), `path`, `rule_id`, `reason`, `findings` (kind and masked preview) | Red: `key_theft_attempt`, `secret_in_request`, `provider_not_chosen`, `model_not_chosen`, `no_permissions` |
| `model_withheld` | `agent`, `path`, `rule_id` (`consent_denied`), `files` | Scene 6: the request went out without these files |
| `consent` | `agent`, `file`, `provider`, `decision`, `scope` | The user's consent answer |
| `model_other`, `model_error`, `model_upstream_error`, `ask_failed` | `agent` and details | Diagnostics. `ask_failed` means a question didn't reach the user and counted as a deny |

Rule ids, reasons and counts come straight from the code. Don't turn them into scores or percentages (truth rules in `CLAUDE.md`).

## 4. Testing that it fits together

| Command | Checks |
|---|---|
| `uv run pytest -m "not docker"` | Firewall unit tests, plus `tests/seams/test_gateway_core.py`, which runs C's real back end in-process: approve, no answer, back end down, a consent question, and a reloaded dashboard |
| `uv run pytest` | Everything, Docker included. Needs Docker running, `GEMINI_API_KEY` in `.env`, and port 8765 free (the scene tests start C's back end there) |
| `uv run pytest tests/seams` | The four seam tests: real agents through the gateway (scenes 3, 5 and 6, and files) |

After any change to an agent config, the compose files, `backend/app.py` or `notification_service.py`, run `uv run pytest tests/seams` before merging. If a seam test breaks, tell A.

## 5. What is not done, by owner

| Plan item | Owner | State |
|---|---|---|
| Live Gmail | A | Issue #12. Needs the test account's OAuth files on the demo laptop |
| AI injection check live | A | Issue #13. Built; runs once an Anthropic key is in the gateway |
| Real Ollama on the demo laptop | B | Wired and tested against a stand-in; install Ollama and pull `llama3.2:3b` |
| Choosing the provider in the app | Everyone (UI) | `frontend/src/data/agents.ts` still sends `gemini`; scene 6 needs a way to pick `local` |
| Labels on memory notes | B and A | Decided Nov 15 to keep Hermes's own memory (with snapshots and rollback). Its notes carry no label and skip consent: a gap against `project-plan.md` section 6, items 2 and 3 |
