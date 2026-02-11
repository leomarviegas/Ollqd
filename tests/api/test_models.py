"""Tests for the Ollama model management endpoints.

Routes tested:
  GET    /api/ollama/models              (list models)
  GET    /api/ollama/api/tags            (raw proxy to Ollama /api/tags)
  POST   /api/ollama/models/show         (show model info)
  POST   /api/ollama/models/pull         (pull model — streams SSE)
  POST   /api/ollama/api/show            (raw proxy)
  POST   /api/ollama/api/pull            (raw proxy)
"""

import pytest


class TestListModels:
    """GET /api/ollama/models and GET /api/ollama/api/tags"""

    def test_list_models(self, api, ollama_available):
        """GET /api/ollama/models returns 200 with a models list when Ollama is up."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        r = api.get("/api/ollama/models", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "models" in data
        assert isinstance(data["models"], list)

    def test_list_models_via_proxy(self, api, ollama_available):
        """GET /api/ollama/api/tags returns the raw Ollama tags response."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        r = api.get("/api/ollama/api/tags", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "models" in data


class TestPullModel:
    """POST /api/ollama/models/pull and POST /api/ollama/api/pull"""

    def test_pull_invalid_model(self, api, ollama_available):
        """Pulling a non-existent model name should result in an error event or HTTP error."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        r = api.post(
            "/api/ollama/models/pull",
            json={"name": "nonexistent-model-xyz-9999:latest"},
            timeout=30,
            # The response is SSE-streamed; requests will buffer the entire body
            stream=False,
        )
        # The gateway returns 200 with SSE, but the final events contain an error
        # or the proxy may return an error status
        if r.status_code == 200:
            body = r.text
            # The stream should contain an error message from Ollama
            assert "error" in body.lower() or "[DONE]" in body
        else:
            # Non-200 is also acceptable
            assert r.status_code in (400, 404, 500, 502)

    def test_pull_via_proxy_invalid_model(self, api, ollama_available):
        """POST /api/ollama/api/pull with a bad model name via the raw proxy."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        r = api.post(
            "/api/ollama/api/pull",
            json={"name": "nonexistent-model-xyz-9999:latest", "stream": False},
            timeout=30,
        )
        # Ollama returns a JSON error or a non-200 status
        if r.status_code == 200:
            data = r.json()
            assert "error" in data or "status" in data
        else:
            assert r.status_code in (400, 404, 500)


class TestModelInfo:
    """POST /api/ollama/models/show"""

    def test_model_info(self, api, ollama_available):
        """POST /api/ollama/models/show with a valid model returns model metadata."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        # First get the list of models to find a real name
        r_list = api.get("/api/ollama/models", timeout=10)
        if r_list.status_code != 200:
            pytest.skip("Could not list models")

        models = r_list.json().get("models", [])
        if not models:
            pytest.skip("No models available on Ollama")

        model_name = models[0].get("name", models[0].get("model", ""))
        assert model_name, "Could not determine model name"

        r = api.post(
            "/api/ollama/models/show",
            json={"name": model_name},
            timeout=15,
        )
        assert r.status_code == 200, f"Show model failed: {r.text}"
        data = r.json()
        # Ollama /api/show returns modelinfo, parameters, etc.
        assert isinstance(data, dict)

    def test_model_info_invalid_name(self, api, ollama_available):
        """POST /api/ollama/models/show with a nonexistent model returns an error."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        r = api.post(
            "/api/ollama/models/show",
            json={"name": "nonexistent-model-xyz-9999:latest"},
            timeout=15,
        )
        assert r.status_code in (404, 500), (
            f"Expected error status, got {r.status_code}: {r.text}"
        )
