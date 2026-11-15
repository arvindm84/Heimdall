#!/bin/sh
set -e
cp /config/config.yaml /opt/data/config.yaml
cp /opt/heimdall/SOUL.md /opt/data/SOUL.md
mkdir -p /opt/data/logs
rm -f /opt/data/logs/gateway.log
hermes gateway run --quiet >/dev/null 2>&1 &
until grep -q "Gateway housekeeping started" /opt/data/logs/gateway.log 2>/dev/null; do sleep 1; done
exec ttyd --writable --port 7681 --credential "heimdall:${HEIMDALL_CHAT_TOKEN}" hermes
