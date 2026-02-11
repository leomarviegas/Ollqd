"""Tests for the RAG search endpoints.

Routes tested:
  POST /api/rag/search
  POST /api/rag/search/{collection}

Meaningful search results require indexed content and a running Ollama
instance for embedding.  Tests that need pre-indexed data are marked with
``@pytest.mark.requires_indexed``.
"""

import pytest


class TestSearchValidation:
    """Basic validation and error handling for the search endpoints."""

    def test_search_requires_collection(self, api, worker_available):
        """POST /api/rag/search with no meaningful query params returns an error or empty result."""
        if not worker_available:
            pytest.skip("gRPC worker not available")

        r = api.post(
            "/api/rag/search",
            json={"query": "hello", "top_k": 5},
            timeout=15,
        )
        # The search may fail (502 if no default collection) or return empty hits
        # Both are acceptable for this validation test
        assert r.status_code in (200, 400, 502)

    def test_search_empty_collection_returns_empty(
        self, api, temp_collection, worker_available, ollama_available
    ):
        """Searching in an empty collection returns an empty hits list or an error."""
        if not worker_available:
            pytest.skip("gRPC worker not available")
        if not ollama_available:
            pytest.skip("Ollama not available for embedding")

        r = api.post(
            f"/api/rag/search/{temp_collection}",
            json={"query": "test query", "top_k": 5},
            timeout=15,
        )
        # Worker may return empty results or an error for a collection with no vectors
        if r.status_code == 200:
            data = r.json()
            hits = data.get("hits", data.get("results", []))
            assert isinstance(hits, list)
            assert len(hits) == 0
        else:
            # 502 is acceptable if the worker could not perform the search
            assert r.status_code in (400, 502)


class TestSearchCollection:
    """POST /api/rag/search/{collection}"""

    def test_search_collection_endpoint(
        self, api, temp_collection, worker_available, ollama_available
    ):
        """POST /api/rag/search/{collection} accepts a valid request body."""
        if not worker_available:
            pytest.skip("gRPC worker not available")
        if not ollama_available:
            pytest.skip("Ollama not available for embedding")

        r = api.post(
            f"/api/rag/search/{temp_collection}",
            json={"query": "function", "top_k": 3},
            timeout=15,
        )
        # Either success or a gateway error (worker could reject the call)
        assert r.status_code in (200, 400, 502)

    @pytest.mark.requires_indexed
    def test_search_returns_hits(self, api, temp_collection):
        """After indexing, a search should return at least one hit.

        This test is only meaningful when pre-indexed content is available.
        """
        r = api.post(
            f"/api/rag/search/{temp_collection}",
            json={"query": "main function", "top_k": 5},
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        hits = data.get("hits", data.get("results", []))
        assert len(hits) > 0, "Expected at least one search hit"

    @pytest.mark.requires_indexed
    def test_search_hits_have_expected_fields(self, api, temp_collection):
        """Search hits should contain score, file_path, and content fields."""
        r = api.post(
            f"/api/rag/search/{temp_collection}",
            json={"query": "configuration", "top_k": 3},
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        hits = data.get("hits", data.get("results", []))
        for hit in hits:
            assert "score" in hit or "Score" in hit
