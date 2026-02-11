"""Shared pytest configuration and fixtures for all test suites."""

import json
import os
import time
from pathlib import Path

import pytest
import requests


# ---------------------------------------------------------------------------
# Skip gRPC tests when grpcio is not installed
# ---------------------------------------------------------------------------
try:
    import grpc  # noqa: F401
except ImportError:
    collect_ignore_glob = ["grpc/*"]

# ---------------------------------------------------------------------------
# Environment defaults
# ---------------------------------------------------------------------------
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
WORKER_ADDR = os.getenv("WORKER_ADDR", "localhost:50051")
WEB_URL = os.getenv("WEB_URL", "http://localhost:3000")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

FIXTURES_DIR = Path(__file__).parent / "fixtures"
ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts"

# Test collection name — unique per run to avoid collisions
TEST_COLLECTION = os.getenv("TEST_COLLECTION", "test_ollqd_suite")

# Timeout for service readiness (seconds)
HEALTH_TIMEOUT = int(os.getenv("HEALTH_TIMEOUT", "120"))


# ---------------------------------------------------------------------------
# Session-scoped: wait for services
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def ensure_artifacts_dir():
    """Create artifacts directories for test outputs."""
    for subdir in ("screenshots", "logs", "trace", "results"):
        (ARTIFACTS_DIR / subdir).mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture(scope="session")
def gateway_url():
    return GATEWAY_URL


@pytest.fixture(scope="session")
def worker_addr():
    return WORKER_ADDR


@pytest.fixture(scope="session")
def web_url():
    return WEB_URL


@pytest.fixture(scope="session")
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def artifacts_dir():
    return ARTIFACTS_DIR


@pytest.fixture(scope="session")
def wait_for_gateway(gateway_url):
    """Block until the gateway health endpoint responds."""
    deadline = time.time() + HEALTH_TIMEOUT
    last_err = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{gateway_url}/api/system/health", timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception as exc:
            last_err = exc
        time.sleep(2)
    pytest.fail(f"Gateway not ready after {HEALTH_TIMEOUT}s: {last_err}")


@pytest.fixture(scope="session")
def wait_for_qdrant(gateway_url):
    """Block until Qdrant is reachable through the gateway proxy."""
    deadline = time.time() + HEALTH_TIMEOUT
    while time.time() < deadline:
        try:
            r = requests.get(f"{gateway_url}/api/qdrant/collections", timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    pytest.fail(f"Qdrant not reachable after {HEALTH_TIMEOUT}s")


# ---------------------------------------------------------------------------
# Collection management
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def test_collection_name():
    """Unique collection name for this test run."""
    return f"{TEST_COLLECTION}_{int(time.time())}"


@pytest.fixture()
def temp_collection(gateway_url, wait_for_qdrant):
    """Create a temporary collection for a single test, delete after."""
    name = f"tmp_{int(time.time() * 1000)}"
    # Create via Qdrant proxy
    r = requests.put(
        f"{gateway_url}/api/qdrant/collections/{name}",
        json={"vectors": {"size": 384, "distance": "Cosine"}},
        timeout=10,
    )
    assert r.status_code in (200, 201), f"Failed to create collection: {r.text}"
    yield name
    # Cleanup
    requests.delete(f"{gateway_url}/api/qdrant/collections/{name}", timeout=10)


# ---------------------------------------------------------------------------
# PII fixture data
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def pii_samples():
    """Load PII test samples from fixtures."""
    with open(FIXTURES_DIR / "pii" / "samples.json") as f:
        return json.load(f)["samples"]


# ---------------------------------------------------------------------------
# Result recording
# ---------------------------------------------------------------------------
class TestResultRecorder:
    """Accumulates test results for the artifacts/results.json bundle."""

    def __init__(self):
        self.results = []

    def record(self, name: str, passed: bool, duration_ms: float, details: str = ""):
        self.results.append(
            {
                "test": name,
                "passed": passed,
                "duration_ms": round(duration_ms, 2),
                "details": details,
            }
        )

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(
                {
                    "total": len(self.results),
                    "passed": sum(1 for r in self.results if r["passed"]),
                    "failed": sum(1 for r in self.results if not r["passed"]),
                    "results": self.results,
                },
                f,
                indent=2,
            )


@pytest.fixture(scope="session")
def result_recorder():
    rec = TestResultRecorder()
    yield rec
    rec.save(ARTIFACTS_DIR / "results" / "results.json")
