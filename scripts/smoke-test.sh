#!/usr/bin/env bash
#
# Smoke test against a RUNNING WeatherWatch instance.
#
#   scripts/smoke-test.sh http://localhost:8000
#   scripts/smoke-test.sh https://weatherwatch-xxxx.onrender.com
#
# Optional environment:
#   EXPECTED_COMMIT  wait until /health reports this commit (used by CD to make
#                    sure the NEW deploy is live, not the old one)
#   HEALTH_RETRIES   attempts for /health (default 12; cold start on Render
#                    free tier takes up to a minute)
#   BACKOFF_SECONDS  linear backoff step (default 5)
#
# Exits non-zero on the first failed check; prints "SMOKE TEST PASSED" only
# when every check succeeded. Dependencies: bash, curl, grep.

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <base-url>" >&2
  exit 2
fi

BASE_URL="${1%/}"
HEALTH_RETRIES="${HEALTH_RETRIES:-12}"
BACKOFF_SECONDS="${BACKOFF_SECONDS:-5}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-}"
CURL_OPTS=(--silent --show-error --connect-timeout 10 --max-time 60)

STATUS=""
BODY=""

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# request PATH -> sets STATUS and BODY
request() {
  local raw
  raw="$(curl "${CURL_OPTS[@]}" -w $'\n%{http_code}' "${BASE_URL}$1")" || return 1
  STATUS="${raw##*$'\n'}"
  BODY="${raw%$'\n'*}"
}

expect() {
  local path="$1" status="$2" pattern="$3"
  request "$path" || fail "GET ${path} failed (connection)"
  [ "$STATUS" = "$status" ] || fail "GET ${path} returned ${STATUS}, expected ${status}: ${BODY}"
  printf '%s' "$BODY" | grep -q -- "$pattern" || fail "GET ${path} body does not match ${pattern}: ${BODY}"
  echo "  OK  ${path} -> ${STATUS}"
}

echo "Target: ${BASE_URL}"
echo "== 1/6 /health (tolerates cold start${EXPECTED_COMMIT:+, waits for commit ${EXPECTED_COMMIT:0:12}}) =="
attempt=1
while :; do
  if request /health && [ "$STATUS" = "200" ] && printf '%s' "$BODY" | grep -q '"status":"ok"'; then
    if [ -z "$EXPECTED_COMMIT" ] || printf '%s' "$BODY" | grep -q "\"commit\":\"${EXPECTED_COMMIT}\""; then
      echo "  OK  /health (attempt ${attempt}): ${BODY}"
      break
    fi
    echo "  live, but still the previous deploy: ${BODY}"
  fi
  [ "$attempt" -lt "$HEALTH_RETRIES" ] || fail "/health not as expected after ${HEALTH_RETRIES} attempts"
  wait_for=$(( BACKOFF_SECONDS * attempt ))
  echo "  attempt ${attempt}/${HEALTH_RETRIES} not yet, waiting ${wait_for}s..."
  sleep "$wait_for"
  attempt=$(( attempt + 1 ))
done

echo "== 2/6 /ready =="
expect /ready 200 '"status":"ready"'

echo "== 3/6 /api/locations =="
expect /api/locations 200 '"slug":"chur"'

echo "== 4/6 /api/weather and /api/forecast =="
expect "/api/weather?city=chur" 200 '"temperature_c"'
expect "/api/forecast?city=chur&days=3" 200 '"days"'

echo "== 5/6 input validation =="
expect "/api/weather?city=atlantis" 404 '"unknown city"'
expect "/api/forecast?days=99" 400 '"error"'

echo "== 6/6 /metrics =="
expect /metrics 200 'weatherwatch_info'

echo
echo "SMOKE TEST PASSED"
