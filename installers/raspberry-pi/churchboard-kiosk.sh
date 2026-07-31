#!/usr/bin/env bash
set -euo pipefail

URL="${CHURCHBOARD_KIOSK_URL:-http://127.0.0.1:8040/display/main}"
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:8040/api/app-info" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

BROWSER="$(command -v chromium || command -v chromium-browser)"
exec "$BROWSER" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --check-for-update-interval=31536000 \
  "$URL"
