#!/usr/bin/env bash
# =============================================================================
# Ollqd Test Campaign Runner
#
# One command to run all tests and export evidence to artifacts/.
#
# Usage:
#   ./scripts/test-run.sh              # Run all test suites
#   ./scripts/test-run.sh --api        # Run only API tests
#   ./scripts/test-run.sh --grpc       # Run only gRPC tests
#   ./scripts/test-run.sh --e2e        # Run only Playwright E2E tests
#   ./scripts/test-run.sh --perf       # Run only perf tests
#   ./scripts/test-run.sh --no-docker  # Skip docker compose up/down
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ARTIFACTS_DIR="$PROJECT_DIR/artifacts"
TESTS_DIR="$PROJECT_DIR/tests"

# Defaults
RUN_API=false
RUN_GRPC=false
RUN_E2E=false
RUN_PERF=false
RUN_ALL=true
MANAGE_DOCKER=true

# Parse arguments
for arg in "$@"; do
  case "$arg" in
    --api)       RUN_API=true; RUN_ALL=false ;;
    --grpc)      RUN_GRPC=true; RUN_ALL=false ;;
    --e2e)       RUN_E2E=true; RUN_ALL=false ;;
    --perf)      RUN_PERF=true; RUN_ALL=false ;;
    --no-docker) MANAGE_DOCKER=false ;;
    --help|-h)
      echo "Usage: $0 [--api] [--grpc] [--e2e] [--perf] [--no-docker]"
      exit 0
      ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

if $RUN_ALL; then
  RUN_API=true
  RUN_GRPC=true
  RUN_E2E=true
  RUN_PERF=true
fi

# Export environment
export GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
export WEB_URL="${WEB_URL:-http://localhost:3000}"
export WORKER_ADDR="${WORKER_ADDR:-localhost:50051}"
export HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[test-run]${NC} $*"; }
ok()   { echo -e "${GREEN}[  OK  ]${NC} $*"; }
fail() { echo -e "${RED}[ FAIL ]${NC} $*"; }
warn() { echo -e "${YELLOW}[ WARN ]${NC} $*"; }

# Track overall status
TOTAL_SUITES=0
PASSED_SUITES=0
FAILED_SUITES=()

