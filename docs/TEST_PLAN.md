# Ollqd Test Plan

## Overview

This document describes the test campaign for the Ollqd self-hosted RAG platform.
The suite covers 4 layers: UI (Playwright), HTTP API (pytest), gRPC integration (pytest-asyncio),
and performance/concurrency testing (k6 + custom scripts).

## Environments

| Environment | Gateway | Web | Worker | Ollama | Qdrant |
|-------------|---------|-----|--------|--------|--------|
| Local dev   | localhost:8000 | localhost:3000 | localhost:50051 | localhost:11434 | localhost:6333 |
| Docker Compose | gateway:8000 | web:80 | worker:50051 | ollama:11434 | qdrant:6333 |
| CI (GitHub Actions) | localhost:8000 | localhost:3000 | localhost:50051 | localhost:11434 | localhost:6333 |

All tests use environment variables for service URLs (`GATEWAY_URL`, `WEB_URL`, `WORKER_ADDR`).

## Prerequisites

- Docker and Docker Compose
- Python 3.12+ with pip
- Node.js 20+ with npm
- k6 (optional, for HTTP load tests)

Install test dependencies:
```bash
pip install pytest pytest-asyncio requests websockets grpcio grpcio-tools protobuf
cd tests/e2e/playwright && npm install && npx playwright install chromium
```

## Running Tests

### All tests (one command)
```bash
./scripts/test-run.sh
```

### Individual suites
```bash
./scripts/test-run.sh --api        # API tests only
./scripts/test-run.sh --grpc       # gRPC tests only
./scripts/test-run.sh --e2e        # Playwright E2E only
./scripts/test-run.sh --perf       # Performance tests only
./scripts/test-run.sh --no-docker  # Skip docker compose up/down (services already running)
```

### Direct pytest
```bash
python -m pytest tests/api/ -v
python -m pytest tests/grpc/ -v
python -m pytest tests/api/test_health.py -v  # Single file
```

## Artifacts

After a test run, `artifacts/` contains:

| Path | Contents |
|------|----------|
| `artifacts/results/api-junit.xml` | API test results (JUnit XML) |
| `artifacts/results/grpc-junit.xml` | gRPC test results (JUnit XML) |
| `artifacts/results/e2e-results.json` | Playwright results (JSON) |
| `artifacts/results/results.json` | Aggregated pass/fail summary |
| `artifacts/results/k6-summary.json` | k6 load test metrics |
| `artifacts/results/ws-concurrency.json` | WebSocket concurrency report |
| `artifacts/results/indexing-concurrent.json` | Concurrent indexing report |
| `artifacts/screenshots/` | Playwright failure screenshots |
| `artifacts/trace/` | Playwright failure traces |
| `artifacts/logs/` | Service logs (gateway, worker, qdrant) + test output |

## Coverage Matrix

### Requirement → Test Mapping

