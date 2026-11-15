#!/bin/sh
set -e
cp /config/config.json /opt/data/config.yaml
cp /opt/heimdall/SOUL.md /opt/data/SOUL.md
mkdir -p /opt/data/logs /heimdall/memory/live /heimdall/memory/snapshots
# Memory lives on the hermes-memory volume; Hermes reads it from /opt/data/memories.
rm -rf /opt/data/memories
ln -s /heimdall/memory/live /opt/data/memories
# Snapshot whenever memory changed (checked every 15s; no-op when unchanged).
(while true; do heimdall-memory snapshot >/dev/null 2>&1 || true; sleep 15; done) &
rm -f /opt/data/logs/gateway.log
hermes gateway run --quiet >/dev/null 2>&1 &
until grep -q "Gateway housekeeping started" /opt/data/logs/gateway.log 2>/dev/null; do sleep 1; done
exec ttyd --writable --port 7681 --credential "heimdall:${HEIMDALL_CHAT_TOKEN}" \
  sh -c 'hermes; status=$?; heimdall-memory snapshot >/dev/null 2>&1 || true; exit $status'
