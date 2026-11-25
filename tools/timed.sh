#!/usr/bin/env bash
set -u
label="$1"; shift
root="$(cd "$(dirname "$0")/.." && pwd)"
log="$root/BUILD_TIME.csv"
[ -f "$log" ] || echo "label,start_utc,seconds,exit_code,command" > "$log"
start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
s=$(date +%s)
"$@"
code=$?
e=$(date +%s)
printf '%s,%s,%d,%d,"%s"\n' "$label" "$start" "$((e-s))" "$code" "$*" >> "$log"
exit $code
