#!/bin/sh
set -e
mkdir -p ~/.openclaw
cp /config/openclaw.json ~/.openclaw/openclaw.json
chmod 600 ~/.openclaw/openclaw.json
node /app/openclaw.mjs gateway &
until curl -fs http://127.0.0.1:18789/healthz >/dev/null; do sleep 1; done
exec ttyd --writable --port 7681 --credential "heimdall:${HEIMDALL_CHAT_TOKEN}" \
  node /app/openclaw.mjs tui
