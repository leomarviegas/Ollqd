"""Tests for the GET /api/system/health endpoint.

The health endpoint pings Ollama and Qdrant and returns an overall status
of 'ok' (both reachable) or 'degraded' (at least one unreachable).
"""

import requests
import pytest


class TestHealthEndpoint:
    """Health endpoint basic contract tests."""

    def test_health_endpoint_returns_ok(self, api):
        """GET /api/system/health returns 200 with a top-level status field."""
        r = api.get("/api/system/health", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert data["status"] in ("ok", "degraded")

    def test_health_shows_ollama_status(self, api):
        """Response includes an ollama object with a status field."""
        r = api.get("/api/system/health", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "ollama" in data
        ollama = data["ollama"]
        assert "status" in ollama
        assert ollama["status"] in ("ok", "error")

    def test_health_shows_qdrant_status(self, api):
        """Response includes a qdrant object with a status field."""
        r = api.get("/api/system/health", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "qdrant" in data
        qdrant = data["qdrant"]
        assert "status" in qdrant
        assert qdrant["status"] in ("ok", "error")

    def test_health_custom_urls(self, api):
        """Passing ?ollama_url and ?qdrant_url overrides the default hosts."""
        r = api.get(
            "/api/system/health",
            params={
                "ollama_url": "http://localhost:11434",
                "qdrant_url": "http://localhost:6333",
            },
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        # The response should contain both service sections regardless
        assert "ollama" in data
        assert "qdrant" in data

    def test_health_invalid_url_returns_degraded(self, api):
        """Pointing to a bad URL should report status=degraded overall."""
        r = api.get(
            "/api/system/health",
            params={
                "ollama_url": "http://127.0.0.1:19999",
                "qdrant_url": "http://127.0.0.1:19998",
            },
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "degraded"
        assert data["ollama"]["status"] == "error"
        assert data["qdrant"]["status"] == "error"


class TestHealthResponseStructure:
    """Validate the structure and metadata of the health response."""

    def test_health_ollama_includes_url(self, api):
        """The ollama section includes the URL that was checked."""
        r = api.get("/api/system/health", timeout=10)
        data = r.json()
        assert "url" in data["ollama"]
        assert data["ollama"]["url"].startswith("http")

    def test_health_qdrant_includes_url(self, api):
        """The qdrant section includes the URL that was checked."""
        r = api.get("/api/system/health", timeout=10)
        data = r.json()
        assert "url" in data["qdrant"]
        assert data["qdrant"]["url"].startswith("http")

    def test_health_includes_latency(self, api):
        """Both service sections include a latency measurement."""
        r = api.get("/api/system/health", timeout=10)
        data = r.json()
        assert "latency" in data["ollama"]
        assert "latency" in data["qdrant"]
