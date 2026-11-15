# Firewall → Agents: changes needed in B's files

From A (firewall). These files are yours (`compose.yaml`, `images/openclaw/`, `core/runtime/`), so I haven't touched them. Items 1 and 2 are needed now. Items 3 and 4 are needed before the firewall's Step 1 (real files and permissions) can run end to end.

The real gateway is on branch `firewall-skeleton`: `core/gateway.py`, image `images/gateway/Dockerfile`. It serves the same URLs as your fake gateway (`/mcp` and `/model/*` on port 8080), so nothing else in OpenClaw's config changes.

## 1. Send the fake key on MCP calls (needed now)

In `images/openclaw/openclaw.json`, add `headers` to the `heimdall` MCP server:

```json
"mcp": {
  "servers": {
    "heimdall": {
      "url": "http://gateway:8080/mcp",
      "transport": "streamable-http",
      "requestTimeoutMs": 130000,
      "headers": { "Authorization": "Bearer ${HEIMDALL_FAKE_KEY}" }
    }
  }
}
```

**Why:** model calls already carry the fake key, but MCP tool calls carry nothing, so the gateway can't tell which agent called. From Step 1 the gateway denies tool calls without a known key.

**Tested** (Nov 14, OpenClaw 2026.9.3): with this change, the gateway logged `{"kind": "tool_call", "agent": "openclaw", ...}`; without it, `"agent": "unknown"`. `${HEIMDALL_FAKE_KEY}` is filled in inside `headers` the same way it is for `apiKey`. OpenClaw's own docs list the field (`/app/docs/cli/mcp.md`, streamable-http table).

## 2. Point compose at the real gateway (needed now)

In `compose.yaml`:

```yaml
  gateway:
    build:
      context: .
      dockerfile: images/gateway/Dockerfile
```

The build context is the repo root, because the image needs `core/` and `uv.lock`. A root `.dockerignore` (on `firewall-skeleton`) keeps `.env` and `data/` out of the build. Keep `env_file: .env`. With no key in `.env`, the gateway answers model calls with a scripted mock, just like your fake gateway.

**Tested:** your `tests/runtime` suite (all 6 tests, including the 4 Docker tests) passes against the real gateway. `images/fake-gateway/` can go once this is merged.

## 3. Tell the gateway each agent's permissions (before firewall Step 1)

Right now `manager.open_agent` writes only `data/agents/<agent>/openclaw.json`, so the gateway never learns what the agent may do. Hiding tools in OpenClaw isn't enough on its own; the gateway has to enforce the same list.

- In `open_agent`, also write `data/agents/<agent>/permissions.json`:
  ```json
  { "run_id": "<new random id each open>", "fake_key": "sk-fake-openclaw-01", "permissions": { "folders": [...], "tools": [...] } }
  ```
  `permissions` is `AgentPermissions.model_dump()` from `core/contracts/agents.py`. A new `run_id` tells the gateway to start a fresh session (labels and placeholders reset), because `up -d gateway` doesn't restart the gateway when the agent restarts.
- Mount it into the gateway, read-only: `./data/agents:/config/agents:ro`.

## 4. Mount user folders into the gateway, never into agents (before firewall Step 1)

- For each `FolderAccess` in the permissions, mount the host folder into the gateway at `/data/folders/<folder name>`, read-only unless `write` is true.
- Agent containers get no user folders. They read files only through the gateway's `files_*` tools.
- Use the same `<folder name>` that `permissions.json` uses, so the gateway can match the two. If two folders share a base name, tell me and we'll pick a naming rule.

## Later (no action yet)

- Firewall Step 4 (Gmail): mount `data/credentials.json` and `data/token.json` read-only into the gateway.
- Scene 4 (fake key stolen), with D: agents have no internet now, so a skill's `curl attacker.example` just fails and nothing shows on the dashboard. The firewall will catch the fake key when it leaves through a gateway tool or a model request. If the demo also needs a visible "blocked" moment for raw network calls, we could add a small logger on `gateway:8081` that refuses every connection and logs the host. That would need `HTTPS_PROXY=http://gateway:8081` in the agent image. Let's decide together.

## How to check

```
docker compose up -d --build gateway
uv run pytest -m docker tests/runtime
docker compose logs --no-log-prefix gateway | grep '"kind": "tool_call"'
```
After item 1, the `tool_call` line should show `"agent": "openclaw"`.
