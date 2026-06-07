#!/usr/bin/env bash
# Delegates to dev/tools.sh — all install/tests run in Docker.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/dev/tools.sh" "$@"
