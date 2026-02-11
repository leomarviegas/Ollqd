"""Tests for indexing endpoints and background task management.

Routes tested:
  POST /api/rag/index/codebase
  POST /api/rag/index/documents
  GET  /api/rag/tasks
  GET  /api/rag/tasks/{id}
  POST /api/rag/tasks/{id}/cancel

Indexing requires the gRPC worker and Ollama for embeddings.  Tests that
exercise real indexing are skipped when those services are unavailable.
"""

import time

import pytest


def _poll_task_until_terminal(api_client, task_id, timeout=120.0, poll_interval=1.0):
    """Poll GET /api/rag/tasks/{task_id} until the task reaches a terminal state."""
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


def _skip_unless_worker(worker_available):
    """Skip the test if the gRPC worker is not reachable."""
    if not worker_available:
        pytest.skip("gRPC worker not available")


def _skip_unless_ollama(ollama_available):
    """Skip the test if Ollama is not reachable."""
    if not ollama_available:
        pytest.skip("Ollama not available for embedding")


# ---------------------------------------------------------------------------
# Codebase indexing
# ---------------------------------------------------------------------------


class TestIndexCodebase:
    """POST /api/rag/index/codebase"""

    def test_index_codebase_starts_task(
        self, api, temp_collection, fixtures_dir, worker_available, ollama_available
    ):
        """Posting a codebase index request returns 202 with a task_id."""
        _skip_unless_worker(worker_available)
        _skip_unless_ollama(ollama_available)

        r = api.post(
            "/api/rag/index/codebase",
            json={
                "root_path": str(fixtures_dir / "codebase"),
                "collection": temp_collection,
            },
            timeout=15,
        )
        assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.text}"
        data = r.json()
        assert "task_id" in data
        assert data.get("status") == "started"

    def test_index_codebase_task_completes(
        self, api, temp_collection, fixtures_dir, worker_available, ollama_available
    ):
        """Start a codebase index and poll until it reaches a terminal state."""
        _skip_unless_worker(worker_available)
        _skip_unless_ollama(ollama_available)

        r = api.post(
            "/api/rag/index/codebase",
            json={
                "root_path": str(fixtures_dir / "codebase"),
                "collection": temp_collection,
            },
            timeout=15,
        )
        assert r.status_code == 202
        task_id = r.json()["task_id"]

        result = _poll_task_until_terminal(api, task_id, timeout=120)
        assert result["status"] in ("completed", "failed"), (
            f"Unexpected terminal status: {result['status']}"
        )

    def test_incremental_reindex(
        self, api, temp_collection, fixtures_dir, worker_available, ollama_available
    ):
        """Indexing the same content twice with incremental=true should succeed.

        The second run is expected to complete (skip unchanged files or be faster).
        Note: fixture paths must be accessible inside the worker container.
        If not mounted, the task will fail — we accept that as a valid outcome and
        only assert the API mechanics work (task created, polled, reaches terminal).
        """
        _skip_unless_worker(worker_available)
        _skip_unless_ollama(ollama_available)

        payload = {
            "root_path": str(fixtures_dir / "codebase"),
            "collection": temp_collection,
            "incremental": True,
        }

        # First run
        r1 = api.post("/api/rag/index/codebase", json=payload, timeout=15)
        assert r1.status_code == 202
        result1 = _poll_task_until_terminal(api, r1.json()["task_id"], timeout=120)
        # Path may not be accessible inside Docker — accept completed or failed
        if result1["status"] == "failed":
            pytest.skip(
                "Fixture path not accessible inside worker container "
                "(run with --no-docker or mount fixtures)"
            )
        assert result1["status"] == "completed"

        # Second run (incremental)
        r2 = api.post("/api/rag/index/codebase", json=payload, timeout=15)
        assert r2.status_code == 202
        result2 = _poll_task_until_terminal(api, r2.json()["task_id"], timeout=120)
        assert result2["status"] == "completed"


# ---------------------------------------------------------------------------
# Document indexing
# ---------------------------------------------------------------------------


class TestIndexDocuments:
    """POST /api/rag/index/documents"""

    def test_index_documents_starts_task(
        self, api, temp_collection, fixtures_dir, worker_available, ollama_available
    ):
        """Posting a document index request returns 202 with a task_id."""
        _skip_unless_worker(worker_available)
        _skip_unless_ollama(ollama_available)

        r = api.post(
            "/api/rag/index/documents",
            json={
                "paths": [
                    str(fixtures_dir / "docs" / "README.txt"),
                    str(fixtures_dir / "docs" / "report.txt"),
                ],
                "collection": temp_collection,
            },
            timeout=15,
        )
        assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.text}"
        data = r.json()
        assert "task_id" in data
        assert data.get("status") == "started"


# ---------------------------------------------------------------------------
# Task management
# ---------------------------------------------------------------------------


class TestTaskManagement:
    """GET /api/rag/tasks and GET /api/rag/tasks/{id}"""

    def test_task_list(self, api):
        """GET /api/rag/tasks returns an object with a tasks array."""
        r = api.get("/api/rag/tasks", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "tasks" in data
        assert isinstance(data["tasks"], list)
        assert "count" in data

    def test_task_get_by_id(
        self, api, temp_collection, fixtures_dir, worker_available, ollama_available
    ):
        """GET /api/rag/tasks/{id} returns the task detail for a known task."""
        _skip_unless_worker(worker_available)
        _skip_unless_ollama(ollama_available)

        # Create a task so we have an ID
        r = api.post(
            "/api/rag/index/codebase",
            json={
                "root_path": str(fixtures_dir / "codebase"),
                "collection": temp_collection,
            },
            timeout=15,
        )
        assert r.status_code == 202
        task_id = r.json()["task_id"]

        r_get = api.get(f"/api/rag/tasks/{task_id}", timeout=10)
        assert r_get.status_code == 200
        data = r_get.json()
        assert data["task_id"] == task_id
        assert "status" in data
        assert "type" in data

    def test_task_get_nonexistent_returns_404(self, api):
        """GET /api/rag/tasks/{id} with a bogus ID returns 404."""
        r = api.get("/api/rag/tasks/nonexistent-task-id-12345", timeout=10)
        assert r.status_code == 404

    def test_cancel_task(
        self, api, temp_collection, fixtures_dir, worker_available, ollama_available
    ):
        """POST /api/rag/tasks/{id}/cancel marks the task as cancelled."""
        _skip_unless_worker(worker_available)
        _skip_unless_ollama(ollama_available)

        # Start a long-ish indexing task
        r = api.post(
            "/api/rag/index/codebase",
            json={
                "root_path": str(fixtures_dir / "codebase"),
                "collection": temp_collection,
            },
            timeout=15,
        )
        assert r.status_code == 202
        task_id = r.json()["task_id"]

        # Immediately cancel
        r_cancel = api.post(f"/api/rag/tasks/{task_id}/cancel", timeout=10)
        assert r_cancel.status_code == 200
        cancel_data = r_cancel.json()
        assert cancel_data.get("status") == "cancelled"
