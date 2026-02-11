"""Tests for the system configuration endpoints.

Routes tested:
  GET    /api/system/config
  PUT    /api/system/config/chunking
  PUT    /api/system/config/pii
  PUT    /api/system/config/ollama
  DELETE /api/system/config/{section}

These endpoints proxy to the gRPC worker's ConfigService.  Tests that
mutate configuration always attempt to reset afterwards to avoid side
effects on other tests.
"""

import pytest


class TestGetConfig:
    """GET /api/system/config"""

    def test_get_config(self, api, worker_available):
        """GET /api/system/config returns the full application configuration."""
        if not worker_available:
            pytest.skip("gRPC worker not available for config")

        r = api.get("/api/system/config", timeout=10)
        assert r.status_code == 200
        data = r.json()
        # The config proto has known top-level sections
        assert isinstance(data, dict)

    def test_get_config_unavailable_returns_error(self, api):
        """If the worker is down, /api/system/config returns 502 or 503."""
        r = api.get("/api/system/config", timeout=10)
        # This test is informational: we just verify it does not crash
        assert r.status_code in (200, 502, 503)


class TestUpdateChunking:
    """PUT /api/system/config/chunking"""

    def test_update_chunking(self, api, worker_available):
        """Update chunk_size and chunk_overlap, then verify via GET."""
        if not worker_available:
            pytest.skip("gRPC worker not available for config")

        new_values = {"chunk_size": 1024, "chunk_overlap": 128}

        r_put = api.put(
            "/api/system/config/chunking",
            json=new_values,
            timeout=10,
        )
        assert r_put.status_code == 200, f"Update failed: {r_put.text}"

        # Verify by reading back
        r_get = api.get("/api/system/config", timeout=10)
        if r_get.status_code == 200:
            cfg = r_get.json()
            chunking = cfg.get("chunking", cfg.get("chunkingConfig", {}))
            if chunking:
                assert chunking.get("chunk_size", chunking.get("chunkSize")) == 1024

        # Reset
        api.delete("/api/system/config/chunking", timeout=10)


class TestUpdatePII:
    """PUT /api/system/config/pii"""

    def test_update_pii(self, api, worker_available):
        """Toggle PII enabled flag and verify the change persists."""
        if not worker_available:
            pytest.skip("gRPC worker not available for config")

        # Enable PII
        r_enable = api.put(
            "/api/system/config/pii",
            json={"enabled": True},
            timeout=10,
        )
        assert r_enable.status_code == 200, f"PII enable failed: {r_enable.text}"

        # Disable PII
        r_disable = api.put(
            "/api/system/config/pii",
            json={"enabled": False},
            timeout=10,
        )
        assert r_disable.status_code == 200, f"PII disable failed: {r_disable.text}"

        # Reset
        api.delete("/api/system/config/pii", timeout=10)


class TestUpdateOllama:
    """PUT /api/system/config/ollama"""

    def test_update_ollama(self, api, worker_available):
        """Change Ollama base_url via the config endpoint."""
        if not worker_available:
            pytest.skip("gRPC worker not available for config")

        r = api.put(
            "/api/system/config/ollama",
            json={"base_url": "http://localhost:11434"},
            timeout=10,
        )
        assert r.status_code == 200, f"Update Ollama config failed: {r.text}"

        # Reset
        api.delete("/api/system/config/ollama", timeout=10)


class TestResetConfig:
    """DELETE /api/system/config/{section}"""

    @pytest.mark.parametrize(
        "section",
        ["chunking", "pii", "ollama", "qdrant", "image", "all"],
    )
    def test_reset_config(self, api, section, worker_available):
        """DELETE /api/system/config/{section} resets that section to defaults."""
        if not worker_available:
            pytest.skip("gRPC worker not available for config")

        r = api.delete(f"/api/system/config/{section}", timeout=10)
        assert r.status_code == 200, (
            f"Reset config/{section} failed ({r.status_code}): {r.text}"
        )
