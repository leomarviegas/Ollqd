"""API-specific pytest fixtures for black-box HTTP tests against the Go gateway."""

import time

import pytest
import requests


class APIClient:
    """Thin wrapper around requests.Session that prepends the gateway base URL."""

    def __init__(self, session: requests.Session, base_url: str):
        self.session = session
        self.base_url = base_url

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.session.get(f"{self.base_url}{path}", **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        return self.session.post(f"{self.base_url}{path}", **kwargs)

    def put(self, path: str, **kwargs) -> requests.Response:
        return self.session.put(f"{self.base_url}{path}", **kwargs)

    def delete(self, path: str, **kwargs) -> requests.Response:
        return self.session.delete(f"{self.base_url}{path}", **kwargs)

    def options(self, path: str, **kwargs) -> requests.Response:
        return self.session.options(f"{self.base_url}{path}", **kwargs)

    def patch(self, path: str, **kwargs) -> requests.Response:
        return self.session.patch(f"{self.base_url}{path}", **kwargs)


@pytest.fixture(scope="session")
def api(gateway_url, wait_for_gateway):
    """Return an APIClient configured with a requests.Session and the gateway URL."""
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    client = APIClient(session, gateway_url)
    yield client
    session.close()


@pytest.fixture(scope="session")
def ollama_available(gateway_url):
    """Return True if Ollama is reachable through the gateway, False otherwise."""
    try:
        r = requests.get(f"{gateway_url}/api/system/health", timeout=5)
        data = r.json()
        return data.get("ollama", {}).get("status") == "ok"
    except Exception:
        return False


@pytest.fixture(scope="session")
def worker_available(gateway_url):
    """Return True if the gRPC worker is reachable (config endpoint responds), False otherwise."""
    try:
        r = requests.get(f"{gateway_url}/api/system/config", timeout=5)
        # 502/503 means worker is down
        return r.status_code == 200
    except Exception:
        return False


def poll_task_until_terminal(
    api_client: APIClient,
    task_id: str,
    timeout: float = 120.0,
    poll_interval: float = 1.0,
) -> dict:
    """Poll GET /api/rag/tasks/{task_id} until the task reaches a terminal state.

    Returns the final task JSON dict. Raises TimeoutError if the task does not
    complete within the given timeout.
    """
    terminal_states = {"completed", "failed", "cancelled"}
    deadline = time.time() + timeout

    while time.time() < deadline:
        r = api_client.get(f"/api/rag/tasks/{task_id}", timeout=10)
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        if status in terminal_states:
            return data
        time.sleep(poll_interval)

    raise TimeoutError(
        f"Task {task_id} did not reach terminal state within {timeout}s"
    )


# ------------------------------------------------------------------
# Custom markers
# ------------------------------------------------------------------

def pytest_configure(config):
    """Register custom markers to avoid warnings."""
    config.addinivalue_line(
        "markers",
        "requires_indexed: mark test as requiring pre-indexed content",
    )
    config.addinivalue_line(
        "markers",
        "requires_ollama: mark test as requiring a running Ollama instance",
    )
    config.addinivalue_line(
        "markers",
        "requires_worker: mark test as requiring the gRPC worker",
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests with requires_indexed marker (no pre-indexed data by default)."""
    skip_indexed = pytest.mark.skip(reason="No pre-indexed data in test collection")
    for item in items:
        if "requires_indexed" in item.keywords:
            item.add_marker(skip_indexed)
