#!/usr/bin/env sh
set -eu
if [ "${SENTINEL_FETCH_ON_START:-1}" = "1" ]; then
    python -m sentinel fetch
fi
exec "$@"
