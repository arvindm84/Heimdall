# Firewall → Agents: status

From A (firewall). Nothing is waiting on B right now.

## Done

| Item | Who | Where |
|---|---|---|
| Fake key sent on MCP calls | B | `agents/openclaw/config.json`, `agents/hermes/config.json` |
| `permissions.json` with a fresh `run_id`, mounted at `/config/agents` | B | `agents/manager.py`, `agents/gateway/compose.yaml` |
| User folders mounted into the gateway only | B | `agents/manager.py` `gateway_folder_mounts` |
| `label` on `FolderAccess` | B | `core/contracts/agents.py` |
| Switch to the real gateway | A, with the user's OK | `agents/gateway/compose.yaml` now builds `images/gateway/Dockerfile`; the stand-in `agents/gateway/server.py` and `Dockerfile` were removed |

**Tested** (Nov 14): `uv run pytest` passed all 53 tests. That covers your `agents/` tests, Docker included, for both OpenClaw and Hermes with a real `GEMINI_API_KEY`, plus the firewall's tests. The gateway logs name both agents, and the real key does not appear in them.

What changed for you with the real gateway:
- Same URLs, port and log lines as your stand-in.
- `HEIMDALL_PROVIDER=mock` in `.env` gives a scripted model with no key, for offline runs.
- Tool results are sent once, without the SDK's extra JSON copy.

## Firewall Step 1 (what changed for you)

- `files_list`, `files_read` and `files_write` now work on the folders you mount, with paths written as `<folder>/<path>`. A call outside the agent's permissions is denied, but it still shows as a `tool_call` event (with `"decision": "deny"`), so `check_sealed_and_routed` keeps working.
- Done on the firewall side: `write_permissions` in `agents/manager.py` now stores each folder's resolved path, whose last part is the mount name the gateway looks for. Before, a path typed as `.` or `~/docs` couldn't be matched. `agents/test_manager.py` has a test for it, and the existing assertion now expects the resolved path.
- New seam test `tests/seams/test_agent_gateway.py` (ours together): it opens OpenClaw with a made-up folder and checks reads, listings and refusals through the real containers.

## Gateway state volume

- Done on the firewall side: `agents/gateway/compose.yaml` now has a named volume, `gateway-state`, mounted at `/state` in the gateway only. It holds the placeholder vault, which has real personal data, so never mount it into an agent. `docker compose down -v` wipes it.

- Also on the firewall side (Step 4): `agents/gateway/compose.yaml` mounts the made-up inbox `tests/firewall/fixtures/inbox` read-only at `/data/inbox`, for `gmail_read` in fixture mode. It moves to D's `attacks/` once the demo attack email lives there.

## Firewall Steps 5 and 6 (what changed for you)

- New tools `gmail_draft` and `gmail_send`. List them in `AgentPermissions.tools` like any other tool; your config builders already pass them through (tested live with OpenClaw).
- Text that `files_read` returns from a Confidential folder now comes wrapped in `<<confidential:id>> ... <</confidential:id>>`. The agent should keep it as is. On calls to a cloud model, the user is asked once per file, and a denied file's text is replaced with `[withheld by Heimdall: Confidential content, consent denied]`.

## Waiting on B: the chosen provider (one line)

The gateway now refuses model calls to a cloud provider the user didn't choose (`provider_not_chosen`), but only when `permissions.json` says which one. In `agents/manager.py`, pass `provider` into `write_permissions` and add it to the file: `"provider": provider` next to `"run_id"`. The values are the keys of `PROVIDERS` (`gemini`, `anthropic`, later `local`). Calls to the local model are always allowed. Without the field nothing changes.

## Later, when C has an events endpoint

Set `HEIMDALL_EVENTS_URL` in `agents/gateway/compose.yaml` to C's endpoint (for example `http://host.docker.internal:5000/event`). The gateway then posts every event there as well as printing it.

## Waiting on B: the local model (scene 6, second half)

The gateway side is done and tested with a fake Ollama: any model call under `/model/local/` goes to Ollama on the host (`OLLAMA_URL`, default `http://host.docker.internal:11434/v1/chat/completions`), is still scanned for keys, and never asks for consent. To use it:

1. `agents/manager.py`: add a provider, for example `PROVIDERS["local"] = "llama3.2:3b"` (any model pulled into Ollama).
2. `agents/openclaw/agent.py`: for `local`, set the `heimdall` provider's `baseUrl` to `http://gateway:8080/model/local` and `api` to `openai-completions`. Hermes: the same base URL with its OpenAI-style client.
3. Ollama running on the host with that model pulled (`ollama pull llama3.2:3b`). It isn't installed on A's laptop, so this part hasn't been run end to end.

## Later

- Firewall Step 4 (Gmail): mount `data/credentials.json` and `data/token.json` read-only into the gateway.
- Scene 4 (fake key stolen), with D: agents have no internet, so a raw `curl` from a skill fails with no event. Decide whether the demo needs an egress logger on `gateway:8081`.
