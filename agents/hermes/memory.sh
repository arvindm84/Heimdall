#!/bin/sh
# heimdall-memory snapshot | list | rollback <id>
# Live memory: /heimdall/memory/live. Snapshots: /heimdall/memory/snapshots/<UTC time>.
set -e
M=/heimdall/memory
KEEP=30
case "$1" in
  snapshot)
    [ -n "$(ls -A "$M/live" 2>/dev/null)" ] || exit 0
    latest=$(ls "$M/snapshots" | tail -n 1)
    if [ -n "$latest" ] && diff -rq "$M/live" "$M/snapshots/$latest" >/dev/null 2>&1; then exit 0; fi
    id=$(date -u +%Y%m%dT%H%M%SZ)
    [ -e "$M/snapshots/$id" ] && exit 0
    cp -r "$M/live" "$M/snapshots/$id"
    ls "$M/snapshots" | head -n "-$KEEP" | while read -r old; do rm -rf "$M/snapshots/$old"; done
    echo "$id"
    ;;
  list)
    ls "$M/snapshots"
    ;;
  rollback)
    [ -n "$2" ] && [ -d "$M/snapshots/$2" ] || { echo "no snapshot named '$2'" >&2; exit 1; }
    "$0" snapshot >/dev/null
    find "$M/live" -mindepth 1 -delete
    cp -r "$M/snapshots/$2/." "$M/live/"
    echo "rolled back to $2 (applies from the next chat)"
    ;;
  *)
    echo "usage: heimdall-memory snapshot | list | rollback <id>" >&2
    exit 2
    ;;
esac