run_suite() {
  local name="$1"
  shift
  TOTAL_SUITES=$((TOTAL_SUITES + 1))
  log "Running: $name"
  if "$@"; then
    ok "$name"
    PASSED_SUITES=$((PASSED_SUITES + 1))
  else
    fail "$name"
    FAILED_SUITES+=("$name")
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────────────────────

log "Preparing artifacts directory..."
mkdir -p "$ARTIFACTS_DIR"/{screenshots,logs,trace,results}

# ─────────────────────────────────────────────────────────────────────────────
# Docker Compose
# ─────────────────────────────────────────────────────────────────────────────

if $MANAGE_DOCKER; then
  log "Starting Docker Compose services..."
  cd "$PROJECT_DIR"
  docker compose up -d --build --wait 2>&1 | tail -5

  log "Waiting for services to be healthy..."
  deadline=$((SECONDS + ${HEALTH_TIMEOUT}))
  while [ $SECONDS -lt $deadline ]; do
    if curl -sf "$GATEWAY_URL/api/system/health" > /dev/null 2>&1; then
      ok "Gateway is healthy"
      break
    fi
    sleep 2
  done

  if [ $SECONDS -ge $deadline ]; then
    fail "Services did not become healthy within ${HEALTH_TIMEOUT}s"
    docker compose logs > "$ARTIFACTS_DIR/logs/startup-failure.log" 2>&1
    exit 1
  fi
fi

# Collect service logs at exit
cleanup() {
  if $MANAGE_DOCKER; then
    log "Collecting service logs..."
    cd "$PROJECT_DIR"
    for svc in gateway worker web qdrant; do
      docker compose logs "$svc" > "$ARTIFACTS_DIR/logs/${svc}.log" 2>&1 || true
    done
    # Sanitize logs: remove potential secrets
    for f in "$ARTIFACTS_DIR"/logs/*.log; do
      [ -f "$f" ] && sed -i.bak -E 's/(password|secret|token|key)=\S+/\1=***REDACTED***/gi' "$f" && rm -f "${f}.bak"
    done
  fi

  # Final summary
  echo ""
  log "═══════════════════════════════════════════"
  log "  Test Campaign Summary"
  log "═══════════════════════════════════════════"
  log "  Suites run:    $TOTAL_SUITES"
  ok  "  Passed:        $PASSED_SUITES"
  if [ ${#FAILED_SUITES[@]} -gt 0 ]; then
    fail "  Failed:        ${#FAILED_SUITES[@]}"
    for s in "${FAILED_SUITES[@]}"; do
      fail "    - $s"
    done
  fi
  log "  Artifacts:     $ARTIFACTS_DIR/"
  log "═══════════════════════════════════════════"
}
trap cleanup EXIT

# ─────────────────────────────────────────────────────────────────────────────
# API Tests (pytest)
# ─────────────────────────────────────────────────────────────────────────────

if $RUN_API; then
  run_suite "API Tests" python -m pytest "$TESTS_DIR/api/" \
    -v --tb=short \
    --junitxml="$ARTIFACTS_DIR/results/api-junit.xml" \
    -o "junit_family=xunit2" \
    2>&1 | tee "$ARTIFACTS_DIR/logs/api-tests.log"
fi

# ─────────────────────────────────────────────────────────────────────────────
# gRPC Tests (pytest-asyncio)
# ─────────────────────────────────────────────────────────────────────────────

if $RUN_GRPC; then
  run_suite "gRPC Tests" python -m pytest "$TESTS_DIR/grpc/" \
    -v --tb=short \
    --junitxml="$ARTIFACTS_DIR/results/grpc-junit.xml" \
    -o "junit_family=xunit2" \
    2>&1 | tee "$ARTIFACTS_DIR/logs/grpc-tests.log"
fi

# ─────────────────────────────────────────────────────────────────────────────
# E2E Playwright Tests
# ─────────────────────────────────────────────────────────────────────────────

if $RUN_E2E; then
  E2E_DIR="$TESTS_DIR/e2e/playwright"
  if [ -f "$E2E_DIR/package.json" ]; then
    log "Installing Playwright dependencies..."
    cd "$E2E_DIR"
    npm ci --silent 2>/dev/null || npm install --silent
    npx playwright install chromium --with-deps 2>/dev/null || true
    cd "$PROJECT_DIR"

    run_suite "Playwright E2E Tests" npx --prefix "$E2E_DIR" playwright test \
      2>&1 | tee "$ARTIFACTS_DIR/logs/e2e-tests.log"
  else
    warn "Playwright tests not found at $E2E_DIR/package.json — skipping"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Performance Tests
# ─────────────────────────────────────────────────────────────────────────────

if $RUN_PERF; then
  # k6 HTTP load test
  if command -v k6 &> /dev/null; then
    run_suite "k6 HTTP Load" k6 run "$TESTS_DIR/perf/k6_http.js" \
      --env "GATEWAY_URL=$GATEWAY_URL" \
      2>&1 | tee "$ARTIFACTS_DIR/logs/k6-tests.log"
  else
    warn "k6 not installed — skipping HTTP load tests"
    warn "Install: brew install grafana/k6/k6"
  fi

  # WebSocket concurrency
  run_suite "WS Concurrency" python "$TESTS_DIR/perf/ws_concurrency.py" \
    --sessions 10 --timeout 60 \
    --output "$ARTIFACTS_DIR/results/ws-concurrency.json" \
    2>&1 | tee "$ARTIFACTS_DIR/logs/ws-concurrency.log"

  # Concurrent indexing
  run_suite "Concurrent Indexing" python "$TESTS_DIR/perf/indexing_concurrent.py" \
    --tasks 3 --timeout 120 \
    --output "$ARTIFACTS_DIR/results/indexing-concurrent.json" \
    2>&1 | tee "$ARTIFACTS_DIR/logs/indexing-concurrent.log"
fi