| # | Requirement | Test Suite | Test File(s) | Markers |
|---|------------|------------|--------------|---------|
| 1 | Health & Smoke | API | `test_health.py` | — |
| 2 | Dashboard UI | E2E | `dashboard.spec.ts` | — |
| 3 | Collections CRUD | API, E2E | `test_collections.py`, `collections.spec.ts` | — |
| 4 | Indexing (codebase) | API, gRPC | `test_indexing.py`, `test_indexing_service.py` | `requires_ollama` |
| 5 | Indexing (documents) | API, gRPC | `test_indexing.py`, `test_indexing_service.py` | `requires_ollama` |
| 6 | Indexing (images) | API, gRPC | `test_indexing.py`, `test_indexing_service.py` | `requires_ollama` |
| 7 | Indexing (uploads) | API | `test_upload.py` | — |
| 8 | Indexing (SMB) | API | `test_indexing.py` (skipped if no SMB) | `requires_smb` |
| 9 | Task cancel | API, gRPC | `test_indexing.py`, `test_indexing_service.py` | `requires_ollama` |
| 10 | Incremental indexing | API, gRPC | `test_indexing.py`, `test_indexing_service.py` | `requires_ollama` |
| 11 | Search | API, gRPC | `test_search.py`, `test_search_service.py` | `requires_indexed` |
| 12 | Chat (WebSocket) | API, E2E | `test_websocket.py`, `chat.spec.ts` | `requires_ollama` |
| 13 | Chat streaming events | gRPC | `test_chat_service.py` | `requires_ollama` |
| 14 | PII masking toggle | API, gRPC | `test_pii.py`, `test_pii_service.py` | — |
| 15 | PII stream unmasking | gRPC | `test_chat_service.py` | `requires_ollama` |
| 16 | PII never reaches LLM | gRPC | `test_chat_service.py` | `requires_ollama` |
| 17 | Config get/update | API, gRPC, E2E | `test_config.py`, `test_config_service.py`, `settings.spec.ts` | — |
| 18 | Config persistence | API | `test_config.py` | — |
| 19 | Config reset | API, gRPC | `test_config.py`, `test_config_service.py` | — |
| 20 | Model list | API, E2E | `test_models.py`, `models.spec.ts` | — |
| 21 | Model pull streaming | API | `test_models.py` | — |
| 22 | Model delete | API | `test_models.py` | — |
| 23 | Embedding info/test | API, gRPC | `test_config.py`, `test_embedding_service.py` | `requires_ollama` |
| 24 | Visualization overview | API, gRPC, E2E | `test_visualization.py`, `test_visualization_service.py`, `visualize.spec.ts` | `requires_indexed` |
| 25 | Visualization file tree | API, gRPC | `test_visualization.py`, `test_visualization_service.py` | `requires_indexed` |
| 26 | Visualization vectors | API, gRPC | `test_visualization.py`, `test_visualization_service.py` | `requires_indexed` |
| 27 | CORS headers | API | `test_security.py` | — |
| 28 | SSRF prevention | API | `test_security.py` | — |
| 29 | Path traversal | API | `test_security.py`, `test_upload.py` | — |
| 30 | Upload size limits | API | `test_security.py`, `test_upload.py` | — |
| 31 | Header leakage | API, E2E | `test_security.py`, `security.spec.ts` | — |
| 32 | Concurrent chat | Perf | `ws_concurrency.py` | — |
| 33 | Concurrent indexing | Perf | `indexing_concurrent.py` | — |
| 34 | HTTP load | Perf | `k6_http.js` | — |
| 35 | SMB connect/browse | API, E2E | `test_indexing.py`, `smb.spec.ts` | `requires_smb` |
| 36 | Settings UI | E2E | `settings.spec.ts` | — |
| 37 | Indexing UI | E2E | `indexing.spec.ts` | — |

### Test Markers

| Marker | Meaning | Skip Condition |
|--------|---------|----------------|
| `requires_ollama` | Needs Ollama with a model loaded | Ollama not reachable or no models |
| `requires_indexed` | Needs pre-indexed fixtures in Qdrant | No indexed data in test collection |
| `requires_smb` | Needs SMB share configuration | `SMB_SERVER` env var not set |

## Interpreting Results

### Pass criteria
- **API tests**: All tests pass (except skipped markers)
- **gRPC tests**: All tests pass (except skipped markers)
- **E2E tests**: All tests pass; no unexpected console errors
- **Perf tests**: p95 latency < 2s; error rate < 10%; no deadlocks

### Common failure patterns

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Health test fails | Services not started | Run `docker compose up -d` |
| Indexing tests skip | Ollama not available or no model | Pull a model: `docker compose exec ollama ollama pull qwen3-embedding:0.6b` |
| PII tests fail | spaCy model not loaded | Worker auto-downloads on first use; check worker logs |
| E2E tests timeout | SPA not loading | Check web container logs, nginx config |
| WS concurrency fails | Gateway WebSocket upgrade issue | Check gateway logs for upgrade errors |

## Fixtures

| Directory | Contents | Purpose |
|-----------|----------|---------|
| `fixtures/codebase/` | Go, Python, TypeScript, JS, SQL, YAML files | Codebase indexing with known symbols |
| `fixtures/docs/` | Markdown, plain text files | Document indexing with known sentences |
| `fixtures/images/` | 4 minimal PNG images (solid colors) | Image indexing validation |
| `fixtures/pii/` | JSON samples + text document with PII | PII masking validation |

## CI Integration

GitHub Actions workflow at `.github/workflows/test.yml`:
1. Build and start Docker Compose
2. Wait for health probes
3. Run all test suites (continue-on-error per suite)
4. Collect service logs
5. Upload `artifacts/` bundle
6. Tear down services
