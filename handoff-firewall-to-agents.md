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

## Coming in firewall Step 1 (heads-up)

- `files_read` and friends will read real files from the folders you mount, instead of returning canned text. A call outside the agent's permissions is denied, but it still shows as a `tool_call` event (with `"decision": "deny"`). So `check_sealed_and_routed`, which looks for any `files_read` call, keeps working.
- The gateway needs to know which mount each folder in `permissions.json` is. Step 1 changes `write_permissions` to store the resolved folder path, which is what the mount name comes from. The firewall side will make that change and run your tests.

## Later

- Firewall Step 4 (Gmail): mount `data/credentials.json` and `data/token.json` read-only into the gateway.
- Scene 4 (fake key stolen), with D: agents have no internet, so a raw `curl` from a skill fails with no event. Decide whether the demo needs an egress logger on `gateway:8081`.
