#!/bin/sh
set -e
until [ -f /certs/mitmproxy-ca-cert.pem ]; do sleep 1; done
mkdir -p ~/.openclaw/workspace
cp /opt/heimdall/workspace/* ~/.openclaw/workspace/
cp /config/config.json ~/.openclaw/openclaw.json
chmod 600 ~/.openclaw/openclaw.json
node /app/openclaw.mjs gateway &
until curl -fs http://127.0.0.1:18789/healthz >/dev/null; do sleep 1; done
exec ttyd --writable --port 7681 --credential "heimdall:${HEIMDALL_CHAT_TOKEN}" \
  node /app/openclaw.mjs tui
