"""Tests for Qdrant collection management endpoints.

Routes tested:
  GET    /api/qdrant/collections
  PUT    /api/qdrant/collections/{name}  (via Qdrant proxy)
  DELETE /api/qdrant/collections/{name}
  GET    /api/qdrant/collections/{name}/points
  POST   /api/qdrant/collections           (gateway wrapper)
"""

import time

import pytest
import requests


class TestListCollections:
    """GET /api/qdrant/collections"""

    def test_list_collections(self, api, wait_for_qdrant):
        """GET /api/qdrant/collections returns 200 with a collections list."""
        r = api.get("/api/qdrant/collections", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "collections" in data
        assert isinstance(data["collections"], list)


class TestCreateAndDeleteCollection:
    """PUT + DELETE /api/qdrant/collections/{name} lifecycle."""

    def test_create_and_delete_collection(self, api, gateway_url, wait_for_qdrant):
        """Create a collection via PUT, verify it appears in the list, then delete it."""
        name = f"test_api_lifecycle_{int(time.time() * 1000)}"

        # Create collection through the Qdrant proxy (PUT)
        r_create = requests.put(
            f"{gateway_url}/api/qdrant/collections/{name}",
            json={"vectors": {"size": 384, "distance": "Cosine"}},
            timeout=10,
        )
        assert r_create.status_code in (200, 201), (
            f"Failed to create collection: {r_create.text}"
        )

        # Verify it shows up in the list
        r_list = api.get("/api/qdrant/collections", timeout=10)
        assert r_list.status_code == 200
        names = [c.get("name") for c in r_list.json().get("collections", [])]
        assert name in names, f"Collection {name} not found in {names}"

        # Delete
        r_delete = api.delete(f"/api/qdrant/collections/{name}", timeout=10)
        assert r_delete.status_code == 200

        # Verify it is gone
        r_list2 = api.get("/api/qdrant/collections", timeout=10)
        names2 = [c.get("name") for c in r_list2.json().get("collections", [])]
        assert name not in names2

    def test_create_collection_via_post(self, api, wait_for_qdrant):
        """POST /api/qdrant/collections with name/vector_size/distance creates a collection."""
        name = f"test_api_post_{int(time.time() * 1000)}"
        r = api.post(
            "/api/qdrant/collections",
            json={"name": name, "vector_size": 384, "distance": "Cosine"},
            timeout=10,
        )
        assert r.status_code in (200, 201), f"Create failed: {r.text}"

        # Clean up
        api.delete(f"/api/qdrant/collections/{name}", timeout=10)


class TestDeleteNonexistent:
    """DELETE /api/qdrant/collections/{name} for a collection that does not exist."""

    def test_delete_nonexistent_collection(self, api, wait_for_qdrant):
        """Deleting a collection that does not exist returns a non-200 status or an error body."""
        name = f"nonexistent_{int(time.time() * 1000)}"
        r = api.delete(f"/api/qdrant/collections/{name}", timeout=10)
        # Qdrant returns 404 or the gateway returns an error body
        # Either a non-2xx status or a JSON body with an error indicator is acceptable
        if r.status_code == 200:
            # Some Qdrant versions return 200 with result=false
            data = r.json()
            assert data.get("result") is not True or "error" in str(data).lower()
        else:
            assert r.status_code in (404, 400)


class TestCollectionPoints:
    """GET /api/qdrant/collections/{name}/points"""

    def test_collection_points_empty(self, api, temp_collection):
        """A freshly created collection has zero points."""
        r = api.get(
            f"/api/qdrant/collections/{temp_collection}/points",
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        points = data.get("points", [])
        assert isinstance(points, list)
        assert len(points) == 0
