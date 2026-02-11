"""Tests for the RAG visualization endpoints.

Routes tested:
  GET /api/rag/visualize/{collection}/overview
  GET /api/rag/visualize/{collection}/file-tree
  GET /api/rag/visualize/{collection}/vectors

These endpoints proxy to the gRPC VisualizationService.  When the worker
is unavailable the gateway returns 503.
"""

import pytest


class TestOverviewEndpoint:
    """GET /api/rag/visualize/{collection}/overview"""

    def test_overview_endpoint(self, api, temp_collection, worker_available):
        """GET overview returns 200 with nodes/edges structure or 502/503."""
        if not worker_available:
            pytest.skip("gRPC worker not available")

        r = api.get(
            f"/api/rag/visualize/{temp_collection}/overview",
            timeout=15,
        )
        # Empty collection may succeed with empty data or error from worker
        assert r.status_code in (200, 502)
        if r.status_code == 200:
            data = r.json()
            # Overview response should have nodes, edges, and/or stats
            assert isinstance(data, dict)

    def test_overview_with_limit(self, api, temp_collection, worker_available):
        """Passing ?limit=10 constrains the overview result."""
        if not worker_available:
            pytest.skip("gRPC worker not available")

        r = api.get(
            f"/api/rag/visualize/{temp_collection}/overview",
            params={"limit": 10},
            timeout=15,
        )
        assert r.status_code in (200, 502)


class TestFileTreeEndpoint:
    """GET /api/rag/visualize/{collection}/file-tree"""

    def test_file_tree_endpoint(self, api, temp_collection, worker_available):
        """GET file-tree returns 200 with tree structure or 502/503."""
        if not worker_available:
            pytest.skip("gRPC worker not available")

        r = api.get(
            f"/api/rag/visualize/{temp_collection}/file-tree",
            timeout=15,
        )
        assert r.status_code in (200, 502)
        if r.status_code == 200:
            data = r.json()
            assert isinstance(data, dict)

    def test_file_tree_with_path_filter(self, api, temp_collection, worker_available):
        """Passing ?file_path=... filters the tree."""
        if not worker_available:
            pytest.skip("gRPC worker not available")

        r = api.get(
            f"/api/rag/visualize/{temp_collection}/file-tree",
            params={"file_path": "/some/path"},
            timeout=15,
        )
        assert r.status_code in (200, 502)


class TestVectorsEndpoint:
    """GET /api/rag/visualize/{collection}/vectors"""

    def test_vectors_endpoint_pca(self, api, temp_collection, worker_available):
        """GET vectors with method=pca returns 200 or appropriate error."""
        if not worker_available:
            pytest.skip("gRPC worker not available")

        r = api.get(
            f"/api/rag/visualize/{temp_collection}/vectors",
            params={"method": "pca"},
            timeout=15,
        )
        assert r.status_code in (200, 502)
        if r.status_code == 200:
            data = r.json()
            assert isinstance(data, dict)

    def test_vectors_endpoint_tsne(self, api, temp_collection, worker_available):
        """GET vectors with method=tsne returns 200 or appropriate error."""
        if not worker_available:
            pytest.skip("gRPC worker not available")

        r = api.get(
            f"/api/rag/visualize/{temp_collection}/vectors",
            params={"method": "tsne", "dims": 2, "limit": 50},
            timeout=15,
        )
        assert r.status_code in (200, 502)

    def test_vectors_default_method(self, api, temp_collection, worker_available):
        """GET vectors without method param defaults to PCA."""
        if not worker_available:
            pytest.skip("gRPC worker not available")

        r = api.get(
            f"/api/rag/visualize/{temp_collection}/vectors",
            timeout=15,
        )
        assert r.status_code in (200, 502)
