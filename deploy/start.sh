#!/bin/sh
# Container entrypoint: generate the daily page, refresh it every
# REFRESH_HOURS, and serve it on PORT.
set -u

PORT="${PORT:-8080}"
REFRESH_HOURS="${REFRESH_HOURS:-6}"
SITE_DIR="${SITE_DIR:-site}"

mkdir -p "$SITE_DIR"

regen() {
    surfwa web --days 3 --out "$SITE_DIR" \
        || echo "surfwa web faalde; vorige pagina blijft staan" >&2
}

regen
if [ ! -f "$SITE_DIR/index.html" ]; then
    printf '<!doctype html><html lang="nl"><title>surfwa</title><p>Eerste build is nog niet gelukt; volgende poging over %s uur.</p></html>' "$REFRESH_HOURS" \
        > "$SITE_DIR/index.html"
fi

(
    while :; do
        sleep $((REFRESH_HOURS * 3600))
        regen
    done
) &

exec python -m http.server "$PORT" -d "$SITE_DIR"
